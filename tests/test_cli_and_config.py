from types import SimpleNamespace

import pytest

from sales_agent import __version__, cli
from sales_agent.config import (
    ConfigurationError,
    provider_max_retries,
    provider_timeout_seconds,
    require_provider_settings,
)
from sales_agent.model import ModelRequest, OpenAIModelClient


def test_distribution_has_one_runtime_version_source():
    assert __version__ == "1.0.0"


def test_root_cli_dispatches_all_four_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_main", lambda args, **_: calls.append(("run", args)))
    monkeypatch.setattr(
        cli,
        "evaluation_main",
        lambda args, **_: calls.append(("evaluation", args)),
    )
    monkeypatch.setattr(cli, "viewer_main", lambda args, **_: calls.append(("viewer", args)))

    cli.main(["run", "--task-id", "task"])
    cli.main(["evaluate", "--manifest", "manifest.json"])
    cli.main(["report", "--json", "report.json"])
    cli.main(["viewer", "--port", "9000"])

    assert calls == [
        ("run", ["--task-id", "task"]),
        ("evaluation", ["evaluate", "--manifest", "manifest.json"]),
        ("evaluation", ["report", "--json", "report.json"]),
        ("viewer", ["--port", "9000"]),
    ]


def test_provider_configuration_is_validated_and_bounded(monkeypatch):
    for name in (
        "SALES_AGENT_PROVIDER_BASE_URL",
        "SALES_AGENT_PROVIDER_API_KEY",
        "SALES_AGENT_TIMEOUT_SECONDS",
        "SALES_AGENT_PROVIDER_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigurationError, match="SALES_AGENT_PROVIDER_BASE_URL"):
        require_provider_settings()

    monkeypatch.setenv("SALES_AGENT_TIMEOUT_SECONDS", "0")
    with pytest.raises(ConfigurationError, match="greater than 0"):
        provider_timeout_seconds()
    monkeypatch.setenv("SALES_AGENT_PROVIDER_RETRIES", "5")
    with pytest.raises(ConfigurationError, match="between 0 and 4"):
        provider_max_retries()


@pytest.mark.asyncio
async def test_model_client_is_created_once_with_explicit_timeout(monkeypatch):
    monkeypatch.setenv("SALES_AGENT_PROVIDER_BASE_URL", "https://example.test/openai/v1")
    monkeypatch.setenv("SALES_AGENT_PROVIDER_API_KEY", "test-only-key")
    monkeypatch.setenv("SALES_AGENT_TIMEOUT_SECONDS", "42")
    monkeypatch.setenv("SALES_AGENT_PROVIDER_RETRIES", "0")
    created = []

    class Responses:
        async def create(self, **_):
            return SimpleNamespace(
                id="response",
                status="completed",
                output=[],
                output_text="done",
                output_parsed=None,
                usage=None,
            )

    def fake_openai(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(responses=Responses())

    monkeypatch.setattr("sales_agent.model.AsyncOpenAI", fake_openai)
    client = OpenAIModelClient()
    request = ModelRequest(
        role="executor",
        model_name="test-model",
        instructions="Respond.",
        input=({"role": "user", "content": "Continue."},),
    )

    await client.respond(request)
    await client.respond(request)

    assert len(created) == 1
    assert created[0]["timeout"] == 42
    assert created[0]["max_retries"] == 0
