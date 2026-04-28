"""ATS command-line interface."""

from __future__ import annotations

from pathlib import Path

import anyio
import typer
from rich.console import Console
from rich.table import Table

from ats import db
from ats.config import get_settings
from ats.logging import configure as configure_logging
from ats.orchestrator import run_pipeline

app = typer.Typer(help="AI-powered resume screening (ATS).")
console = Console()


def _setup_logging(level: str, json_format: bool) -> None:
    configure_logging(level=level, json_format=json_format)


@app.callback()
def _root(
    log_level: str = typer.Option(
        "INFO", "--log-level", help="DEBUG | INFO | WARNING | ERROR"
    ),
    log_json: bool = typer.Option(
        False, "--log-json", help="Emit logs as JSON to stderr."
    ),
) -> None:
    _setup_logging(log_level, log_json)


@app.command()
def init() -> None:
    """Initialize the SQLite database and inbox directory."""
    s = get_settings()
    db.init_db(s.db_path)
    s.inbox_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]ok[/]  db={s.db_path}  inbox={s.inbox_dir}")


@app.command()
def screen(
    jd: Path = typer.Option(
        ..., exists=True, readable=True, help="Path to JD text file."
    ),
    resumes: Path = typer.Option(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directory of resumes.",
    ),
    top: int = typer.Option(5, help="How many to shortlist."),
    skip_optional: bool = typer.Option(
        False, "--skip-optional", help="Skip the 6 optional agents."
    ),
    max_cost_usd: float | None = typer.Option(
        None,
        "--max-cost-usd",
        help="Abort the run if cumulative spend exceeds this cap.",
    ),
) -> None:
    """Run the full screening pipeline."""
    s = get_settings()
    if max_cost_usd is not None:
        s.max_cost_usd = max_cost_usd
    summary = anyio.run(run_pipeline, s, jd, resumes, top, skip_optional)
    console.print_json(data=summary)


@app.command()
def report(
    run: int = typer.Option(..., help="Run id."),
    cost: bool = typer.Option(False, "--cost", help="Show token usage and USD cost."),
) -> None:
    """Print a summary of a previous run."""
    s = get_settings()
    scores = db.get_run_scores(s.db_path, run)
    audits = db.get_audits(s.db_path, run)

    t = Table(title=f"Run {run} — Candidates")
    t.add_column("ID")
    t.add_column("Name")
    t.add_column("Email")
    t.add_column("Score", justify="right")
    t.add_column("Rationale", overflow="fold")
    for row in scores:
        t.add_row(
            str(row["candidate_id"]),
            str(row.get("name") or ""),
            str(row.get("email") or ""),
            f"{row['score']:.2f}",
            (row.get("rationale") or "")[:200],
        )
    console.print(t)

    bias = next((a for a in audits if a["kind"] == "bias"), None)
    if bias:
        console.print("[bold]Bias audit:[/]")
        console.print_json(data=bias["payload"])

    if cost:
        run_row = db.get_run(s.db_path, run)
        usage = (run_row or {}).get("usage", {})
        if usage:
            console.print("[bold]Cost:[/]")
            console.print_json(data=usage)
        else:
            console.print("[yellow]No usage data recorded for this run.[/]")


@app.command()
def outreach(
    run: int = typer.Option(...),
    decision: str = typer.Option(
        "shortlist", help="shortlist | reject (filter applied)."
    ),
) -> None:
    """Print outreach drafts for a run."""
    s = get_settings()
    audits = db.get_audits(s.db_path, run)
    drafts_audit = next((a for a in audits if a["kind"] == "outreach"), None)
    if not drafts_audit:
        console.print("[yellow]No outreach drafts found for this run.[/]")
        raise typer.Exit(0)
    drafts = drafts_audit["payload"].get("drafts", [])
    if decision != "shortlist":
        console.print(
            "[yellow]Only 'shortlist' drafts are produced; "
            "no rejection emails are stored.[/]"
        )
        raise typer.Exit(0)
    console.print_json(data={"drafts": drafts})


def main() -> None:  # entrypoint for `python -m ats.cli`
    app()


if __name__ == "__main__":
    main()
