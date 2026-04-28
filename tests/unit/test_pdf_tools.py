from __future__ import annotations

from pathlib import Path

import pytest

from ats.tools.pdf_tools import extract_text_from_path


def test_txt(tmp_path: Path) -> None:
    p = tmp_path / "r.txt"
    p.write_text("Hello resume")
    assert "Hello resume" in extract_text_from_path(p)


def test_md(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("# Resume\n\nHi")
    assert "Resume" in extract_text_from_path(p)


def test_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "r.zip"
    p.write_bytes(b"PK")
    with pytest.raises(ValueError):
        extract_text_from_path(p)
