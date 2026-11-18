from __future__ import annotations

import httpx
import pytest

from ai_answer_tracker import (
    AuthenticationError,
    PaymentRequiredError,
    QuanticDataClient,
    QuanticDataError,
    RateLimitError,
)


def make(transport: httpx.MockTransport, sleeps: list[float] | None = None) -> QuanticDataClient:
    return QuanticDataClient(
        "qd_test_123", transport=transport, sleep=(sleeps.append if sleeps is not None else lambda _: None)
    )


def error(status: int, message: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers, json={"type": "error", "message": message, "payload": {}})


def test_sends_bearer_key_and_returns_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"type": "response", "message": "ok", "payload": {"url": "u"}})

    with make(httpx.MockTransport(handler)) as client:
        assert client.ai_visibility({"url": "u"}) == {"url": "u"}
    assert seen[0].headers["authorization"] == "Bearer qd_test_123"
    assert seen[0].url.path == "/v1/scraper/ai-visibility"
    assert seen[0].headers["user-agent"].startswith("ai-answer-tracker/")


def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTICDATA_API_KEY", raising=False)
    with pytest.raises(AuthenticationError, match="QUANTICDATA_API_KEY"):
        QuanticDataClient()


def test_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTICDATA_API_KEY", "qd_test_123")
    monkeypatch.setenv("QUANTICDATA_API_BASE", "http://127.0.0.1:4012/v1/")
    with QuanticDataClient() as client:
        assert client.base_url == "http://127.0.0.1:4012/v1"


def test_429_retried_after_retry_after() -> None:
    answers = iter([error(429, "slow down", {"retry-after": "3"}), httpx.Response(200, json={"payload": {}})])
    sleeps: list[float] = []
    with make(httpx.MockTransport(lambda r: next(answers)), sleeps) as client:
        assert client.ai_visibility({}) == {}
    assert sleeps == [3.0]


def test_429_with_long_wait_is_raised() -> None:
    with (
        make(httpx.MockTransport(lambda r: error(429, "cap", {"retry-after": "3600"}))) as client,
        pytest.raises(RateLimitError) as info,
    ):
        client.ai_visibility({})
    assert info.value.retry_after == 3600


@pytest.mark.parametrize(
    ("status", "exc"), [(401, AuthenticationError), (402, PaymentRequiredError), (400, QuanticDataError)]
)
def test_errors(status: int, exc: type[Exception]) -> None:
    with make(httpx.MockTransport(lambda r: error(status, "nope"))) as client, pytest.raises(exc):
        client.ai_visibility({})


def test_server_error_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return error(500, "unavailable")

    with make(httpx.MockTransport(handler)) as client, pytest.raises(QuanticDataError, match="500"):
        client.ai_visibility({})
    assert len(calls) == 1


def test_connect_error_retried_then_raised() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("refused", request=request)

    with make(httpx.MockTransport(handler)) as client, pytest.raises(QuanticDataError, match="Cannot reach"):
        client.ai_visibility({})
    assert len(calls) == 3


def test_answer_without_payload() -> None:
    with (
        make(httpx.MockTransport(lambda r: httpx.Response(200, text="not json"))) as client,
        pytest.raises(QuanticDataError, match="no payload"),
    ):
        client.ai_visibility({})
