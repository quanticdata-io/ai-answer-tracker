from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ai_answer_tracker import QuanticDataClient, Store, TrackerConfig, parse_config

from .mock_api import FIXTURE, MockState, transport


@pytest.fixture
def recorded() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def config() -> TrackerConfig:
    return parse_config(
        {
            "name": "example",
            "url": "https://www.example.com/",
            "brand": "Example",
            "competitors": ["competitor-one.example"],
            "engines": ["openai", "perplexity", "aio"],
            "country": "us",
            "queries": [
                "What is a good tool to convert web pages to Markdown?",
                "How do I track brand mentions in AI answers?",
            ],
        }
    )


@pytest.fixture
def state() -> MockState:
    return MockState()


@pytest.fixture
def client(state: MockState) -> Iterator[QuanticDataClient]:
    with QuanticDataClient("qd_test_123", transport=transport(state), sleep=lambda _: None) as c:
        yield c


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    counter = iter(range(1, 10_000))
    with Store(tmp_path / "history.db", clock=lambda: f"2026-11-18T10:00:{next(counter):02d}+00:00") as s:
        yield s
