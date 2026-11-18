"""Data shared by the tracker, the store and the reports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    """One (query x engine) answer."""

    query: str
    engine: str
    #: ``answered`` or ``error`` (the engine gave no answer; not counted as "not cited").
    status: str
    cited: bool = False
    mentioned: bool = False
    #: Position of the first citation of the tracked domain, when the engine numbers its sources.
    rank: int | None = None
    our_urls: tuple[str, ...] = ()
    cited_domains: tuple[str, ...] = ()
    competitors_cited: tuple[str, ...] = ()
    error: str | None = None
    answer_excerpt: str | None = None
