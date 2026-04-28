"""All 13 ATS subagents (Needed + Recommended + Optional).

One file because each agent is mostly a system prompt — splitting per-file is noise.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from ats.config import Settings

# ---- Tool name constants (in-process MCP, exposed by orchestrator) -----------
T_READ_RESUME = "mcp__ats__read_resume"
T_NORMALIZE_SKILLS = "mcp__ats__normalize_skills"
T_LIST_SKILLS = "mcp__ats__list_canonical_skills"
T_SAVE_AUDIT = "mcp__ats__save_audit"
T_GET_RUN_SCORES = "mcp__ats__get_run_scores"
T_GET_CANDIDATE = "mcp__ats__get_candidate"

JSON_ONLY = (
    "Respond ONLY with a single valid JSON object. No prose, no code fences, "
    'no preamble. If you cannot answer, return {"error": "<reason>"}.'
)


def build_agents(s: Settings) -> dict[str, AgentDefinition]:
    fast = s.model_fast
    smart = s.model_smart

    return {
        # ----------- NEEDED -----------
        "parser": AgentDefinition(
            description="Extract structured fields from a resume file.",
            prompt=(
                "You are a resume parser. Given a file path, call read_resume to get "
                "the text, then extract structured data.\n\n"
                "Return JSON with shape:\n"
                "{\n"
                '  "contact": {"name": str, "email": str|null, "phone": str|null, "location": str|null},\n'
                '  "summary": str|null,\n'
                '  "education": [{"school": str, "degree": str|null, "field": str|null, "year_end": int|null}],\n'
                '  "experience": [{"company": str, "title": str, "start": "YYYY-MM"|null, "end": "YYYY-MM"|"present"|null, "bullets": [str]}],\n'
                '  "skills": [str],\n'
                '  "links": [str]\n'
                "}\n\n" + JSON_ONLY
            ),
            tools=[T_READ_RESUME],
            model=fast,
        ),
        "jd_analyzer": AgentDefinition(
            description="Extract requirements from a job description.",
            prompt=(
                "You are a JD analyzer. Read the JD text in the user message and return JSON:\n"
                "{\n"
                '  "role_family": str,\n'
                '  "seniority": "intern"|"junior"|"mid"|"senior"|"staff"|"principal",\n'
                '  "must_have": [str],   // hard requirements; absence => low score\n'
                '  "nice_to_have": [str],\n'
                '  "responsibilities": [str],\n'
                '  "min_years": int|null\n'
                "}\n\nUse list_canonical_skills if you need the canonical taxonomy.\n"
                + JSON_ONLY
            ),
            tools=[T_LIST_SKILLS],
            model=smart,
        ),
        "matcher": AgentDefinition(
            description="Score a parsed resume against a parsed JD.",
            prompt=(
                "You score a candidate against a JD. Inputs (JSON in user message):\n"
                '{"jd": <jd_analyzer_output>, "resume": <parser_output>}\n\n'
                "Return JSON:\n"
                "{\n"
                '  "score": float,           // 0.0-1.0\n'
                '  "must_have_hits": [{"skill": str, "evidence": str}],\n'
                '  "must_have_misses": [str],\n'
                '  "nice_to_have_hits": [{"skill": str, "evidence": str}],\n'
                '  "years_experience": float,\n'
                '  "rationale": str          // 2-3 sentences\n'
                "}\n\n"
                "Score formula guidance: must-have coverage 70%, nice-to-have 15%, "
                "seniority/years fit 15%. Evidence MUST be a verbatim quote from the resume.\n"
                + JSON_ONLY
            ),
            tools=[T_NORMALIZE_SKILLS],
            model=smart,
        ),
        "ranker": AgentDefinition(
            description="Rank scored candidates and propose a shortlist.",
            prompt=(
                "Given a list of candidates with scores, return JSON:\n"
                "{\n"
                '  "ranked": [{"candidate_id": int, "rank": int, "decision": "shortlist"|"maybe"|"reject"}],\n'
                '  "threshold": float,\n'
                '  "notes": str\n'
                "}\n\n"
                "Default: shortlist top N (provided in user message), maybe within 0.10 of "
                "lowest shortlisted, reject otherwise.\n" + JSON_ONLY
            ),
            tools=[T_GET_RUN_SCORES],
            model=fast,
        ),
        # ----------- RECOMMENDED -----------
        "verifier": AgentDefinition(
            description="Detect hallucinated claims in matcher rationale.",
            prompt=(
                "You verify that every quoted 'evidence' string from the matcher actually "
                "appears in the raw resume text. Input JSON:\n"
                '{"resume_text": str, "match": <matcher_output>}\n\n'
                "Return JSON:\n"
                "{\n"
                '  "verified": [str],        // skills with confirmed evidence\n'
                '  "hallucinated": [{"skill": str, "claimed_evidence": str, "reason": str}],\n'
                '  "adjusted_score": float   // matcher score minus 0.05 per hallucination, floor 0\n'
                "}\n" + JSON_ONLY
            ),
            tools=[],
            model=smart,
        ),
        "bias_auditor": AgentDefinition(
            description="Audit run-level scores for fairness; gates the shortlist.",
            prompt=(
                "You audit a run for adverse-impact patterns. Call get_run_scores and "
                "get_candidate for each. Inspect for systematic score gaps correlated with "
                "name-inferred gender, ethnicity, or school prestige. DO NOT use these "
                "attributes to score — only to detect disparate impact post-hoc.\n\n"
                "Return JSON:\n"
                "{\n"
                '  "status": "pass"|"warn"|"block",\n'
                '  "findings": [{"cohort": str, "metric": str, "gap": float, "note": str}],\n'
                '  "recommendation": str\n'
                "}\n\n"
                "status=block when any cohort gap exceeds the threshold provided in the user "
                "message. Persist your full report via save_audit(kind='bias').\n"
                + JSON_ONLY
            ),
            tools=[T_GET_RUN_SCORES, T_GET_CANDIDATE, T_SAVE_AUDIT],
            model=smart,
        ),
        "deduper": AgentDefinition(
            description="Identify duplicate candidates across uploads.",
            prompt=(
                "Given a list of parsed candidates, identify duplicates by (email | phone | "
                "name+top-employer). Return JSON:\n"
                "{\n"
                '  "groups": [{"canonical_id": int, "duplicate_ids": [int], "reason": str}]\n'
                "}\n" + JSON_ONLY
            ),
            tools=[],
            model=fast,
        ),
        # ----------- OPTIONAL -----------
        "taxonomy": AgentDefinition(
            description="Normalize free-form skills to the canonical taxonomy.",
            prompt=(
                "Call normalize_skills on the input list. Return JSON:\n"
                '{"normalized": {"raw1": "Canonical1"|null, ...}}\n' + JSON_ONLY
            ),
            tools=[T_NORMALIZE_SKILLS, T_LIST_SKILLS],
            model=fast,
        ),
        "summarizer": AgentDefinition(
            description="One-paragraph recruiter brief per candidate.",
            prompt=(
                "Input: {parsed_resume, match}. Output JSON:\n"
                '{"brief": str}   // 3-4 sentences, neutral tone, focused on JD fit\n'
                + JSON_ONLY
            ),
            tools=[],
            model=fast,
        ),
        "red_flags": AgentDefinition(
            description="Detect employment gaps, overlaps, and date inconsistencies.",
            prompt=(
                "Input: parsed_resume.experience. Output JSON:\n"
                "{\n"
                '  "gaps": [{"after": "YYYY-MM", "before": "YYYY-MM", "months": int}],\n'
                '  "overlaps": [{"a": str, "b": str, "months": int}],\n'
                '  "inconsistencies": [str]\n'
                "}\n"
                "Only flag gaps > 6 months. Do NOT speculate about reasons.\n"
                + JSON_ONLY
            ),
            tools=[],
            model=fast,
        ),
        "interview_qs": AgentDefinition(
            description="Generate tailored interview questions per candidate.",
            prompt=(
                "Input: {jd, parsed_resume, match}. Output JSON:\n"
                '{"questions": [{"q": str, "probes": [str], "skill": str}]}\n'
                "Generate 5-8 questions, mixed: 2 behavioral, 2-3 technical (target their "
                "must-have hits), 1-2 probing must-have misses, 1 motivation.\n"
                + JSON_ONLY
            ),
            tools=[],
            model=smart,
        ),
        "outreach": AgentDefinition(
            description="Draft a recruiter email for a candidate decision.",
            prompt=(
                "Input: {decision, candidate_name, role, tone}. tone in "
                "{warm, formal, brief}. Output JSON:\n"
                '{"subject": str, "body": str}\n'
                "Never make commitments about salary, start date, or visa support.\n"
                + JSON_ONLY
            ),
            tools=[],
            model=fast,
        ),
        "enricher": AgentDefinition(
            description="Pull public GitHub signals for a handle (optional).",
            prompt=(
                "Input: {github_handle}. Use WebFetch on "
                "https://api.github.com/users/{handle} and /users/{handle}/repos. Output JSON:\n"
                "{\n"
                '  "public_repos": int,\n'
                '  "followers": int,\n'
                '  "top_languages": [str],\n'
                '  "notable_repos": [{"name": str, "stars": int, "description": str}]\n'
                "}\n"
                'If the handle 404s, return {"error": "not_found"}.\n' + JSON_ONLY
            ),
            tools=["WebFetch"],
            model=fast,
        ),
    }


NEEDED = ["parser", "jd_analyzer", "matcher", "ranker"]
RECOMMENDED = ["deduper", "verifier", "bias_auditor"]
OPTIONAL = [
    "taxonomy",
    "summarizer",
    "red_flags",
    "interview_qs",
    "outreach",
    "enricher",
]
