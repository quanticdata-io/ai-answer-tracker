"""Plans the API calls for a tracker and turns their answers into observations."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from .api import QuanticDataClient, QuanticDataError
from .config import MAX_QUERIES_PER_CALL, TrackerConfig
from .models import Observation
from .store import Store

EXCERPT_CHARS = 500


def chunks(items: Sequence[str], size: int = MAX_QUERIES_PER_CALL) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def build_requests(config: TrackerConfig) -> list[dict[str, Any]]:
    """One request body per group of at most 10 queries (the documented per-call cap)."""
    bodies: list[dict[str, Any]] = []
    for group in chunks(config.queries):
        body: dict[str, Any] = {"url": config.url, "queries": group, "engines": list(config.engines)}
        if config.brand:
            body["brand"] = config.brand
        if config.competitors:
            body["competitors"] = list(config.competitors)
        if config.country:
            body["country"] = config.country
        if not config.full_audit:
            # The on-page audit always runs; these flags skip its optional, separately billed parts.
            body.update(no_render=True, no_bot_fetch=True, no_retrieval=True)
        if config.offsite:
            body["offsite"] = True
        bodies.append(body)
    return bodies


def planned_engine_calls(config: TrackerConfig) -> int:
    """Upper bound of billed (query x engine) pairs; pairs that do not answer are not billed."""
    return len(config.queries) * len(config.engines)


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v) for v in value if isinstance(v, str) and v)


def observation_from_row(row: Mapping[str, Any]) -> Observation | None:
    query, engine = row.get("query"), row.get("engine")
    if not isinstance(query, str) or not isinstance(engine, str):
        return None
    error = row.get("error")
    if isinstance(error, str) and error.strip():
        return Observation(query=query, engine=engine, status="error", error=error.strip())
    rank = row.get("rank")
    excerpt = row.get("answerExcerpt") or row.get("answerText")
    return Observation(
        query=query,
        engine=engine,
        status="answered",
        cited=row.get("cited") is True,
        mentioned=row.get("mentioned") is True,
        rank=rank if isinstance(rank, int) and not isinstance(rank, bool) else None,
        our_urls=_strings(row.get("ourUrls")),
        cited_domains=_strings(row.get("allDomains")),
        competitors_cited=_strings(row.get("competitors")),
        answer_excerpt=excerpt[:EXCERPT_CHARS] if isinstance(excerpt, str) and excerpt else None,
    )


def observations_from_payload(payload: Mapping[str, Any]) -> list[Observation]:
    citations = payload.get("citations")
    if not isinstance(citations, Mapping):
        return []
    rows = citations.get("rows")
    out: list[Observation] = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, Mapping):
            obs = observation_from_row(row)
            if obs is not None:
                out.append(obs)
    return out


def _overall_score(payload: Mapping[str, Any]) -> int | None:
    score = payload.get("score")
    overall = score.get("overall") if isinstance(score, Mapping) else None
    return overall if isinstance(overall, int) and not isinstance(overall, bool) else None


def _billed_calls(payload: Mapping[str, Any]) -> int:
    billing = payload.get("billing")
    value = billing.get("citation_calls_billed") if isinstance(billing, Mapping) else None
    return value if isinstance(value, int) else 0


def run_tracker(
    client: QuanticDataClient,
    config: TrackerConfig,
    store: Store,
    *,
    on_call: Callable[[int, int, Mapping[str, Any]], None] | None = None,
) -> int:
    """Runs every planned call, stores the observations and returns the run id.

    If a call fails (402, 429, network), the observations already received are
    kept and the run is marked ``partial`` before the error is raised again.
    """
    bodies = build_requests(config)
    run_id = store.start_run(config)
    billed = 0
    score: int | None = None
    try:
        for i, body in enumerate(bodies, start=1):
            if on_call:
                on_call(i, len(bodies), body)
            payload = client.ai_visibility(body)
            store.add_observations(run_id, observations_from_payload(payload))
            billed += _billed_calls(payload)
            score = _overall_score(payload) if score is None else score
    except QuanticDataError as exc:
        store.finish_run(run_id, status="partial", billed_calls=billed, page_score=score, note=str(exc))
        raise
    store.finish_run(run_id, status="done", billed_calls=billed, page_score=score)
    return run_id
