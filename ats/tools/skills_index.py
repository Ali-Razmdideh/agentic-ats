from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool
from rapidfuzz import process

CANONICAL_SKILLS: list[str] = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Go",
    "Rust",
    "Java",
    "C++",
    "C#",
    "Ruby",
    "PHP",
    "Kotlin",
    "Swift",
    "Scala",
    "React",
    "Vue",
    "Angular",
    "Next.js",
    "Svelte",
    "Node.js",
    "Django",
    "Flask",
    "FastAPI",
    "Spring Boot",
    "Express",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "ClickHouse",
    "Kafka",
    "RabbitMQ",
    "GraphQL",
    "gRPC",
    "REST",
    "AWS",
    "GCP",
    "Azure",
    "Docker",
    "Kubernetes",
    "Terraform",
    "Ansible",
    "CI/CD",
    "GitLab CI",
    "GitHub Actions",
    "Jenkins",
    "Machine Learning",
    "Deep Learning",
    "PyTorch",
    "TensorFlow",
    "scikit-learn",
    "NLP",
    "Computer Vision",
    "LLM",
    "RAG",
    "Linux",
    "Git",
    "Bash",
]


def normalize_skill(raw: str, threshold: int = 80) -> str | None:
    if not raw:
        return None
    match = process.extractOne(raw, CANONICAL_SKILLS, score_cutoff=threshold)
    if match is None:
        return None
    return str(match[0])


@tool(
    "normalize_skills",
    "Map raw skill strings to canonical skill IDs. Returns a dict raw->canonical (or null).",
    {"skills": list},
)
async def normalize_skills(args: dict[str, Any]) -> dict[str, Any]:
    raw_list = args.get("skills") or []
    mapping = {raw: normalize_skill(str(raw)) for raw in raw_list}
    import json

    return {"content": [{"type": "text", "text": json.dumps(mapping)}]}


@tool(
    "list_canonical_skills",
    "Return the canonical skill taxonomy used by the ATS.",
    {},
)
async def list_canonical_skills(args: dict[str, Any]) -> dict[str, Any]:
    import json

    return {"content": [{"type": "text", "text": json.dumps(CANONICAL_SKILLS)}]}
