from __future__ import annotations

from ats.agents.definitions import NEEDED, OPTIONAL, RECOMMENDED, build_agents
from ats.config import Settings


def test_all_thirteen_agents_registered() -> None:
    agents = build_agents(Settings())
    expected = set(NEEDED) | set(RECOMMENDED) | set(OPTIONAL)
    assert set(agents.keys()) == expected
    assert len(agents) == 13


def test_required_agents_have_models_and_prompts() -> None:
    agents = build_agents(Settings())
    for name, a in agents.items():
        assert a.description, f"{name} missing description"
        assert a.prompt, f"{name} missing prompt"
        assert a.model, f"{name} missing model"


def test_bias_auditor_has_audit_tool() -> None:
    agents = build_agents(Settings())
    assert "mcp__ats__save_audit" in (agents["bias_auditor"].tools or [])


def test_parser_can_read_resume() -> None:
    agents = build_agents(Settings())
    assert "mcp__ats__read_resume" in (agents["parser"].tools or [])


def test_enricher_has_webfetch() -> None:
    agents = build_agents(Settings())
    assert "WebFetch" in (agents["enricher"].tools or [])
