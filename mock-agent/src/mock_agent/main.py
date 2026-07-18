from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Callable
from urllib.parse import quote

from dotenv import load_dotenv

from mock_agent.adapter import AutomationBenchAdapter
from mock_agent.artifacts import (
    RunArtifactStore,
    artifact_from_outcome,
    configuration_identity,
    task_snapshot,
)
from mock_agent.catalog import TaskCatalog
from mock_agent.contract import AgentRuntime, RuntimeRequest
from mock_agent.model import OpenAIModelClient
from mock_agent.plan_state_runtime import PLAN_STATE_LIMITS
from mock_agent.plan_state_runtime import PlanStateRuntime


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parent
RuntimeFactory = Callable[[], AgentRuntime]
HARNESS_VERSION = "plan-state/1.0.0"
PROMPT_VERSION = "plan-state-prompts/v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one AutomationBench task")
    parser.add_argument("--task-id", default="sales.zoom_calendar_conflict")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional exact artifact path; defaults to results/runs/<run-id>.json",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=PROJECT_ROOT / "results/runs",
    )
    parser.add_argument("--viewer-base-url", default="http://127.0.0.1:8000/")
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None, *, runtime_factory: RuntimeFactory | None = None
) -> None:
    args = parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(REPOSITORY_ROOT / ".env")
    catalog = TaskCatalog.from_sales_dataset()
    adapter = AutomationBenchAdapter(catalog=catalog)
    task = catalog.get_task(args.task_id)
    tools = adapter.open(args.task_id).agent_task.tools
    snapshot = task_snapshot(
        task,
        tool_definitions=[
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ],
    )
    configuration = {
        "model": args.model,
        "harness_version": HARNESS_VERSION,
        "prompt_version": PROMPT_VERSION,
        "evaluation_protocol_version": "single-run/v1",
        "execution_limits": PLAN_STATE_LIMITS,
        "runtime": {
            "id": "custom",
            "label": "Custom agent",
            "version": HARNESS_VERSION,
        },
    }
    configuration["identity"] = configuration_identity(configuration)
    started_at = datetime.now(timezone.utc).isoformat()
    started = monotonic()
    runtime = (
        runtime_factory()
        if runtime_factory is not None
        else PlanStateRuntime(model_client=OpenAIModelClient(), adapter=adapter)
    )
    outcome = asyncio.run(
        runtime.run(RuntimeRequest(task_id=args.task_id, model_name=args.model))
    )
    finished_at = datetime.now(timezone.utc).isoformat()
    artifact = artifact_from_outcome(
        outcome,
        task=snapshot,
        configuration=configuration,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=(monotonic() - started) * 1000,
        initial_world=task.info["initial_state"],
    )
    output = args.output or args.artifacts_dir / f"{outcome.run_id}.json"
    path = RunArtifactStore(output.parent).write(artifact, filename=output.name)
    print(f"task: {args.task_id}")
    print(f"status: {outcome.status.value}")
    reason = (
        outcome.termination_reason.value
        if outcome.termination_reason
        else "unavailable"
    )
    print(f"termination_reason: {reason}")
    if outcome.score is not None:
        print(f"partial_credit: {outcome.score['partial_credit']:.3f}")
        print(
            f"task_completed_correctly: {outcome.score['task_completed_correctly']:.0f}"
        )
    viewer_separator = "&" if "?" in args.viewer_base_url else "?"
    viewer_url = (
        f"{args.viewer_base_url}{viewer_separator}run_id={quote(outcome.run_id)}"
    )
    print(f"artifact: {path}")
    print(f"viewer: {viewer_url}")


if __name__ == "__main__":
    main()
