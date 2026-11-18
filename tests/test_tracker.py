from __future__ import annotations

from typing import Any

import httpx
import pytest

from ai_answer_tracker import (
    PaymentRequiredError,
    QuanticDataClient,
    Store,
    TrackerConfig,
    build_requests,
    observations_from_payload,
    parse_config,
    planned_engine_calls,
    run_tracker,
)
from ai_answer_tracker.tracker import EXCERPT_CHARS, observation_from_row

from .mock_api import MockState, build_payload


def test_requests_carry_config_and_cheap_audit_flags(config: TrackerConfig) -> None:
    (body,) = build_requests(config)
    assert body == {
        "url": "https://www.example.com/",
        "queries": list(config.queries),
        "engines": ["openai", "perplexity", "aio"],
        "brand": "Example",
        "competitors": ["competitor-one.example"],
        "country": "us",
        "no_render": True,
        "no_bot_fetch": True,
        "no_retrieval": True,
    }


def test_full_audit_and_offsite() -> None:
    cfg = parse_config({"url": "https://example.com/", "queries": ["q"], "full_audit": True, "offsite": True})
    (body,) = build_requests(cfg)
    assert "no_render" not in body
    assert body["offsite"] is True
    assert "brand" not in body
    assert "competitors" not in body


def test_more_than_ten_queries_are_split() -> None:
    cfg = parse_config({"url": "https://example.com/", "queries": [f"q{i}" for i in range(23)]})
    bodies = build_requests(cfg)
    assert [len(b["queries"]) for b in bodies] == [10, 10, 3]
    assert planned_engine_calls(cfg) == 23 * 6


def test_observations_from_recorded_answer(recorded: dict[str, Any]) -> None:
    obs = observations_from_payload(recorded["payload"])
    assert len(obs) == 6
    first = obs[0]
    assert (first.engine, first.status, first.cited, first.mentioned, first.rank) == (
        "openai",
        "answered",
        True,
        True,
        2,
    )
    assert first.our_urls == ("https://www.example.com/markdown/",)
    assert first.competitors_cited == ("competitor-one.example",)
    assert "example.com" in first.cited_domains
    mention_only = obs[1]
    assert (mention_only.cited, mention_only.mentioned) == (False, True)
    unanswered = obs[2]
    assert unanswered.status == "error"
    assert unanswered.error == "no AI Overview for this query"
    assert not unanswered.cited


def test_observation_edge_cases() -> None:
    assert observation_from_row({"engine": "openai"}) is None
    row = {"query": "q", "engine": "openai", "cited": "yes", "rank": True, "answerText": "x" * 2000}
    obs = observation_from_row(row)
    assert obs is not None
    assert obs.cited is False
    assert obs.rank is None
    assert obs.answer_excerpt is not None
    assert len(obs.answer_excerpt) == EXCERPT_CHARS
    assert observations_from_payload({}) == []
    assert observations_from_payload({"citations": {"rows": "bad"}}) == []


def test_run_stores_every_pair(
    client: QuanticDataClient, store: Store, config: TrackerConfig, state: MockState
) -> None:
    run_id = run_tracker(client, config, store)
    run = store.run(run_id)
    assert run is not None
    assert run.status == "done"
    assert run.page_score == 84
    assert run.billed_calls == 4  # the mock leaves aio unanswered, which is not billed
    obs = store.observations(run_id)
    assert len(obs) == 6
    assert {o.engine for o in obs if o.status == "error"} == {"aio"}
    assert len(state.bodies) == 1


def test_run_split_over_calls(client: QuanticDataClient, store: Store, state: MockState) -> None:
    cfg = parse_config(
        {
            "url": "https://example.com/",
            "queries": [f"question {i}" for i in range(12)],
            "engines": ["openai"],
        }
    )
    progress: list[tuple[int, int]] = []
    run_id = run_tracker(client, cfg, store, on_call=lambda i, n, body: progress.append((i, n)))
    assert progress == [(1, 2), (2, 2)]
    assert len(store.observations(run_id)) == 12
    assert [len(b["queries"]) for b in state.bodies] == [10, 2]


def test_failed_call_keeps_partial_run(store: Store) -> None:
    state = MockState()
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 2:
            return httpx.Response(402, json={"type": "error", "message": "INSUFFICIENT_FUNDS", "payload": {}})
        import json

        body = json.loads(request.content)
        return httpx.Response(200, json={"type": "response", "payload": build_payload(body, state)})

    cfg = parse_config(
        {"url": "https://example.com/", "queries": [f"q{i}" for i in range(15)], "engines": ["openai"]}
    )
    with (
        QuanticDataClient("qd_test_123", transport=httpx.MockTransport(handler)) as client,
        pytest.raises(PaymentRequiredError),
    ):
        run_tracker(client, cfg, store)
    (run,) = store.runs()
    assert run.status == "partial"
    assert run.note == "INSUFFICIENT_FUNDS"
    assert len(store.observations(run.id)) == 10
