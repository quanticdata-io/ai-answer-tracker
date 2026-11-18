"""Export stored observations as CSV, JSON or JSONL (one row per run x query x engine)."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator
from typing import Any

from .store import Run, Store

#: Export columns, a public contract: adding one is a minor release, renaming or removing one is major.
COLUMNS: tuple[str, ...] = (
    "run_id",
    "tracker",
    "started_at",
    "domain",
    "query",
    "engine",
    "status",
    "cited",
    "mentioned",
    "rank",
    "our_urls",
    "cited_domains",
    "competitors_cited",
    "error",
    "answer_excerpt",
)
FORMATS = ("csv", "json", "jsonl")


def rows(store: Store, runs: Iterable[Run]) -> Iterator[dict[str, Any]]:
    for run in runs:
        for o in store.observations(run.id):
            yield {
                "run_id": run.id,
                "tracker": run.tracker,
                "started_at": run.started_at,
                "domain": run.domain,
                "query": o.query,
                "engine": o.engine,
                "status": o.status,
                "cited": o.cited,
                "mentioned": o.mentioned,
                "rank": o.rank,
                "our_urls": list(o.our_urls),
                "cited_domains": list(o.cited_domains),
                "competitors_cited": list(o.competitors_cited),
                "error": o.error,
                "answer_excerpt": o.answer_excerpt,
            }


def _csv_value(value: Any) -> Any:
    if isinstance(value, list):
        return ";".join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else value


def dumps(data: Iterable[dict[str, Any]], fmt: str) -> str:
    items = list(data)
    if fmt == "json":
        return json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    if fmt == "jsonl":
        return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in items)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(COLUMNS), lineterminator="\n")
        writer.writeheader()
        for r in items:
            writer.writerow({k: _csv_value(r[k]) for k in COLUMNS})
        return buf.getvalue()
    raise ValueError(f"Unknown format {fmt!r}; choose from {', '.join(FORMATS)}")
