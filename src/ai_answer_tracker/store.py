"""SQLite history of tracker runs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import TrackerConfig
from .models import Observation

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tracker      TEXT NOT NULL,
    url          TEXT NOT NULL,
    domain       TEXT NOT NULL,
    brand        TEXT,
    country      TEXT,
    engines      TEXT NOT NULL,
    competitors  TEXT NOT NULL,
    queries      TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,
    billed_calls INTEGER NOT NULL DEFAULT 0,
    page_score   INTEGER,
    note         TEXT
);
CREATE TABLE IF NOT EXISTS observations (
    run_id            INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    query             TEXT NOT NULL,
    engine            TEXT NOT NULL,
    status            TEXT NOT NULL,
    cited             INTEGER NOT NULL,
    mentioned         INTEGER NOT NULL,
    rank              INTEGER,
    our_urls          TEXT NOT NULL,
    cited_domains     TEXT NOT NULL,
    competitors_cited TEXT NOT NULL,
    error             TEXT,
    answer_excerpt    TEXT,
    PRIMARY KEY (run_id, query, engine)
);
CREATE INDEX IF NOT EXISTS runs_by_tracker ON runs (tracker, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Run:
    id: int
    tracker: str
    url: str
    domain: str
    brand: str | None
    country: str | None
    engines: tuple[str, ...]
    competitors: tuple[str, ...]
    queries: tuple[str, ...]
    started_at: str
    finished_at: str | None
    status: str
    billed_calls: int
    page_score: int | None
    note: str | None

    def as_dict(self) -> dict[str, Any]:
        return {k: list(v) if isinstance(v, tuple) else v for k, v in self.__dict__.items()}


class Store:
    def __init__(self, path: str | Path, *, clock: Callable[[], str] = _now) -> None:
        self.path = str(path)
        self._clock = clock
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes ------------------------------------------------------------

    def start_run(self, config: TrackerConfig) -> int:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO runs (tracker, url, domain, brand, country, engines, competitors, queries,"
                " started_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')",
                (
                    config.name,
                    config.url,
                    config.domain,
                    config.brand,
                    config.country,
                    json.dumps(list(config.engines)),
                    json.dumps(list(config.competitors)),
                    json.dumps(list(config.queries)),
                    self._clock(),
                ),
            )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def add_observations(self, run_id: int, observations: Iterable[Observation]) -> None:
        with self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        o.query,
                        o.engine,
                        o.status,
                        int(o.cited),
                        int(o.mentioned),
                        o.rank,
                        json.dumps(list(o.our_urls)),
                        json.dumps(list(o.cited_domains)),
                        json.dumps(list(o.competitors_cited)),
                        o.error,
                        o.answer_excerpt,
                    )
                    for o in observations
                ],
            )

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        billed_calls: int,
        page_score: int | None = None,
        note: str | None = None,
    ) -> None:
        with self._db:
            self._db.execute(
                "UPDATE runs SET finished_at = ?, status = ?, billed_calls = ?, page_score = ?, note = ?"
                " WHERE id = ?",
                (self._clock(), status, billed_calls, page_score, note, run_id),
            )

    # -- reads -------------------------------------------------------------

    @staticmethod
    def _run(row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"],
            tracker=row["tracker"],
            url=row["url"],
            domain=row["domain"],
            brand=row["brand"],
            country=row["country"],
            engines=tuple(json.loads(row["engines"])),
            competitors=tuple(json.loads(row["competitors"])),
            queries=tuple(json.loads(row["queries"])),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=row["status"],
            billed_calls=row["billed_calls"],
            page_score=row["page_score"],
            note=row["note"],
        )

    def runs(self, tracker: str | None = None) -> list[Run]:
        if tracker is None:
            rows = self._db.execute("SELECT * FROM runs ORDER BY id").fetchall()
        else:
            rows = self._db.execute("SELECT * FROM runs WHERE tracker = ? ORDER BY id", (tracker,)).fetchall()
        return [self._run(r) for r in rows]

    def run(self, run_id: int) -> Run | None:
        row = self._db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def latest_run(self, tracker: str | None = None) -> Run | None:
        sql = "SELECT * FROM runs WHERE status IN ('done', 'partial')"
        params: tuple[Any, ...] = ()
        if tracker is not None:
            sql += " AND tracker = ?"
            params = (tracker,)
        row = self._db.execute(sql + " ORDER BY id DESC LIMIT 1", params).fetchone()
        return self._run(row) if row else None

    def previous_run(self, run: Run) -> Run | None:
        row = self._db.execute(
            "SELECT * FROM runs WHERE tracker = ? AND id < ? AND status IN ('done', 'partial')"
            " ORDER BY id DESC LIMIT 1",
            (run.tracker, run.id),
        ).fetchone()
        return self._run(row) if row else None

    def observations(self, run_id: int) -> list[Observation]:
        rows = self._db.execute(
            "SELECT * FROM observations WHERE run_id = ? ORDER BY rowid", (run_id,)
        ).fetchall()
        return [
            Observation(
                query=r["query"],
                engine=r["engine"],
                status=r["status"],
                cited=bool(r["cited"]),
                mentioned=bool(r["mentioned"]),
                rank=r["rank"],
                our_urls=tuple(json.loads(r["our_urls"])),
                cited_domains=tuple(json.loads(r["cited_domains"])),
                competitors_cited=tuple(json.loads(r["competitors_cited"])),
                error=r["error"],
                answer_excerpt=r["answer_excerpt"],
            )
            for r in rows
        ]
