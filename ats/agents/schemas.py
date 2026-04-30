"""Pydantic schemas for every agent's JSON output.

Acts as a contract: if a model deviates, we coerce common shape mistakes
(list-when-we-wanted-dict, ``{"data": ...}`` wrappers) before validation.
"""

from __future__ import annotations

from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ----------------------------- Needed agents ---------------------------------


class Contact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None


class Education(BaseModel):
    school: str = ""
    degree: str | None = None
    field: str | None = None
    year_end: int | None = None

    model_config = ConfigDict(extra="ignore")


class Experience(BaseModel):
    company: str = ""
    title: str = ""
    start: str | None = None
    end: str | None = None
    bullets: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class ParsedResume(BaseModel):
    contact: Contact = Field(default_factory=Contact)
    summary: str | None = None
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class JDParsed(BaseModel):
    role_family: str = ""
    seniority: str = "mid"
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    min_years: int | None = None

    model_config = ConfigDict(extra="ignore")


class SkillEvidence(BaseModel):
    skill: str
    evidence: str = ""


class MatchResult(BaseModel):
    score: float = 0.0
    must_have_hits: list[SkillEvidence] = Field(default_factory=list)
    must_have_misses: list[str] = Field(default_factory=list)
    nice_to_have_hits: list[SkillEvidence] = Field(default_factory=list)
    years_experience: float = 0.0
    rationale: str = ""

    model_config = ConfigDict(extra="ignore")


class RankEntry(BaseModel):
    candidate_id: int
    rank: int = 0
    decision: Literal["shortlist", "maybe", "reject"] = "reject"


class Ranking(BaseModel):
    ranked: list[RankEntry] = Field(default_factory=list)
    threshold: float = 0.0
    notes: str = ""

    model_config = ConfigDict(extra="ignore")


# --------------------------- Recommended agents ------------------------------


class Hallucination(BaseModel):
    skill: str
    claimed_evidence: str = ""
    reason: str = ""


class VerifierResult(BaseModel):
    verified: list[str] = Field(default_factory=list)
    hallucinated: list[Hallucination] = Field(default_factory=list)
    adjusted_score: float = 0.0

    model_config = ConfigDict(extra="ignore")


class BiasFinding(BaseModel):
    cohort: str = ""
    metric: str = ""
    gap: float = 0.0
    note: str = ""


class BiasReport(BaseModel):
    status: Literal["pass", "warn", "block"] = "pass"
    findings: list[BiasFinding] = Field(default_factory=list)
    recommendation: str = ""

    model_config = ConfigDict(extra="ignore")


class DedupGroup(BaseModel):
    canonical_id: int
    duplicate_ids: list[int] = Field(default_factory=list)
    reason: str = ""


class DedupReport(BaseModel):
    groups: list[DedupGroup] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


# ------------------------------ Optional agents ------------------------------


class TaxonomyResult(BaseModel):
    normalized: dict[str, str | None] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class SummarizerResult(BaseModel):
    brief: str = ""

    model_config = ConfigDict(extra="ignore")


class Gap(BaseModel):
    after: str = ""
    before: str = ""
    months: int = 0


class Overlap(BaseModel):
    a: str = ""
    b: str = ""
    months: int = 0


class RedFlagsResult(BaseModel):
    gaps: list[Gap] = Field(default_factory=list)
    overlaps: list[Overlap] = Field(default_factory=list)
    inconsistencies: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class InterviewQuestion(BaseModel):
    q: str
    probes: list[str] = Field(default_factory=list)
    skill: str = ""


class InterviewResult(BaseModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class OutreachDraft(BaseModel):
    subject: str = ""
    body: str = ""

    model_config = ConfigDict(extra="ignore")


class EnrichmentResult(BaseModel):
    public_repos: int = 0
    followers: int = 0
    top_languages: list[str] = Field(default_factory=list)
    notable_repos: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None

    model_config = ConfigDict(extra="ignore")


# ------------------------------- Registry ------------------------------------

AGENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "parser": ParsedResume,
    "jd_analyzer": JDParsed,
    "matcher": MatchResult,
    "ranker": Ranking,
    "verifier": VerifierResult,
    "bias_auditor": BiasReport,
    "deduper": DedupReport,
    "taxonomy": TaxonomyResult,
    "summarizer": SummarizerResult,
    "red_flags": RedFlagsResult,
    "interview_qs": InterviewResult,
    "outreach": OutreachDraft,
    "enricher": EnrichmentResult,
}


T = TypeVar("T", bound=BaseModel)


_DEGENERATE_AGENTS = {"jd_analyzer", "parser", "matcher"}


def _looks_degenerate(agent: str, model: BaseModel) -> bool:
    """Detect a "valid but useless" response on load-bearing agents.

    The matcher / parser / jd_analyzer outputs all have at least one
    non-empty field in any real run. If the schema validates but every
    such field is empty, treat it as a soft validation failure so the
    invoker can retry.
    """
    if agent == "jd_analyzer":
        d = model.model_dump()
        empty_text = not (d.get("role_family") or "").strip()
        empty_lists = not d.get("must_have") and not d.get("nice_to_have") and not d.get(
            "responsibilities"
        )
        return empty_text and empty_lists
    if agent == "parser":
        d = model.model_dump()
        contact = d.get("contact") or {}
        empty_contact = not (contact.get("name") or contact.get("email"))
        empty_lists = not d.get("experience") and not d.get("skills")
        return empty_contact and empty_lists
    if agent == "matcher":
        d = model.model_dump()
        return (
            float(d.get("score") or 0.0) == 0.0
            and not d.get("must_have_hits")
            and not d.get("must_have_misses")
        )
    return False


def coerce_to_model(agent: str, raw: Any) -> BaseModel:
    """Validate ``raw`` against ``AGENT_SCHEMAS[agent]``, with shape coercion.

    Real models occasionally return a JSON array when the schema expects an
    object, or wrap the object in ``{"data": ...}``. We try the raw value,
    then unwrap common envelope keys, then wrap a bare list under the
    schema's primary list field.

    Two failure modes:

    - Every candidate fails validation → raise CoercionFailedError so the
      caller's retry loop can try again. Previously this silently returned
      a default-constructed model, which let the pipeline proceed against
      an empty parse (matcher would score against an empty JD, etc.).
    - Validation succeeds but the result is "valid but empty" on a
      load-bearing agent (jd_analyzer / parser / matcher) — also raise so
      the retry loop kicks in. This catches the LLM-returned-{} case where
      pydantic happily fills defaults.

    Optional-tier agents (red_flags, summarizer, …) keep the soft-fallback
    behaviour: an empty result there is acceptable and the caller will
    log + skip.
    """
    schema = AGENT_SCHEMAS.get(agent)
    if schema is None:
        raise KeyError(f"No schema registered for agent {agent!r}")

    list_field = _primary_list_field(schema)

    def _expand(value: Any) -> list[Any]:
        out: list[Any] = [value]
        if isinstance(value, list) and list_field is not None:
            out.append({list_field: value})
        return out

    # Prefer envelope-unwrapped variants over the raw value: pydantic with
    # ``extra="ignore"`` and field defaults will happily validate an off-spec
    # dict as a default-filled model, which would mask a useful nested payload.
    candidates: list[Any] = []
    if isinstance(raw, dict):
        for key in ("data", "result", "output", "response", agent):
            inner = raw.get(key)
            if isinstance(inner, (dict, list)):
                candidates.extend(_expand(inner))
    candidates.extend(_expand(raw))

    last_err: ValidationError | None = None
    for c in candidates:
        try:
            model = schema.model_validate(c)
        except ValidationError as exc:
            last_err = exc
            continue
        if agent in _DEGENERATE_AGENTS and _looks_degenerate(agent, model):
            # Try the next candidate; if none survive we fall through to
            # the post-loop fallback below.
            last_err = ValidationError.from_exception_data(  # type: ignore[arg-type]
                title="degenerate-output",
                line_errors=[],
            ) if last_err is None else last_err
            continue
        return model

    raise CoercionFailedError(
        agent=agent,
        raw=raw,
        validation_error=last_err,
    )


class CoercionFailedError(RuntimeError):
    """Raised when no candidate validated, or every candidate degenerated.

    Carries the raw LLM payload so the invoker can persist it for debugging
    and so the retry loop can try a fresh model call.
    """

    def __init__(
        self,
        *,
        agent: str,
        raw: Any,
        validation_error: ValidationError | None,
    ) -> None:
        self.agent = agent
        self.raw = raw
        self.validation_error = validation_error
        super().__init__(
            f"coerce_to_model({agent}) produced no usable output "
            f"(validation_error={validation_error})"
        )


def _primary_list_field(schema: type[BaseModel]) -> str | None:
    """Return the first field on the schema whose annotation is a list type."""
    for name, field in schema.model_fields.items():
        ann = field.annotation
        if ann is None:
            continue
        if getattr(ann, "__origin__", None) is list:
            return name
    return None
