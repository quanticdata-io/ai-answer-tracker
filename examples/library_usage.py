"""Run a tracker from Python and print the questions where the site lost a citation.

export QUANTICDATA_API_KEY=qd_live_your_key
python examples/library_usage.py
"""

from __future__ import annotations

from ai_answer_tracker import QuanticDataClient, Store, build_report, parse_config, render, run_tracker

config = parse_config(
    {
        "name": "docs-pages",
        "url": "https://www.example.com/docs/",
        "brand": "Example",
        "engines": ["openai", "perplexity"],
        "queries": ["How do I convert a web page to Markdown for an LLM?"],
    }
)

with QuanticDataClient() as client, Store("ai-answers.db") as store:
    run_id = run_tracker(client, config, store)
    run = store.run(run_id)
    assert run is not None
    previous = store.previous_run(run)
    report = build_report(
        run,
        store.observations(run_id),
        previous=previous,
        previous_observations=store.observations(previous.id) if previous else (),
    )

print(render(report))
for change in report.changes:
    if change.direction == "lost":
        print(f"Lost {change.signal} on {change.engine}: {change.query}")
