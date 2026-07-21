from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = _SOURCE_ROOT if (_SOURCE_ROOT / "pyproject.toml").is_file() else Path.cwd()
DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_PROVIDER_RETRIES = 2
MAX_PROVIDER_RETRIES = 4


class ConfigurationError(ValueError):
    """Raised when the repository-level runtime configuration is invalid."""


@dataclass(frozen=True)
class ProviderSettings:
    base_url: str
    api_key: str
    timeout_seconds: float
    max_retries: int


def load_repository_environment() -> None:
    """Load the single supported dotenv contract without overriding shell values."""

    load_dotenv(REPOSITORY_ROOT / ".env")


def default_model() -> str:
    return os.environ.get("SALES_AGENT_MODEL", DEFAULT_MODEL)


def provider_timeout_seconds() -> float:
    raw = os.environ.get("SALES_AGENT_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError("SALES_AGENT_TIMEOUT_SECONDS must be a number") from error
    if not 0 < value <= 600:
        raise ConfigurationError(
            "SALES_AGENT_TIMEOUT_SECONDS must be greater than 0 and at most 600"
        )
    return value


def provider_max_retries() -> int:
    raw = os.environ.get("SALES_AGENT_PROVIDER_RETRIES", str(DEFAULT_PROVIDER_RETRIES))
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError("SALES_AGENT_PROVIDER_RETRIES must be an integer") from error
    if not 0 <= value <= MAX_PROVIDER_RETRIES:
        raise ConfigurationError(
            f"SALES_AGENT_PROVIDER_RETRIES must be between 0 and {MAX_PROVIDER_RETRIES}"
        )
    return value


def require_provider_settings() -> ProviderSettings:
    base_url = os.environ.get("SALES_AGENT_PROVIDER_BASE_URL", "").strip()
    api_key = os.environ.get("SALES_AGENT_PROVIDER_API_KEY", "").strip()
    missing = [
        name
        for name, value in (
            ("SALES_AGENT_PROVIDER_BASE_URL", base_url),
            ("SALES_AGENT_PROVIDER_API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(
            f"Missing required provider configuration: {joined}. "
            "Copy .env.example to .env and set the credential values."
        )
    return ProviderSettings(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=provider_timeout_seconds(),
        max_retries=provider_max_retries(),
    )
