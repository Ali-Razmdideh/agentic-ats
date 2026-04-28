"""A FakeClaudeClient that mimics the Agent SDK message stream from canned data.

Lets us run the full orchestrator end-to-end without network or API key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    UserMessage,
)

# Canned output is keyed by agent name. A handler may inspect the payload
# to vary the response (e.g. parser keyed by file path).
Handler = Callable[[str], dict[str, Any] | list[Any]]


_AGENT_RE = re.compile(r"Dispatch the (\w+) subagent")
_INPUT_RE = re.compile(r"INPUT:\n(.*)\Z", re.DOTALL)


@dataclass
class FakeClaudeClient:
    handlers: dict[str, Handler] = field(default_factory=dict)
    _last_prompt: str = ""

    async def __aenter__(self) -> "FakeClaudeClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def query(self, prompt: str) -> None:
        self._last_prompt = prompt

    def receive_response(self) -> AsyncIterator[Any]:
        prompt = self._last_prompt
        m_agent = _AGENT_RE.search(prompt)
        m_input = _INPUT_RE.search(prompt)
        agent = m_agent.group(1) if m_agent else "unknown"
        payload = m_input.group(1) if m_input else ""

        async def _gen() -> AsyncIterator[Any]:
            handler = self.handlers.get(agent)
            if handler is None:
                # Default to a permissive empty object — schema's defaults
                # will fill it in.
                output: Any = {}
            else:
                output = handler(payload)
            text = json.dumps(output)

            # Subagent's "verbatim" output, surfaced as a ToolResultBlock
            # (the same path real agents take).
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id="fake-1",
                        content=[{"type": "text", "text": text}],
                    )
                ]
            )
            yield AssistantMessage(
                content=[TextBlock(text=text)],
                model="fake",
            )
            yield ResultMessage(
                subtype="end_turn",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="fake",
                total_cost_usd=0.0,
            )

        return _gen()


def make_factory(
    handlers: dict[str, Handler],
) -> Callable[[ClaudeAgentOptions], FakeClaudeClient]:
    def factory(options: ClaudeAgentOptions) -> FakeClaudeClient:
        return FakeClaudeClient(handlers=handlers)

    return factory
