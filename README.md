# AI Answer Tracker

Track whether AI assistants cite your site or mention your brand when they answer the questions your customers ask. Give it a list of questions; it asks Perplexity, OpenAI and Anthropic models with web search, Google AI Overview, Bing Copilot and DeepSeek, stores every answer in SQLite, and reports what is cited, who else is cited (share of voice), and what changed since the last run. Export to CSV, JSON or JSONL.

[![CI](https://github.com/quanticdata-io/ai-answer-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/quanticdata-io/ai-answer-tracker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

The questions are asked through the AI visibility endpoint of the [QuanticData API](https://quanticdata.io/docs/) (`POST /scraper/ai-visibility`), so you need an API key. This tool adds what one API call does not give you: a history, run-to-run comparison, question lists longer than one call accepts, and exports.

```text
By question (C cited, M mentioned only, - neither, ! no answer)

question                                               openai  perplexity  aio
-----------------------------------------------------  ------  ----------  ---
What is a good tool to convert web pages to Markdown?  C2      M           !
How do I track brand mentions in AI answers?           -       -           !
```

## Install

From source (the package is not on PyPI):

```bash
pip install git+https://github.com/quanticdata-io/ai-answer-tracker
```

or from a clone:

```bash
git clone https://github.com/quanticdata-io/ai-answer-tracker
cd ai-answer-tracker
pip install -e .
```

Python 3.10 or later. The command is `ai-answer-tracker` (also `python -m ai_answer_tracker`). The only dependencies are `httpx` and, on Python 3.10, `tomli`.

## Quickstart

```bash
ai-answer-tracker init tracker.toml               # writes a commented example configuration
# edit tracker.toml: your URL, brand, competitors and questions
ai-answer-tracker run tracker.toml --dry-run      # prints the planned API calls, costs nothing
export QUANTICDATA_API_KEY=qd_live_your_key       # created on the API keys page of the dashboard
ai-answer-tracker run tracker.toml                # asks the engines, stores and prints the report
ai-answer-tracker export -o answers.csv
```

Run it again tomorrow, or on a schedule (cron, a CI job), and each report lists the citations and mentions gained or lost since the previous run of the same tracker.

### Try it without a key or network

From a clone, the bundled mock of the endpoint answers with synthetic data built from a recorded answer:

```bash
python tests/mock_api.py &        # mock API on http://127.0.0.1:4012/v1
export QUANTICDATA_API_KEY=qd_test_123 QUANTICDATA_API_BASE=http://127.0.0.1:4012/v1
ai-answer-tracker run examples/tracker.toml --db demo.db
ai-answer-tracker report --db demo.db -f markdown
```

## Configuration

A TOML file (`tomllib` on Python 3.11+, `tomli` on 3.10):

```toml
name = "example"                          # tracker name; runs are compared within one name (default: file name)
url = "https://www.example.com/"          # a page of your site; citations count for its domain (www. ignored)
brand = "Example"                         # name looked for in the answer text ("mentioned"); optional
competitors = ["competitor-one.example"]  # always listed in the share of voice; optional, at most 20
engines = ["openai", "perplexity", "aio"] # default: all six
country = "us"                            # two-letter country of the search locale; optional
queries = [                               # questions, up to 300 characters each
  "What is a good tool to convert web pages to Markdown?",
  "How do I track brand mentions in AI answers?",
]
full_audit = false                        # see "What one call runs" below
offsite = false                           # also search the brand on five off-site platforms (5 billed searches per call)
```

When `brand` is not set, the API looks for the page's own site name.

### Engines

| Name | What answers |
| --- | --- |
| `perplexity` | Perplexity |
| `openai` | An OpenAI model with web search, an approximation of ChatGPT search (not chatgpt.com itself) |
| `anthropic` | An Anthropic model with web search, an approximation of Claude with search (not claude.ai itself) |
| `aio` | The Google AI Overview on a live Google results page |
| `copilot` | The generative answer on a live Bing results page |
| `deepseek` | A Google top 10 for the question handed to DeepSeek to answer and cite: it measures whether a model picks your page from the same results |

The API documents that Google AI Overview and Bing Copilot report brand mentions only, because their results pages expose no sources. Treat their "cited" column accordingly.

## Commands

```text
ai-answer-tracker run CONFIG [--db FILE] [--engines a,b] [--dry-run] [--fail-on-lost] [--timeout S]
ai-answer-tracker report [--db FILE] [--tracker NAME] [--run ID] [-f text|markdown|json] [-o FILE]
ai-answer-tracker export [--db FILE] [--tracker NAME] [--run ID] [-f csv|json|jsonl] [-o FILE]
ai-answer-tracker runs   [--db FILE] [--tracker NAME]
ai-answer-tracker init   [PATH] [--force]
```

| Option | Meaning |
| --- | --- |
| `--db` | SQLite history file (default `ai-answers.db` in the current directory) |
| `run --engines` | Comma-separated engines for this run only, overriding the configuration |
| `run --dry-run` | Print the request bodies and the maximum number of billed pairs, send nothing |
| `run --fail-on-lost` | Exit with code 3 when a citation or mention was lost since the previous run (for CI alerts) |
| `run --timeout` | Seconds per API call (default 300; one call asks every engine and can take a while) |
| `report --tracker`, `--run` | Which run to show (default: the latest finished run) |
| `report -f` | `text` (default), `markdown` (for a pull request or a wiki page) or `json` (everything, including each answer) |
| `export` | Every stored answer of the selected runs (default: all runs, or all runs of `--tracker`); format from `-f` or the `-o` extension, else CSV |
| `-o, --output` | Write to a file instead of stdout |

Exit codes: 0 success, 1 API error (the answers already received are kept as a `partial` run), 2 configuration or usage error, 3 lost citation with `--fail-on-lost`.

## What a report contains

- **By engine**: questions asked, answered, not answered, cited and mentioned, with rates over the answered ones.
- **By question**: one cell per question and engine. `C` cited (with the position of your first source when the engine numbers its sources, for example `C2`), `M` mentioned in the text but not cited, `-` neither, `!` no answer.
- **Share of voice**: for each domain, the share of answered (question x engine) pairs that cite it. Computed by this tool over all the answers of the run, so it also covers runs split over several calls. Your domain and your competitors are always listed.
- **Changes since the previous run** of the same tracker: `gained cited`, `lost cited`, `gained mentioned`, `lost mentioned`. A pair that answered in only one of the two runs is counted apart, never reported as a change.
- **No answer**: the reasons the engines gave, grouped.

A pair with no answer is stored with `status = error` and its reason. It is excluded from the rates and from the share of voice, so an engine that is temporarily unavailable does not show up as "not cited".

## Export columns

`run_id, tracker, started_at, domain, query, engine, status, cited, mentioned, rank, our_urls, cited_domains, competitors_cited, error, answer_excerpt`

In CSV, lists are `;`-separated and booleans are `true`/`false`. `answer_excerpt` keeps the first 500 characters of the answer. The SQLite file has two tables, `runs` and `observations`, if you prefer to query it directly.

## What one call runs, and what it costs

Each call to `POST /scraper/ai-visibility` asks up to 10 questions (the documented cap), so a list of 23 questions becomes 3 calls; `--dry-run` shows them. Every call:

- always runs the on-page audit of `url` (the page score shown in the report comes from it);
- asks each engine each question. Each (question x engine) pair that answers is billed; pairs that return no answer are not (`billing.citation_calls_billed` in the answer, stored as `billed_calls` per run).

By default the tool sends `no_render`, `no_bot_fetch` and `no_retrieval`, which skip the optional parts of the audit (a rendered pass, a fetch that identifies as an AI crawler and two retrievability searches). `full_audit = true` keeps them. `offsite = true` adds five searches per call. Prices are on the [pricing page](https://quanticdata.io/pricing/); the API also enforces a daily per-account cap on engine calls.

Example of one row of the answer, trimmed (the shape the tool reads):

```json
{
  "query": "What is a good tool to convert web pages to Markdown?",
  "engine": "openai",
  "cited": true,
  "mentioned": true,
  "rank": 2,
  "ourUrls": ["https://www.example.com/markdown/"],
  "allDomains": ["docs.example.org", "example.com", "competitor-one.example"],
  "citations": [{"position": 1, "url": "https://docs.example.org/guide/markdown", "domain": "docs.example.org"}],
  "competitors": ["competitor-one.example"],
  "answerExcerpt": "Several tools convert pages to Markdown..."
}
```

A pair without an answer carries `"error": "<reason>"` instead.

## Python

```python
from ai_answer_tracker import QuanticDataClient, Store, build_report, load_config, render, run_tracker

config = load_config("tracker.toml")
with (
    QuanticDataClient() as client,
    Store("ai-answers.db") as store,
):  # QUANTICDATA_API_KEY, QUANTICDATA_API_BASE
    run_id = run_tracker(client, config, store)
    run = store.run(run_id)
    previous = store.previous_run(run)
    report = build_report(
        run,
        store.observations(run_id),
        previous=previous,
        previous_observations=store.observations(previous.id) if previous else (),
    )
print(render(report, markdown=True))
```

More in [`examples/`](examples/).

## Limits

- AI answers vary from one request to the next even for the same question. One run is a sample: look at trends over several runs and many questions before drawing conclusions.
- `openai` and `anthropic` are model APIs with web search, not the consumer apps; `deepseek` answers from a Google top 10, not from DeepSeek's own product. The API says so in `engineNotes`.
- An engine can return no answer for a question, or be unavailable for a while. Those pairs are kept as `!` and excluded from the rates.
- Engine availability depends on the service. In our checks on 2026-11-18 only `openai` returned answers; the other engines returned error rows ("not configured" or "retry"). Run with `--dry-run`, then a single question, to see which engines answer for your account before scheduling a tracker.
- "Cited" is about the domain of `url`. To track several sites, use one tracker per site.
- Results depend on the locale (`country`) and on the day; the tool does not try to reproduce one user's personalised answers.

## Respectful use

Ask questions that real people ask about your market, at a modest frequency (daily or weekly is plenty for trends). Do not put personal data in questions. Answer excerpts are stored locally in the SQLite file; delete it when you no longer need it.

## Development

```bash
uv venv && uv pip install -e . --group dev     # or: pip install -e . pytest pytest-cov mypy ruff
ruff check . && ruff format --check . && mypy && pytest
```

Tests never call the QuanticData API or the network: the client runs against `httpx.MockTransport`, with answers built from the recorded and sanitised fixture in `tests/fixtures/`. See [CONTRIBUTING.md](CONTRIBUTING.md). To run against the real API, set `QUANTICDATA_API_KEY` and use the commands above; start with `--dry-run` and one engine.

## License

[MIT](LICENSE)
