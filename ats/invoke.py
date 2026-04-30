"""Subagent dispatch: prompt → JSON → validated Pydantic model.

The orchestrator calls :func:`invoke_agent` for every agent step. This module
owns the cross-cutting concerns (timeout, retries, JSON extraction, schema
validation, structured logging, usage capture) so the orchestrator stays
focused on sequencing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    UserMessage,
)
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ats.agents.schemas import coerce_to_model
from ats.cost import Usage

log = logging.getLogger("ats.invoke")

_JSON_RE = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


class TransientAgentError(RuntimeError):
    """Network / rate-limit / parsing flake — retry candidate."""


class FatalAgentError(RuntimeError):
    """Non-retryable: schema invalid, agent rejected the request, etc."""


class _Client(Protocol):
    async def query(self, prompt: str) -> None: ...
    def receive_response(self) -> Any: ...


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if m:
            return json.loads(m.group(0))
        raise


def _texts_from_tool_result(block: ToolResultBlock) -> list[str]:
    out: list[str] = []
    c = block.content
    if isinstance(c, str):
        out.append(c)
    elif isinstance(c, list):
        for item in c:
            if isinstance(item, dict) and item.get("type") == "text":
                out.append(str(item.get("text", "")))
    return out


def _record_usage(
    usage: Usage | None,
    agent: str,
    result: ResultMessage | None,
) -> None:
    """Pull token counts off the SDK's ResultMessage and add them to ``usage``."""
    if usage is None or result is None:
        return
    raw = result.usage or {}
    if not isinstance(raw, dict):
        return
    in_tok = int(raw.get("input_tokens") or 0)
    out_tok = int(raw.get("output_tokens") or 0)
    cache_read = int(raw.get("cache_read_input_tokens") or 0)
    cache_write = int(raw.get("cache_creation_input_tokens") or 0)
    model = ""
    model_usage = result.model_usage or {}
    if isinstance(model_usage, dict) and model_usage:
        # First key is the model id when single-model; pick any.
        model = next(iter(model_usage.keys()), "")
    usage.add(agent, model, in_tok, out_tok, cache_read, cache_write)


async def _one_attempt(
    client: ClaudeSDKClient | _Client,
    agent: str,
    payload: str,
    timeout_s: float,
    client_lock: asyncio.Lock | None,
    usage: Usage | None,
) -> Any:
    """Send one prompt and consume the full response stream atomically.

    The lock guarantees that on a shared ``ClaudeSDKClient`` (which uses one
    underlying request/response channel) two concurrent invocations do not
    interleave their messages. If ``client_lock`` is ``None`` the caller is
    responsible for serialization (e.g. tests with a per-call fake client).
    """
    prompt = (
        f"Dispatch the {agent} subagent with the input below. "
        f"Reply with the subagent's JSON output VERBATIM, nothing else.\n\n"
        f"INPUT:\n{payload}"
    )
    tool_result_texts: list[str] = []
    text_chunks: list[str] = []
    last_result: ResultMessage | None = None

    async def _consume() -> None:
        nonlocal last_result
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_chunks.append(block.text)
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        tool_result_texts.extend(_texts_from_tool_result(block))
            if isinstance(msg, ResultMessage):
                last_result = msg
                return

    async def _round_trip() -> None:
        await client.query(prompt)
        try:
            await asyncio.wait_for(_consume(), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise TransientAgentError(f"{agent}: timeout after {timeout_s}s") from exc

    if client_lock is not None:
        async with client_lock:
            await _round_trip()
    else:
        await _round_trip()

    _record_usage(usage, agent, last_result)

    for candidate in tool_result_texts + text_chunks:
        try:
            return _extract_json(candidate)
        except Exception:
            continue
    raise TransientAgentError(
        f"{agent}: no parseable JSON in response. "
        f"text={text_chunks!r} tool_results={tool_result_texts!r}"
    )


async def invoke_agent(
    client: ClaudeSDKClient | _Client,
    agent: str,
    payload: str,
    *,
    timeout_s: float = 120.0,
    max_retries: int = 2,
    run_id: int | None = None,
    candidate_id: int | None = None,
    client_lock: asyncio.Lock | None = None,
    usage: Usage | None = None,
) -> BaseModel:
    """Invoke a subagent and return its validated, typed output."""
    from ats.agents.schemas import CoercionFailedError

    start = time.monotonic()
    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(
                (TransientAgentError, CoercionFailedError)
            ),
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=1.5, min=1, max=10),
            reraise=True,
        ):
            with attempt:
                raw = await _one_attempt(
                    client, agent, payload, timeout_s, client_lock, usage
                )
                try:
                    model = coerce_to_model(agent, raw)
                except CoercionFailedError as exc:
                    raw_str = str(exc.raw)[:1500] if exc.raw is not None else ""
                    log.warning(
                        "agent output unusable; retrying. agent=%s attempt=%d raw=%s",
                        agent,
                        attempt.retry_state.attempt_number,
                        raw_str,
                        extra={
                            "run_id": run_id,
                            "candidate_id": candidate_id,
                            "agent": agent,
                            "attempt": attempt.retry_state.attempt_number,
                            "raw_preview": raw_str,
                        },
                    )
                    raise
                latency_ms = int((time.monotonic() - start) * 1000)
                log.info(
                    "agent ok",
                    extra={
                        "run_id": run_id,
                        "candidate_id": candidate_id,
                        "agent": agent,
                        "latency_ms": latency_ms,
                        "attempt": attempt.retry_state.attempt_number,
                    },
                )
                return model
    except RetryError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        log.error(
            "agent failed",
            extra={
                "run_id": run_id,
                "candidate_id": candidate_id,
                "agent": agent,
                "latency_ms": latency_ms,
                "error": str(exc),
            },
        )
        raise FatalAgentError(f"{agent}: exhausted retries — {exc}") from exc
    raise FatalAgentError(f"{agent}: unreachable")  # for mypy
