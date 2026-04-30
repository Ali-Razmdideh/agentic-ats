"""SQLAlchemy ORM models for the ATS storage layer."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    admin = "admin"
    hiring_manager = "hiring_manager"
    reviewer = "reviewer"


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    blocked_by_bias = "blocked_by_bias"
    budget_exceeded = "budget_exceeded"
    ok = "ok"


class DecisionKind(str, enum.Enum):
    shortlist = "shortlist"
    reject = "reject"
    hold = "hold"


class ActorKind(str, enum.Enum):
    user = "user"
    worker = "worker"
    system = "system"


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)


class Membership(Base):
    __tablename__ = "memberships"

    org_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[Role] = mapped_column(Enum(Role, name="role_enum"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    jd_path: Mapped[str] = mapped_column(Text, nullable=False)
    jd_hash: Mapped[str] = mapped_column(Text, nullable=False)
    jd_blob_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status_enum"), nullable=False
    )
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    queued_inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (UniqueConstraint("org_id", "id", name="uq_runs_org_id"),)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    file_blob_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("org_id", "file_hash", name="uq_candidates_org_file_hash"),
        UniqueConstraint("org_id", "id", name="uq_candidates_org_id"),
    )


class Score(Base):
    __tablename__ = "scores"

    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("run_id", "candidate_id", name="pk_scores"),
        ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["runs.org_id", "runs.id"],
            ondelete="CASCADE",
            name="fk_scores_runs",
        ),
        ForeignKeyConstraint(
            ["org_id", "candidate_id"],
            ["candidates.org_id", "candidates.id"],
            ondelete="CASCADE",
            name="fk_scores_candidates",
        ),
    )


class Shortlist(Base):
    __tablename__ = "shortlists"

    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("run_id", "candidate_id", name="pk_shortlists"),
        ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["runs.org_id", "runs.id"],
            ondelete="CASCADE",
            name="fk_shortlists_runs",
        ),
        ForeignKeyConstraint(
            ["org_id", "candidate_id"],
            ["candidates.org_id", "candidates.id"],
            ondelete="CASCADE",
            name="fk_shortlists_candidates",
        ),
    )


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["runs.org_id", "runs.id"],
            ondelete="CASCADE",
            name="fk_audits_runs",
        ),
    )


class Decision(Base):
    __tablename__ = "decisions"

    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decision: Mapped[DecisionKind] = mapped_column(
        Enum(DecisionKind, name="decision_kind_enum"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("run_id", "candidate_id", name="pk_decisions"),
        ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["runs.org_id", "runs.id"],
            ondelete="CASCADE",
            name="fk_decisions_runs",
        ),
        ForeignKeyConstraint(
            ["org_id", "candidate_id"],
            ["candidates.org_id", "candidates.id"],
            ondelete="CASCADE",
            name="fk_decisions_candidates",
        ),
    )


class CandidateComment(Base):
    __tablename__ = "candidate_comments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["runs.org_id", "runs.id"],
            ondelete="CASCADE",
            name="fk_candidate_comments_runs",
        ),
        ForeignKeyConstraint(
            ["org_id", "candidate_id"],
            ["candidates.org_id", "candidates.id"],
            ondelete="CASCADE",
            name="fk_candidate_comments_candidates",
        ),
    )


class AuditLog(Base):
    """Append-only compliance log of reviewer actions.

    Distinct from the existing ``audits`` table (which holds agent
    outputs). This table records WHO did WHAT to WHICH target — the
    raw material for legal / compliance reviews (NYC AEDT, EU AI Act).

    v1 has no chain-hash; rows are append-only by convention (no
    UPDATE/DELETE codepaths) but not cryptographically tamper-evident.
    A future migration may add ``prev_hash`` + ``hash`` columns.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_kind: Mapped[ActorKind] = mapped_column(
        Enum(ActorKind, name="actor_kind_enum"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
