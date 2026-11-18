"""Track whether AI assistants cite or mention your site, run after run."""

from ._version import __version__
from .api import (
    AuthenticationError,
    PaymentRequiredError,
    QuanticDataClient,
    QuanticDataError,
    RateLimitError,
)
from .config import ENGINES, ConfigError, TrackerConfig, load_config, parse_config
from .models import Observation
from .report import Report, build_report, render
from .store import Run, Store
from .tracker import build_requests, observations_from_payload, planned_engine_calls, run_tracker

__all__ = [
    "ENGINES",
    "AuthenticationError",
    "ConfigError",
    "Observation",
    "PaymentRequiredError",
    "QuanticDataClient",
    "QuanticDataError",
    "RateLimitError",
    "Report",
    "Run",
    "Store",
    "TrackerConfig",
    "__version__",
    "build_report",
    "build_requests",
    "load_config",
    "observations_from_payload",
    "parse_config",
    "planned_engine_calls",
    "render",
    "run_tracker",
]
