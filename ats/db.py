from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jd_path TEXT NOT NULL,
    jd_hash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    usage_json TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    name TEXT,
    email TEXT,
    phone TEXT,
    parsed_json TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    run_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    score REAL NOT NULL,
    rationale TEXT,
    verified_json TEXT,
    PRIMARY KEY (run_id, candidate_id),
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

CREATE TABLE IF NOT EXISTS audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS shortlists (
    run_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    decision TEXT NOT NULL,
    PRIMARY KEY (run_id, candidate_id),
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # Lightweight migration: add usage_json to existing runs tables.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(runs)")}
        if "usage_json" not in cols:
            conn.execute("ALTER TABLE runs ADD COLUMN usage_json TEXT")


def create_run(db_path: Path, jd_path: str, jd_hash: str) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO runs (jd_path, jd_hash, started_at, status) VALUES (?,?,?,?)",
            (jd_path, jd_hash, _now(), "running"),
        )
        if cur.lastrowid is None:
            raise RuntimeError("create_run: insert did not produce a row id")
        return int(cur.lastrowid)


def finish_run(db_path: Path, run_id: int, status: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE runs SET finished_at=?, status=? WHERE id=?",
            (_now(), status, run_id),
        )


def update_run_usage(db_path: Path, run_id: int, usage: dict[str, Any]) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE runs SET usage_json=? WHERE id=?",
            (json.dumps(usage), run_id),
        )


def get_run(db_path: Path, run_id: int) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("usage_json"):
            d["usage"] = json.loads(d["usage_json"])
        return d


def upsert_candidate(
    db_path: Path,
    file_path: str,
    file_hash: str,
    parsed: dict[str, Any],
) -> int:
    name = parsed.get("contact", {}).get("name")
    email = parsed.get("contact", {}).get("email")
    phone = parsed.get("contact", {}).get("phone")
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM candidates WHERE file_hash=?", (file_hash,)
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            "INSERT INTO candidates (file_path, file_hash, name, email, phone, parsed_json)"
            " VALUES (?,?,?,?,?,?)",
            (file_path, file_hash, name, email, phone, json.dumps(parsed)),
        )
        if cur.lastrowid is None:
            raise RuntimeError("upsert_candidate: insert did not produce a row id")
        return int(cur.lastrowid)


def write_score(
    db_path: Path,
    run_id: int,
    candidate_id: int,
    score: float,
    rationale: str,
    verified: dict[str, Any] | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scores (run_id, candidate_id, score, rationale, verified_json)"
            " VALUES (?,?,?,?,?)",
            (
                run_id,
                candidate_id,
                score,
                rationale,
                json.dumps(verified) if verified is not None else None,
            ),
        )


def write_audit(db_path: Path, run_id: int, kind: str, payload: dict[str, Any]) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO audits (run_id, kind, payload_json) VALUES (?,?,?)",
            (run_id, kind, json.dumps(payload)),
        )


def write_shortlist(
    db_path: Path,
    run_id: int,
    ranked: list[tuple[int, str]],
) -> None:
    with connect(db_path) as conn:
        for rank, (candidate_id, decision) in enumerate(ranked, start=1):
            conn.execute(
                "INSERT OR REPLACE INTO shortlists (run_id, candidate_id, rank, decision)"
                " VALUES (?,?,?,?)",
                (run_id, candidate_id, rank, decision),
            )


def get_run_scores(db_path: Path, run_id: int) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT s.candidate_id, s.score, s.rationale, c.name, c.email"
            " FROM scores s JOIN candidates c ON c.id = s.candidate_id"
            " WHERE s.run_id=? ORDER BY s.score DESC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_audits(db_path: Path, run_id: int) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT kind, payload_json FROM audits WHERE run_id=?", (run_id,)
        ).fetchall()
        return [
            {"kind": r["kind"], "payload": json.loads(r["payload_json"])} for r in rows
        ]


def get_candidate(db_path: Path, candidate_id: int) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM candidates WHERE id=?", (candidate_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("parsed_json"):
            d["parsed"] = json.loads(d["parsed_json"])
        return d
