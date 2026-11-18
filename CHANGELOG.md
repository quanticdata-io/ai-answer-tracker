# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-18

### Added

- `ai-answer-tracker` CLI with `run`, `report`, `export`, `runs` and `init`.
- TOML tracker configuration: page URL, brand, competitors, engines, country, questions, optional full audit and off-site searches.
- Question lists longer than the per-call cap are split into calls of at most 10 questions.
- `--dry-run` prints the planned request bodies and the maximum number of billed pairs.
- SQLite history of runs and answers; answers received before an API error are kept as a `partial` run.
- Reports by engine and by question, share of voice over all answers of a run, and citations or mentions gained or lost since the previous run; text, Markdown and JSON output; `--fail-on-lost` exit code for CI.
- CSV, JSON and JSONL export.
- Python API: `QuanticDataClient`, `Store`, `run_tracker`, `build_report`, `render`.
