# Contributing

Thanks for helping improve the tracker.

## Setup

```bash
git clone https://github.com/quanticdata-io/ai-answer-tracker
cd ai-answer-tracker
uv venv && uv pip install -e . --group dev
```

Plain pip works too: `pip install -e . pytest pytest-cov mypy ruff`.

## Checks

CI runs these on Python 3.10 to 3.13, on Ubuntu and Windows:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

## Ground rules

- Tests never call the QuanticData API or the network. Use `httpx.MockTransport` and the helpers in `tests/mock_api.py`.
- Fixtures are recorded answers reduced to the fields the tool reads, with every domain, URL and answer text replaced by fictional values (`.example` domains). Never commit a key, a request id or a real answer that names people.
- The client sends only fields documented for `POST /scraper/ai-visibility` in the [API reference](https://quanticdata.io/docs/).
- The export columns (`ai_answer_tracker.export.COLUMNS`) and the SQLite tables are a public contract: adding a column is a minor release, renaming or removing one is a major release. Schema changes need a migration for existing history files.
- User-facing changes need a CHANGELOG entry under "Unreleased".

## Running against the real API

Set `QUANTICDATA_API_KEY`, start with `--dry-run`, then a single question and a single engine (`--engines deepseek`) so a mistake costs little.
