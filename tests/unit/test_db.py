from __future__ import annotations

from pathlib import Path

from ats import db


def test_init_creates_tables(tmp_path: Path) -> None:
    p = tmp_path / "ats.db"
    db.init_db(p)
    with db.connect(p) as conn:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"runs", "candidates", "scores", "audits", "shortlists"} <= names


def test_upsert_dedup(tmp_path: Path) -> None:
    p = tmp_path / "ats.db"
    db.init_db(p)
    parsed = {"contact": {"name": "A", "email": "a@x.com", "phone": "1"}}
    a = db.upsert_candidate(p, "/r/a.txt", "h1", parsed)
    b = db.upsert_candidate(p, "/r/a-copy.txt", "h1", parsed)
    assert a == b


def test_run_lifecycle(tmp_path: Path) -> None:
    p = tmp_path / "ats.db"
    db.init_db(p)
    rid = db.create_run(p, "/jd.txt", "h")
    assert rid > 0
    cid = db.upsert_candidate(p, "/r.txt", "rh", {"contact": {"name": "X"}})
    db.write_score(p, rid, cid, 0.8, "good", {"verified": ["Python"]})
    db.write_audit(p, rid, "bias", {"status": "pass"})
    db.write_shortlist(p, rid, [(cid, "shortlist")])
    db.finish_run(p, rid, "ok")

    scores = db.get_run_scores(p, rid)
    assert len(scores) == 1
    assert scores[0]["score"] == 0.8

    audits = db.get_audits(p, rid)
    assert audits[0]["kind"] == "bias"
    assert audits[0]["payload"]["status"] == "pass"
