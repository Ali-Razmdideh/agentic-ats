from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool


def extract_text_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        import docx  # python-docx

        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)
    raise ValueError(f"Unsupported file type: {suffix}")


@tool(
    "read_resume",
    "Extract plain text from a resume file (.pdf, .docx, .txt, .md).",
    {"path": str},
)
async def read_resume(args: dict[str, Any]) -> dict[str, Any]:
    path = Path(args["path"])
    if not path.exists():
        return {
            "content": [{"type": "text", "text": f"ERROR: file not found: {path}"}],
            "isError": True,
        }
    try:
        text = extract_text_from_path(path)
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": f"ERROR: {exc}"}],
            "isError": True,
        }
    return {"content": [{"type": "text", "text": text}]}
