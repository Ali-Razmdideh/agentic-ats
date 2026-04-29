"""ATS command-line interface."""

from __future__ import annotations

from pathlib import Path

import anyio
import typer
from rich.console import Console
from rich.table import Table

from ats.config import Settings, get_settings
from ats.logging import configure as configure_logging
from ats.orchestrator import run_pipeline
from ats.storage import BlobStore, make_engine, make_sessionmaker, uow
from ats.storage.uow import _build_bundle

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


async def _resolve_org_id(settings: Settings, slug: str) -> int:
    engine = make_engine(settings)
    sm = make_sessionmaker(engine)
    try:
        async with sm() as session:
            bundle = _build_bundle(session, org_id=0)
            org = await bundle.orgs.get_by_slug(slug)
            if org is None:
                raise typer.BadParameter(
                    f"Org '{slug}' not found. Run `ats init` first."
                )
            return int(org.id)
    finally:
        await engine.dispose()


async def _init_async(settings: Settings) -> None:
    """Create schema (idempotent), seed the default org, ensure the bucket."""
    from sqlalchemy import select

    from ats.storage.models import Base, Org

    engine = make_engine(settings)
    sm = make_sessionmaker(engine)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS citext")
            await conn.run_sync(Base.metadata.create_all)
        async with sm() as session:
            existing = await session.execute(
                select(Org).where(Org.slug == settings.default_org_slug)
            )
            if existing.scalar_one_or_none() is None:
                session.add(Org(slug=settings.default_org_slug, name="System (CLI)"))
                await session.commit()
    finally:
        await engine.dispose()

    blob = BlobStore(settings)
    await blob.ensure_bucket()


@app.command()
def init() -> None:
    """Create Postgres schema, seed default org, create MinIO bucket + inbox."""
    s = get_settings()
    s.inbox_dir.mkdir(parents=True, exist_ok=True)
    anyio.run(_init_async, s)
    console.print(
        f"[green]ok[/]  pg={s.pg_dsn}  bucket={s.minio_bucket}  inbox={s.inbox_dir}"
    )


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
    org: str = typer.Option(
        None, "--org", help="Org slug (default: ATS_DEFAULT_ORG_SLUG = 'system')."
    ),
) -> None:
    """Run the full screening pipeline."""
    s = get_settings()
    if max_cost_usd is not None:
        s.max_cost_usd = max_cost_usd

    async def _go() -> dict[str, object]:
        return await run_pipeline(s, jd, resumes, top, skip_optional, org_slug=org)

    summary = anyio.run(_go)
    console.print_json(data=summary)


async def _report_async(settings: Settings, slug: str, run_id: int, cost: bool) -> None:
    org_id = await _resolve_org_id(settings, slug)
    engine = make_engine(settings)
    sm = make_sessionmaker(engine)
    try:
        async with uow(sm, org_id) as repos:
            scores = await repos.scores.list_for_run(run_id)
            audits = await repos.audits.list_for_run(run_id)
            run_row = await repos.runs.get(run_id)
    finally:
        await engine.dispose()

    t = Table(title=f"Run {run_id} — Candidates")
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
        usage = (run_row or {}).get("usage") or {}
        if usage:
            console.print("[bold]Cost:[/]")
            console.print_json(data=usage)
        else:
            console.print("[yellow]No usage data recorded for this run.[/]")


@app.command()
def report(
    run: int = typer.Option(..., help="Run id."),
    cost: bool = typer.Option(False, "--cost", help="Show token usage and USD cost."),
    org: str = typer.Option(None, "--org"),
) -> None:
    """Print a summary of a previous run."""
    s = get_settings()
    slug = org or s.default_org_slug
    anyio.run(_report_async, s, slug, run, cost)


async def _outreach_async(
    settings: Settings, slug: str, run_id: int
) -> dict[str, object]:
    org_id = await _resolve_org_id(settings, slug)
    engine = make_engine(settings)
    sm = make_sessionmaker(engine)
    try:
        async with uow(sm, org_id) as repos:
            audits = await repos.audits.list_for_run(run_id)
    finally:
        await engine.dispose()
    drafts_audit = next((a for a in audits if a["kind"] == "outreach"), None)
    if not drafts_audit:
        return {}
    payload: dict[str, object] = drafts_audit["payload"]
    return payload


@app.command()
def outreach(
    run: int = typer.Option(...),
    decision: str = typer.Option(
        "shortlist", help="shortlist | reject (filter applied)."
    ),
    org: str = typer.Option(None, "--org"),
) -> None:
    """Print outreach drafts for a run."""
    s = get_settings()
    slug = org or s.default_org_slug
    payload = anyio.run(_outreach_async, s, slug, run)
    if not payload:
        console.print("[yellow]No outreach drafts found for this run.[/]")
        raise typer.Exit(0)
    if decision != "shortlist":
        console.print(
            "[yellow]Only 'shortlist' drafts are produced; "
            "no rejection emails are stored.[/]"
        )
        raise typer.Exit(0)
    console.print_json(data={"drafts": payload.get("drafts", [])})


def main() -> None:
    app()


if __name__ == "__main__":
    main()
