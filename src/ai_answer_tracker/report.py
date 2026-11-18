"""Summaries, share of voice and run-to-run changes, as text, Markdown or JSON."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .models import Observation
from .store import Run


@dataclass
class EngineStats:
    engine: str
    asked: int = 0
    answered: int = 0
    errors: int = 0
    cited: int = 0
    mentioned: int = 0

    @property
    def cited_rate(self) -> float | None:
        return self.cited / self.answered if self.answered else None

    @property
    def mentioned_rate(self) -> float | None:
        return self.mentioned / self.answered if self.answered else None


@dataclass(frozen=True)
class Change:
    query: str
    engine: str
    #: ``cited`` or ``mentioned``.
    signal: str
    #: ``gained`` or ``lost``.
    direction: str


@dataclass
class Report:
    run: Run
    engines: list[EngineStats]
    share_of_voice: list[dict[str, Any]]
    observations: list[Observation]
    previous_run_id: int | None = None
    changes: list[Change] = field(default_factory=list)
    #: (query, engine) pairs that answered in only one of the two runs, so cannot be compared.
    not_comparable: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "run": self.run.as_dict(),
            "engines": [
                {
                    "engine": e.engine,
                    "asked": e.asked,
                    "answered": e.answered,
                    "errors": e.errors,
                    "cited": e.cited,
                    "mentioned": e.mentioned,
                    "cited_rate": e.cited_rate,
                    "mentioned_rate": e.mentioned_rate,
                }
                for e in self.engines
            ],
            "share_of_voice": self.share_of_voice,
            "previous_run_id": self.previous_run_id,
            "changes": [c.__dict__ for c in self.changes],
            "not_comparable": self.not_comparable,
            "observations": [_obs_dict(o) for o in self.observations],
        }


def _obs_dict(o: Observation) -> dict[str, Any]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in o.__dict__.items()}


def engine_stats(run: Run, observations: Sequence[Observation]) -> list[EngineStats]:
    stats = {e: EngineStats(e) for e in run.engines}
    for o in observations:
        s = stats.setdefault(o.engine, EngineStats(o.engine))
        s.asked += 1
        if o.status != "answered":
            s.errors += 1
            continue
        s.answered += 1
        s.cited += int(o.cited)
        s.mentioned += int(o.mentioned)
    return list(stats.values())


def share_of_voice(run: Run, observations: Sequence[Observation], *, top: int = 15) -> list[dict[str, Any]]:
    """Share of answered (query x engine) pairs that cite each domain.

    Computed here from every stored answer, so it covers runs split over several calls.
    The tracked domain and the configured competitors are always listed.
    """
    answered = [o for o in observations if o.status == "answered"]
    counts: Counter[str] = Counter()
    for o in answered:
        domains = {d.lower().removeprefix("www.") for d in o.cited_domains}
        if o.cited:
            domains.add(run.domain)
        counts.update(domains)
    always = {run.domain, *run.competitors}
    keep = {d for d, _ in counts.most_common(top)} | always
    rows = [
        {
            "domain": d,
            "answers": counts.get(d, 0),
            "share": (counts.get(d, 0) / len(answered)) if answered else None,
            "ours": d == run.domain,
            "competitor": d in run.competitors,
        }
        for d in keep
    ]
    rows.sort(key=lambda r: (-counts.get(str(r["domain"]), 0), str(r["domain"])))
    return rows


def compare(previous: Sequence[Observation], current: Sequence[Observation]) -> tuple[list[Change], int]:
    before = {(o.query, o.engine): o for o in previous}
    changes: list[Change] = []
    not_comparable = 0
    for o in current:
        p = before.get((o.query, o.engine))
        if p is None:
            continue
        if (p.status == "answered") != (o.status == "answered"):
            not_comparable += 1
            continue
        if o.status != "answered":
            continue
        for signal in ("cited", "mentioned"):
            was, now = getattr(p, signal), getattr(o, signal)
            if was != now:
                changes.append(Change(o.query, o.engine, signal, "gained" if now else "lost"))
    return changes, not_comparable


def build_report(
    run: Run,
    observations: Sequence[Observation],
    *,
    previous: Run | None = None,
    previous_observations: Sequence[Observation] = (),
) -> Report:
    report = Report(
        run=run,
        engines=engine_stats(run, observations),
        share_of_voice=share_of_voice(run, observations),
        observations=list(observations),
    )
    if previous is not None:
        report.previous_run_id = previous.id
        report.changes, report.not_comparable = compare(previous_observations, observations)
    return report


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def cell(o: Observation | None) -> str:
    """Matrix cell: C = cited (with rank when known), M = mentioned only, - = neither, ! = no answer."""
    if o is None:
        return " "
    if o.status != "answered":
        return "!"
    if o.cited:
        return f"C{o.rank}" if o.rank else "C"
    return "M" if o.mentioned else "-"


def _table(headers: list[str], rows: list[list[str]], *, markdown: bool) -> list[str]:
    if markdown:
        lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
        lines += ["| " + " | ".join(r) + " |" for r in rows]
        return lines
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))] + [fmt.format(*r) for r in rows]
    return [line.rstrip() for line in lines]


def render(report: Report, *, markdown: bool = False, query_width: int = 60) -> str:
    run = report.run
    h = "## " if markdown else ""
    out: list[str] = []
    title = f"Run {run.id} of '{run.tracker}' for {run.domain}"
    out += [("# " if markdown else "") + title, ""]
    out.append(
        f"Started {run.started_at}, status {run.status}, {run.billed_calls} engine call(s) billed"
        + (f", page score {run.page_score}/100" if run.page_score is not None else "")
        + (f", brand '{run.brand}'" if run.brand else "")
        + (f", country {run.country}" if run.country else "")
        + "."
    )
    if run.note:
        out.append(f"Note: {run.note}")
    out.append("")

    out += [f"{h}By engine", ""]
    out += _table(
        ["engine", "asked", "answered", "no answer", "cited", "mentioned"],
        [
            [
                e.engine,
                str(e.asked),
                str(e.answered),
                str(e.errors),
                f"{e.cited} ({_pct(e.cited_rate)})",
                f"{e.mentioned} ({_pct(e.mentioned_rate)})",
            ]
            for e in report.engines
        ],
        markdown=markdown,
    )
    out.append("")

    engines = [e.engine for e in report.engines]
    index = {(o.query, o.engine): o for o in report.observations}
    queries = list(dict.fromkeys([*run.queries, *(o.query for o in report.observations)]))
    out += [f"{h}By question (C cited, M mentioned only, - neither, ! no answer)", ""]
    rows = []
    for q in queries:
        label = q if markdown or len(q) <= query_width else q[: query_width - 3] + "..."
        rows.append([label, *(cell(index.get((q, e))) for e in engines)])
    out += _table(["question", *engines], rows, markdown=markdown)
    out.append("")

    out += [f"{h}Share of voice (answered pairs citing each domain)", ""]
    out += _table(
        ["domain", "answers", "share", ""],
        [
            [
                str(r["domain"]),
                str(r["answers"]),
                _pct(r["share"]),
                "you" if r["ours"] else ("competitor" if r["competitor"] else ""),
            ]
            for r in report.share_of_voice
        ],
        markdown=markdown,
    )
    out.append("")

    out += [f"{h}Changes since the previous run", ""]
    if report.previous_run_id is None:
        out.append("No earlier run of this tracker.")
    elif not report.changes:
        out.append(f"No change since run {report.previous_run_id}.")
    else:
        out.append(f"Compared with run {report.previous_run_id}:")
        for c in report.changes:
            out.append(f"- {c.direction} {c.signal}: [{c.engine}] {c.query}")
    if report.not_comparable:
        out.append(f"{report.not_comparable} pair(s) answered in only one of the two runs were not compared.")

    errors = Counter(o.error for o in report.observations if o.status != "answered" and o.error)
    if errors:
        out += ["", f"{h}No answer", ""]
        out += [f"- {n} x {msg}" for msg, n in errors.most_common()]
    return "\n".join(out).rstrip() + "\n"
