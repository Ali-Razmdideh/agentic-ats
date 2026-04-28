from __future__ import annotations

import pytest

from ats.invoke import _extract_json


def test_plain_json() -> None:
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_code_fence() -> None:
    text = '```json\n{"a": 1}\n```'
    assert _extract_json(text) == {"a": 1}


def test_with_preamble() -> None:
    text = 'Here you go:\n{"a": 1, "b": [2,3]}'
    assert _extract_json(text) == {"a": 1, "b": [2, 3]}


def test_invalid() -> None:
    with pytest.raises(Exception):
        _extract_json("nope")
