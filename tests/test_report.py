from __future__ import annotations

from typing import Any

from ai_answer_tracker import (
    Observation,
    Store,
    TrackerConfig,
    build_report,
    observations_from_payload,
    render,
)
from ai_answer_tracker.report import cell, compare


def stored(store: Store, config: TrackerConfig, observations: list[Observation]) -> int:
    run_id = store.start_run(config)
    store.add_observations(run_id, observations)
    store.finish_run(run_id, status="done", billed_calls=len(observations), page_score=80)
    return run_id


def test_engine_stats_exclude_unanswered(
    store: Store, config: TrackerConfig, recorded: dict[str, Any]
) -> None:
    run_id = stored(store, config, observations_from_payload(recorded["payload"]))
    run = store.run(run_id)
    assert run is not None
    report = build_report(run, store.observations(run_id))
    stats = {e.engine: e for e in report.engines}
    assert (stats["openai"].asked, stats["openai"].answered, stats["openai"].cited) == (2, 2, 1)
    assert stats["openai"].cited_rate == 0.5
    assert (stats["perplexity"].cited, stats["perplexity"].mentioned) == (0, 1)
    assert (stats["aio"].answered, stats["aio"].errors) == (0, 2)
    assert stats["aio"].cited_rate is None


def test_share_of_voice(store: Store, config: TrackerConfig, recorded: dict[str, Any]) -> None:
    run_id = stored(store, config, observations_from_payload(recorded["payload"]))
    run = store.run(run_id)
    assert run is not None
    sov = {r["domain"]: r for r in build_report(run, store.observations(run_id)).share_of_voice}
    # 4 answered pairs; docs.example.org appears in 2 of them.
    assert sov["docs.example.org"]["answers"] == 2
    assert sov["docs.example.org"]["share"] == 0.5
    assert sov["example.com"]["ours"] is True
    assert sov["example.com"]["answers"] == 1
    assert sov["competitor-one.example"]["competitor"] is True
    assert sov["competitor-one.example"]["answers"] == 2


def test_compare_gained_lost_and_not_comparable() -> None:
    def o(engine: str, status: str = "answered", cited: bool = False, mentioned: bool = False) -> Observation:
        return Observation("q", engine, status, cited=cited, mentioned=mentioned)

    before = [o("openai", cited=True, mentioned=True), o("perplexity"), o("aio", "error")]
    after = [o("openai"), o("perplexity", mentioned=True), o("aio")]
    changes, not_comparable = compare(before, after)
    assert [(c.engine, c.signal, c.direction) for c in changes] == [
        ("openai", "cited", "lost"),
        ("openai", "mentioned", "lost"),
        ("perplexity", "mentioned", "gained"),
    ]
    assert not_comparable == 1


def test_cells() -> None:
    assert cell(None) == " "
    assert cell(Observation("q", "e", "error", error="x")) == "!"
    assert cell(Observation("q", "e", "answered", cited=True, rank=3)) == "C3"
    assert cell(Observation("q", "e", "answered", cited=True)) == "C"
    assert cell(Observation("q", "e", "answered", mentioned=True)) == "M"
    assert cell(Observation("q", "e", "answered")) == "-"


def test_render_text_and_markdown(store: Store, config: TrackerConfig, recorded: dict[str, Any]) -> None:
    first = stored(store, config, observations_from_payload(recorded["payload"]))
    second = stored(store, config, [Observation(config.queries[0], "openai", "answered")])
    run = store.run(second)
    previous = store.run(first)
    assert run is not None
    assert previous is not None
    report = build_report(
        run, store.observations(second), previous=previous, previous_observations=store.observations(first)
    )
    text = render(report)
    assert "Run 2 of 'example' for example.com" in text
    assert "lost cited: [openai] What is a good tool" in text
    assert "page score 80/100" in text
    md = render(report, markdown=True)
    assert md.startswith("# Run 2")
    assert "| engine | asked |" in md
    first_report = build_report(previous, store.observations(first))
    assert "No earlier run" in render(first_report)
    assert "2 x no AI Overview for this query" in render(first_report)
    data = report.as_dict()
    assert data["previous_run_id"] == 1
    assert data["changes"][0] == {
        "query": config.queries[0],
        "engine": "openai",
        "signal": "cited",
        "direction": "lost",
    }
