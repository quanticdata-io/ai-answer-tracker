from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_answer_tracker import ENGINES, ConfigError, load_config, parse_config
from ai_answer_tracker.cli import EXAMPLE_CONFIG

BASE: dict[str, Any] = {"url": "https://www.example.com/", "queries": ["q1"]}


def test_defaults() -> None:
    cfg = parse_config(BASE)
    assert cfg.engines == ENGINES
    assert cfg.domain == "example.com"
    assert cfg.name == "default"
    assert not cfg.full_audit
    assert not cfg.offsite


def test_example_config_parses(tmp_path: Path) -> None:
    path = tmp_path / "mine.toml"
    path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.name == "example"
    assert cfg.engines == ("openai", "perplexity", "aio")
    assert cfg.competitors == ("competitor-one.example", "competitor-two.example")


def test_repository_example_parses() -> None:
    cfg = load_config(Path(__file__).parent.parent / "examples" / "tracker.toml")
    assert cfg.queries


def test_name_defaults_to_file_stem(tmp_path: Path) -> None:
    path = tmp_path / "brand-watch.toml"
    path.write_text('url = "https://example.com/"\nqueries = ["q"]\n', encoding="utf-8")
    assert load_config(path).name == "brand-watch"


def test_queries_deduplicated_and_competitors_normalised() -> None:
    cfg = parse_config({**BASE, "queries": ["a", "a", " b "], "competitors": ["WWW.Rival.example"]})
    assert cfg.queries == ("a", "b")
    assert cfg.competitors == ("rival.example",)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"url": "ftp://example.com"}, "url"),
        ({"queries": []}, "at least one"),
        ({"queries": ["x" * 301]}, "300"),
        ({"engines": ["chatgpt"]}, "Unknown engine"),
        ({"country": "usa"}, "two-letter"),
        ({"competitors": [f"c{i}.example" for i in range(21)]}, "20"),
        ({"brand": "b" * 81}, "80"),
        ({"offsite": "yes"}, "true or false"),
        ({"unknown_key": 1}, "Unknown keys"),
    ],
)
def test_invalid(override: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config({**BASE, **override})


def test_missing_file_and_bad_toml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("url = ", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(bad)


def test_with_engines_validates() -> None:
    cfg = parse_config(BASE).with_engines(["OpenAI", "openai", "aio"])
    assert cfg.engines == ("openai", "aio")
    with pytest.raises(ConfigError):
        cfg.with_engines([])
