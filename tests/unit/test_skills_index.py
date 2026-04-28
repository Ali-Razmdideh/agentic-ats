from __future__ import annotations

from ats.tools.skills_index import normalize_skill


def test_exact_match() -> None:
    assert normalize_skill("Python") == "Python"


def test_fuzzy_match() -> None:
    assert normalize_skill("Pythn") == "Python"
    assert normalize_skill("javascript") == "JavaScript"


def test_unknown_returns_none() -> None:
    assert normalize_skill("Underwater Basket Weaving") is None
