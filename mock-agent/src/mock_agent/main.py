from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from mock_agent.contract import RuntimeRequest
from mock_agent.model import OpenAIModelClient
from mock_agent.plan_state_runtime import PlanStateRuntime


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one AutomationBench task")
    parser.add_argument("--task-id", default="sales.zoom_calendar_conflict")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/sales.zoom_calendar_conflict.json",
    )
    return parser.parse_args()


def _json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def main() -> None:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(REPOSITORY_ROOT / ".env")
    outcome = asyncio.run(
        PlanStateRuntime(model_client=OpenAIModelClient()).run(
            RuntimeRequest(task_id=args.task_id, model_name=args.model)
        )
    )
    record = asdict(outcome)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, indent=2, default=_json_value) + "\n",
        encoding="utf-8",
    )
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
    print(f"result: {args.output}")


if __name__ == "__main__":
    main()
