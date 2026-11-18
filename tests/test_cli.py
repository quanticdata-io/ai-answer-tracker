from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_answer_tracker import QuanticDataClient, cli

from .mock_api import MockState, transport

CONFIG = """\
name = "demo"
url = "https://www.example.com/"
brand = "Example"
competitors = ["competitor-one.example"]
engines = ["openai", "perplexity", "aio"]
queries = ["What is a good tool to convert web pages to Markdown?", "How do I track brand mentions?"]
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "demo.toml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


@pytest.fixture
def mock_state(monkeypatch: pytest.MonkeyPatch) -> MockState:
    state = MockState()

    def factory(**kwargs: Any) -> QuanticDataClient:
        return QuanticDataClient("qd_test_123", transport=transport(state), **kwargs)

    monkeypatch.setattr(cli, "QuanticDataClient", factory)
    return state


def test_dry_run_makes_no_call(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", str(config_path), "--dry-run", "--engines", "openai,aio"]) == 0
    out = capsys.readouterr().out
    assert "1 call(s) to POST /scraper/ai-visibility" in out
    assert "up to 4 billed" in out
    assert '"engines": [\n    "openai",\n    "aio"\n  ]' in out


def test_run_report_export_runs(
    tmp_path: Path, config_path: Path, mock_state: MockState, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "h.db")
    assert cli.main(["run", str(config_path), "--db", db]) == 0
    out = capsys.readouterr().out
    assert "Run 1 of 'demo' for example.com" in out
    assert "No earlier run" in out

    mock_state.flip = True  # every answered pair changes its "cited" value
    assert cli.main(["run", str(config_path), "--db", db, "--fail-on-lost"]) == cli.EXIT_LOST
    out = capsys.readouterr().out
    assert "Compared with run 1:" in out

    assert cli.main(["report", "--db", db, "--run", "1", "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["run"]["id"] == 1
    assert len(data["observations"]) == 6

    md = tmp_path / "report.md"
    assert cli.main(["report", "--db", db, "--tracker", "demo", "-f", "markdown", "-o", str(md)]) == 0
    assert md.read_text(encoding="utf-8").startswith("# Run 2")

    out_csv = tmp_path / "all.csv"
    assert cli.main(["export", "--db", db, "-o", str(out_csv)]) == 0
    assert len(out_csv.read_text(encoding="utf-8").splitlines()) == 1 + 12
    assert cli.main(["export", "--db", db, "--run", "2", "-f", "jsonl"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 6

    assert cli.main(["runs", "--db", db]) == 0
    listing = capsys.readouterr().out
    assert "demo" in listing
    assert "2 question(s) x 3 engine(s)" in listing


def test_api_error_exit_code(
    config_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("QUANTICDATA_API_KEY", raising=False)
    assert cli.main(["run", str(config_path), "--db", str(tmp_path / "h.db")]) == cli.EXIT_API
    assert "QUANTICDATA_API_KEY" in capsys.readouterr().err


def test_usage_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "empty.db")
    assert cli.main(["report", "--db", db]) == cli.EXIT_USAGE
    assert "No finished run" in capsys.readouterr().err
    assert cli.main(["report", "--db", db, "--run", "7"]) == cli.EXIT_USAGE
    assert cli.main(["export", "--db", db, "-o", str(tmp_path / "x.xml")]) == cli.EXIT_USAGE
    assert cli.main(["run", str(tmp_path / "missing.toml")]) == cli.EXIT_USAGE
    assert cli.main(["runs", "--db", db]) == 0
    assert "No runs" in capsys.readouterr().out


def test_init(tmp_path: Path) -> None:
    path = tmp_path / "tracker.toml"
    assert cli.main(["init", str(path)]) == 0
    assert "queries" in path.read_text(encoding="utf-8")
    assert cli.main(["init", str(path)]) == cli.EXIT_USAGE
    assert cli.main(["init", str(path), "--force"]) == 0
