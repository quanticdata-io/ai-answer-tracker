"""Local stand-in for ``POST /scraper/ai-visibility``, built from the recorded fixture.

Run it to try the CLI without a key or network (from a clone of the repository):

    python tests/mock_api.py            # http://127.0.0.1:4012/v1
    QUANTICDATA_API_KEY=qd_test_123 QUANTICDATA_API_BASE=http://127.0.0.1:4012/v1 \
        ai-answer-tracker run examples/tracker.toml

Rows follow the shape of the recorded answer in ``tests/fixtures``. Whether a pair is
cited is derived from a hash of the query and engine, so answers are stable between
runs; ``MockState.flip`` changes them to simulate a later run. Domains are fictional.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

FIXTURE = Path(__file__).parent / "fixtures" / "ai_visibility_response.json"
TEMPLATE: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))


class MockState:
    def __init__(self, *, flip: bool = False, unanswered: frozenset[str] = frozenset({"aio"})) -> None:
        self.flip = flip
        self.unanswered = unanswered
        self.bodies: list[dict[str, Any]] = []


def _bit(query: str, engine: str, salt: str) -> bool:
    return hashlib.sha256(f"{salt}|{query}|{engine}".encode()).digest()[0] % 2 == 0


def build_payload(body: dict[str, Any], state: MockState) -> dict[str, Any]:
    payload: dict[str, Any] = copy.deepcopy(TEMPLATE["payload"])
    url = str(body["url"])
    domain = (urlparse(url).hostname or "").removeprefix("www.")
    payload.update(url=url, finalUrl=url, domain=domain)
    rows = []
    billed = 0
    for query in body.get("queries") or []:
        for engine in body.get("engines") or []:
            if engine in state.unanswered:
                rows.append({"query": query, "engine": engine, "cited": False, "mentioned": False,
                             "ourUrls": [], "rank": None, "allDomains": [], "citedUrls": [],
                             "citations": [], "competitors": [], "answerText": "",
                             "answerExcerpt": "", "error": "no answer for this query"})  # fmt: skip
                continue
            billed += 1
            cited = _bit(query, engine, "cited") != state.flip
            mentioned = cited or _bit(query, engine, "mentioned")
            domains = ["docs.example.org", *([domain] if cited else []), "competitor-one.example"]
            rows.append(
                {
                    "query": query,
                    "engine": engine,
                    "cited": cited,
                    "mentioned": mentioned,
                    "ourUrls": [url] if cited else [],
                    "rank": 2 if cited else None,
                    "allDomains": domains,
                    "citedUrls": [f"https://{d}/" for d in domains],
                    "citations": [
                        {"position": i, "url": f"https://{d}/", "domain": d} for i, d in enumerate(domains, 1)
                    ],
                    "competitors": [d for d in domains if d in (body.get("competitors") or [])],
                    "answerText": f"A synthetic answer to: {query}",
                    "answerExcerpt": f"A synthetic answer to: {query}",
                }
            )
    payload["citations"]["queries"] = body.get("queries")
    payload["citations"]["engines"] = body.get("engines")
    payload["citations"]["rows"] = rows
    payload["billing"] = {"citation_calls_billed": billed, "offsite_serps_billed": 0}
    return payload


def handle(request: httpx.Request, state: MockState) -> httpx.Response:
    """Handler for ``httpx.MockTransport``."""
    if not request.headers.get("authorization", "").startswith("Bearer "):
        return httpx.Response(401, json={"type": "error", "message": "Missing API key", "payload": {}})
    if request.method != "POST" or not request.url.path.endswith("/scraper/ai-visibility"):
        return httpx.Response(404, json={"type": "error", "message": "Not found", "payload": {}})
    body = json.loads(request.content)
    state.bodies.append(body)
    if len(body.get("queries") or []) > 10:
        return httpx.Response(400, json={"type": "error", "message": "queries: at most 10", "payload": {}})
    return httpx.Response(
        200, json={"type": "response", "message": "AI visibility audit successful",
                   "payload": build_payload(body, state), "pagination": {}}
    )  # fmt: skip


def transport(state: MockState) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: handle(request, state))


def serve(port: int = 4012) -> None:  # pragma: no cover - manual use
    state = MockState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            request = httpx.Request(
                "POST",
                f"http://127.0.0.1:{port}{self.path}",
                headers=dict(self.headers),
                content=self.rfile.read(length),
            )
            response = handle(request, state)
            self.send_response(response.status_code)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(response.content)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write(f"Mock QuanticData API on http://127.0.0.1:{port}/v1\n")
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 4012)
