"""Command line: ``ai-answer-tracker run | report | export | runs | init``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._version import __version__
from .api import QuanticDataClient, QuanticDataError
from .config import ENGINE_LABELS, MAX_QUERIES_PER_CALL, ConfigError, load_config
from .export import FORMATS, dumps, rows
from .report import Report, build_report, render
from .store import Run, Store
from .tracker import build_requests, planned_engine_calls, run_tracker

DEFAULT_DB = "ai-answers.db"
EXIT_API = 1
EXIT_USAGE = 2
EXIT_LOST = 3

EXAMPLE_CONFIG = """\
# ai-answer-tracker configuration. Every (query x engine) pair that answers is billed:
# see https://quanticdata.io/pricing/ before adding many queries or engines.
name = "example"

# A page of the site you track. Citations are counted for its domain.
url = "https://www.example.com/"

# Name to look for in the answer text ("mentioned" even when not cited). Optional.
brand = "Example"

# Domains always listed in the share of voice. Optional, at most 20.
competitors = ["competitor-one.example", "competitor-two.example"]

# Engines to ask: perplexity, openai, anthropic, aio, copilot, deepseek. Default: all six.
engines = ["openai", "perplexity", "aio"]

# Two-letter country of the search locale. Optional.
country = "us"

# Questions, up to 300 characters each. More than 10 are sent in several calls.
queries = [
  "What is a good tool to convert web pages to Markdown?",
  "How do I track brand mentions in AI answers?",
]

# true also runs the rendered pass, the AI-crawler fetch and 2 retrievability searches (billed).
full_audit = false

# true also searches the brand on five off-site platforms (5 billed searches per call).
offsite = false
"""


def _print(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _err(text: str) -> None:
    sys.stderr.write(text.rstrip("\n") + "\n")


def _write(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
        _err(f"Wrote {output}")
    else:
        _print(text)


def _report_for(store: Store, run: Run) -> Report:
    previous = store.previous_run(run)
    return build_report(
        run,
        store.observations(run.id),
        previous=previous,
        previous_observations=store.observations(previous.id) if previous else (),
    )


def _select_run(store: Store, args: argparse.Namespace) -> Run:
    if args.run is not None:
        run = store.run(args.run)
        if run is None:
            raise ConfigError(f"No run {args.run} in {store.path}")
        return run
    run = store.latest_run(args.tracker)
    if run is None:
        raise ConfigError(
            f"No finished run in {store.path}" + (f" for '{args.tracker}'" if args.tracker else "")
        )
    return run


def _plan_text(bodies: Sequence[Mapping[str, Any]], engine_calls: int) -> str:
    lines = [
        f"{len(bodies)} call(s) to POST /scraper/ai-visibility "
        f"(at most {MAX_QUERIES_PER_CALL} queries per call), up to {engine_calls} billed "
        "(query x engine) pair(s) plus one on-page audit per call. Prices: https://quanticdata.io/pricing/",
        "",
    ]
    for i, body in enumerate(bodies, start=1):
        lines.append(f"Call {i}:")
        lines.append(json.dumps(body, indent=2, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.engines:
        config = config.with_engines([e for e in args.engines.split(",") if e.strip()])
    bodies = build_requests(config)
    if args.dry_run:
        _print(_plan_text(bodies, planned_engine_calls(config)))
        return 0
    with QuanticDataClient(timeout=args.timeout) as client, Store(args.db) as store:

        def progress(i: int, n: int, body: Mapping[str, Any]) -> None:
            _err(f"Call {i}/{n}: {len(body['queries'])} question(s) x {len(body['engines'])} engine(s)...")

        try:
            run_id = run_tracker(client, config, store, on_call=progress)
        except QuanticDataError as exc:
            _err(f"Error: {exc}. The answers received so far are stored as a partial run.")
            return EXIT_API
        run = store.run(run_id)
        assert run is not None
        report = _report_for(store, run)
    _print(render(report))
    if args.fail_on_lost and any(c.direction == "lost" for c in report.changes):
        _err("A citation or mention was lost since the previous run.")
        return EXIT_LOST
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    with Store(args.db) as store:
        report = _report_for(store, _select_run(store, args))
    if args.format == "json":
        text = json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"
    else:
        text = render(report, markdown=args.format == "markdown")
    _write(text, args.output)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    fmt = args.format or (Path(args.output).suffix.lstrip(".").lower() if args.output else "csv")
    if fmt not in FORMATS:
        raise ConfigError(f"Unknown format {fmt!r}; choose from {', '.join(FORMATS)}")
    with Store(args.db) as store:
        selected = [_select_run(store, args)] if args.run is not None else store.runs(args.tracker)
        text = dumps(rows(store, selected), fmt)
    _write(text, args.output)
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    with Store(args.db) as store:
        runs = store.runs(args.tracker)
    if not runs:
        _print(f"No runs in {args.db}.")
        return 0
    for r in runs:
        _print(
            f"{r.id:>4}  {r.started_at}  {r.status:<8}  {r.tracker}  {r.domain}  "
            f"{len(r.queries)} question(s) x {len(r.engines)} engine(s), {r.billed_calls} billed"
        )
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        raise ConfigError(f"{path} exists; use --force to overwrite it")
    path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    _err(f"Wrote {path}. Edit it, then run: ai-answer-tracker run {path} --dry-run")
    return 0


def build_parser() -> argparse.ArgumentParser:
    engines_help = "; ".join(f"{k} = {v}" for k, v in ENGINE_LABELS.items())
    parser = argparse.ArgumentParser(
        prog="ai-answer-tracker",
        description="Track whether AI assistants cite or mention your site, run after run.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def db_opt(p: argparse.ArgumentParser) -> None:
        p.add_argument("--db", default=DEFAULT_DB, help=f"SQLite history file (default {DEFAULT_DB})")

    p = sub.add_parser("run", help="Ask the engines every question and store the answers")
    p.add_argument("config", help="TOML tracker configuration")
    db_opt(p)
    p.add_argument("--engines", help=f"Comma-separated subset that overrides the config. {engines_help}")
    p.add_argument("--dry-run", action="store_true", help="Print the planned API calls and exit, no cost")
    p.add_argument("--fail-on-lost", action="store_true", help="Exit 3 when a citation or mention was lost")
    p.add_argument("--timeout", type=float, default=300.0, help="Seconds per API call (default 300)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="Summary of a stored run with changes since the previous one")
    db_opt(p)
    p.add_argument("--tracker", help="Tracker name (default: the latest run of any tracker)")
    p.add_argument("--run", type=int, help="Run id (default: latest)")
    p.add_argument("-f", "--format", choices=("text", "markdown", "json"), default="text")
    p.add_argument("-o", "--output", help="Write to this file instead of stdout")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("export", help="Every stored answer as CSV, JSON or JSONL")
    db_opt(p)
    p.add_argument("--tracker", help="Only runs of this tracker")
    p.add_argument("--run", type=int, help="Only this run")
    p.add_argument("-f", "--format", choices=FORMATS, help="Default: from the -o extension, else csv")
    p.add_argument("-o", "--output", help="Write to this file instead of stdout")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("runs", help="List stored runs")
    db_opt(p)
    p.add_argument("--tracker", help="Only runs of this tracker")
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("init", help="Write an example configuration")
    p.add_argument("path", nargs="?", default="tracker.toml")
    p.add_argument("--force", action="store_true", help="Overwrite an existing file")
    p.set_defaults(func=cmd_init)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except ConfigError as exc:
        _err(f"Error: {exc}")
        return EXIT_USAGE
    except QuanticDataError as exc:
        _err(f"Error: {exc}")
        return EXIT_API
    return code
