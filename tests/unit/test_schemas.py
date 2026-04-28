"""Schema coercion contract: list-vs-dict, envelope unwraps, default fallback."""

from __future__ import annotations

from ats.agents.schemas import BiasReport, DedupReport, Ranking, coerce_to_model


def test_list_wraps_into_primary_field() -> None:
    raw = [{"cohort": "A", "metric": "mean", "gap": 0.1, "note": "x"}]
    m = coerce_to_model("bias_auditor", raw)
    assert isinstance(m, BiasReport)
    assert len(m.findings) == 1
    assert m.findings[0].cohort == "A"


def test_data_envelope_dict() -> None:
    raw = {"data": {"groups": [{"canonical_id": 1, "duplicate_ids": [2]}]}}
    m = coerce_to_model("deduper", raw)
    assert isinstance(m, DedupReport)
    assert len(m.groups) == 1


def test_data_envelope_list_wraps_into_primary_field() -> None:
    """{"data": [...]} should also be wrapped into the schema's list field."""
    raw = {"data": [{"canonical_id": 1, "duplicate_ids": [2]}]}
    m = coerce_to_model("deduper", raw)
    assert isinstance(m, DedupReport)
    assert m.groups[0].canonical_id == 1


def test_garbage_falls_back_to_default() -> None:
    """All-fail validation must yield an empty default, not raise."""
    m = coerce_to_model("ranker", "totally-not-a-ranking")
    assert isinstance(m, Ranking)
    assert m.ranked == []


def test_valid_dict_passes_through() -> None:
    raw = {"status": "block", "findings": [], "recommendation": "review"}
    m = coerce_to_model("bias_auditor", raw)
    assert isinstance(m, BiasReport)
    assert m.status == "block"
