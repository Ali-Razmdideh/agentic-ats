from __future__ import annotations

from pathlib import Path

from ats import storage


def test_hash_file_stable(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hello")
    assert storage.hash_file(p) == storage.hash_file(p)


def test_hash_file_differs(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    a.write_text("hello")
    b = tmp_path / "b.txt"
    b.write_text("world")
    assert storage.hash_file(a) != storage.hash_file(b)


def test_iter_resumes_filters_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "ignore.zip").write_text("x")
    found = {p.name for p in storage.iter_resumes(tmp_path)}
    assert found == {"a.txt", "b.pdf"}
