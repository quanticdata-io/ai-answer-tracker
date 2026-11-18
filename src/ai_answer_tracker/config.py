"""Tracker configuration, read from a TOML file."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10 only
    import tomli as tomllib

#: Engines documented for the citation panel of ``POST /scraper/ai-visibility``.
ENGINES: tuple[str, ...] = ("perplexity", "openai", "anthropic", "aio", "copilot", "deepseek")
ENGINE_LABELS: dict[str, str] = {
    "perplexity": "Perplexity",
    "openai": "OpenAI with web search (approximates ChatGPT search)",
    "anthropic": "Anthropic with web search (approximates Claude with search)",
    "aio": "Google AI Overview",
    "copilot": "Bing Copilot answer",
    "deepseek": "DeepSeek over a Google top 10",
}
#: Documented limits of one call.
MAX_QUERIES_PER_CALL = 10
MAX_QUERY_LENGTH = 300
MAX_COMPETITORS = 20
MAX_BRAND_LENGTH = 80

_KNOWN_KEYS = frozenset(
    {"name", "url", "brand", "competitors", "engines", "country", "queries", "full_audit", "offsite"}
)


class ConfigError(ValueError):
    """The configuration cannot be used as written."""


@dataclass(frozen=True)
class TrackerConfig:
    url: str
    queries: tuple[str, ...]
    name: str = "default"
    brand: str | None = None
    competitors: tuple[str, ...] = ()
    engines: tuple[str, ...] = ENGINES
    country: str | None = None
    #: Also run the rendered pass, the AI-crawler fetch and the 2 retrievability SERPs.
    full_audit: bool = False
    #: Also search the brand on five off-site platforms (5 extra SERPs per call).
    offsite: bool = False

    @property
    def domain(self) -> str:
        host = urlparse(self.url).hostname or ""
        return host.removeprefix("www.")

    def with_engines(self, engines: Sequence[str]) -> TrackerConfig:
        return replace(self, engines=validate_engines(engines))


def validate_engines(engines: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for engine in engines:
        e = engine.strip().lower()
        if e not in ENGINES:
            raise ConfigError(f"Unknown engine {engine!r}; choose from {', '.join(ENGINES)}")
        if e not in out:
            out.append(e)
    if not out:
        raise ConfigError("At least one engine is needed")
    return tuple(out)


def _str_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key!r} must be a list of strings")
    return [v.strip() for v in value if v.strip()]


def parse_config(data: Mapping[str, Any], *, default_name: str = "default") -> TrackerConfig:
    unknown = sorted(set(data) - _KNOWN_KEYS)
    if unknown:
        raise ConfigError(f"Unknown keys: {', '.join(unknown)}")
    url = data.get("url")
    if (
        not isinstance(url, str)
        or urlparse(url).scheme not in ("http", "https")
        or not urlparse(url).hostname
    ):
        raise ConfigError("'url' must be an http(s) URL of a page on the site you track")

    queries = list(dict.fromkeys(_str_list(data.get("queries", []), "queries")))
    if not queries:
        raise ConfigError("'queries' must hold at least one question")
    too_long = [q for q in queries if len(q) > MAX_QUERY_LENGTH]
    if too_long:
        raise ConfigError(f"Queries are limited to {MAX_QUERY_LENGTH} characters: {too_long[0][:60]}...")

    competitors = [
        c.lower().removeprefix("www.") for c in _str_list(data.get("competitors", []), "competitors")
    ]
    if len(competitors) > MAX_COMPETITORS:
        raise ConfigError(f"At most {MAX_COMPETITORS} competitor domains")

    brand = data.get("brand")
    if brand is not None and (not isinstance(brand, str) or len(brand) > MAX_BRAND_LENGTH):
        raise ConfigError(f"'brand' must be a string of at most {MAX_BRAND_LENGTH} characters")

    engines = validate_engines(_str_list(data["engines"], "engines")) if "engines" in data else ENGINES

    country = data.get("country")
    if country is not None and (not isinstance(country, str) or len(country) != 2 or not country.isalpha()):
        raise ConfigError("'country' must be a two-letter country code")

    name = data.get("name", default_name)
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("'name' must be a non-empty string")

    for key in ("full_audit", "offsite"):
        if key in data and not isinstance(data[key], bool):
            raise ConfigError(f"{key!r} must be true or false")

    return TrackerConfig(
        url=url,
        queries=tuple(queries),
        name=name.strip(),
        brand=brand.strip() if isinstance(brand, str) and brand.strip() else None,
        competitors=tuple(dict.fromkeys(competitors)),
        engines=engines,
        country=country.lower() if isinstance(country, str) else None,
        full_audit=bool(data.get("full_audit", False)),
        offsite=bool(data.get("offsite", False)),
    )


def load_config(path: str | Path) -> TrackerConfig:
    p = Path(path)
    try:
        with p.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {p}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{p}: invalid TOML: {exc}") from exc
    return parse_config(data, default_name=p.stem)
