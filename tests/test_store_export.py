from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from ai_answer_tracker import Store, TrackerConfig, observations_from_payload
from ai_answer_tracker.export import COLUMNS, dumps, rows


def test_runs_and_lookup(store: Store, config: TrackerConfig, recorded: dict[str, Any]) -> None:
    assert store.latest_run() is None
    a = store.start_run(config)
    store.add_observations(a, observations_from_payload(recorded["payload"]))
    store.finish_run(a, status="done", billed_calls=4)
    running = store.start_run(config)  # unfinished runs are ignored by latest/previous
    b = store.start_run(config)
    store.finish_run(b, status="partial", billed_calls=0, note="stopped")
    latest = store.latest_run("example")
    assert latest is not None
    assert latest.id == b
    previous = store.previous_run(latest)
    assert previous is not None
    assert previous.id == a
    assert store.previous_run(previous) is None
    assert store.latest_run("other") is None
    assert [r.id for r in store.runs("example")] == [a, running, b]
    assert store.run(999) is None
    run = store.run(a)
    assert run is not None
    assert run.engines == ("openai", "perplexity", "aio")
    assert run.as_dict()["queries"] == list(config.queries)


def test_observations_round_trip(store: Store, config: TrackerConfig, recorded: dict[str, Any]) -> None:
    run_id = store.start_run(config)
    original = observations_from_payload(recorded["payload"])
    store.add_observations(run_id, original)
    assert store.observations(run_id) == original


def test_history_survives_reopen(tmp_path: Path, config: TrackerConfig) -> None:
    path = tmp_path / "h.db"
    with Store(path) as s:
        s.finish_run(s.start_run(config), status="done", billed_calls=0)
    with Store(path) as s:
        assert len(s.runs()) == 1


def test_exports(store: Store, config: TrackerConfig, recorded: dict[str, Any]) -> None:
    run_id = store.start_run(config)
    store.add_observations(run_id, observations_from_payload(recorded["payload"]))
    run = store.run(run_id)
    assert run is not None
    data = list(rows(store, [run]))
    assert len(data) == 6
    assert tuple(data[0]) == COLUMNS

    parsed = list(csv.DictReader(io.StringIO(dumps(data, "csv"))))
    assert parsed[0]["cited"] == "true"
    assert parsed[0]["cited_domains"] == "docs.example.org;example.com;competitor-one.example"
    assert parsed[2]["status"] == "error"
    assert parsed[2]["rank"] == ""

    assert json.loads(dumps(data, "json"))[0]["rank"] == 2
    lines = dumps(data, "jsonl").splitlines()
    assert len(lines) == 6
    assert json.loads(lines[1])["mentioned"] is True
    with pytest.raises(ValueError, match="Unknown format"):
        dumps(data, "xml")
