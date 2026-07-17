from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from mock_agent.catalog import TaskCatalog
from mock_agent.contract import AgentRuntime, EventKind, RuntimeOutcome, RuntimeRequest
from mock_agent.model import OpenAIModelClient
from mock_agent.planner_executor import EXECUTION_LIMITS, PlannerExecutorRuntime


RuntimeFactory = Callable[[], AgentRuntime]
CONFIGURATION_FIELDS = (
    "model",
    "harness_version",
    "prompt_version",
    "evaluation_protocol_version",
    "execution_limits",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and report offline agent evaluations"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run or resume a preregistered task panel")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--repetitions", type=int, required=True)
    run.add_argument("--artifacts-dir", type=Path, required=True)
    report = commands.add_parser("report", help="Build deterministic offline reports")
    report.add_argument("--artifacts-dir", type=Path, required=True)
    report.add_argument("--markdown", type=Path, required=True)
    report.add_argument("--json", type=Path, required=True)
    return parser


def _load_inputs(manifest_path: Path, config_path: Path) -> tuple[list[str], dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tasks = manifest.get("tasks")
    if (
        not isinstance(tasks, list)
        or not tasks
        or not all(isinstance(x, str) for x in tasks)
    ):
        raise ValueError("Manifest must contain a non-empty string task list")
    if len(set(tasks)) != len(tasks):
        raise ValueError("Manifest task IDs must be unique")
    missing = [field for field in CONFIGURATION_FIELDS if field not in config]
    if missing:
        raise ValueError(f"Configuration is missing: {', '.join(missing)}")
    if config["execution_limits"] != EXECUTION_LIMITS:
        raise ValueError(f"Execution limits must equal the frozen limits: {EXECUTION_LIMITS}")
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return tasks, {**config, "identity": sha256(canonical.encode()).hexdigest()}


def _existing_pairs(directory: Path) -> set[tuple[str, str, int]]:
    pairs = set()
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("artifact_type") != "agent_evaluation_run":
                continue
            pairs.add(
                (
                    record["configuration"]["identity"],
                    record["task_id"],
                    int(record["repetition"]),
                )
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return pairs


def _infrastructure_failure(outcome: RuntimeOutcome) -> bool:
    return any(
        event.kind is EventKind.MODEL_ERROR
        and isinstance(event.content, dict)
        and event.content.get("infrastructure_failure") is True
        for event in outcome.events
    )


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _write_json(path: Path, value: Any) -> None:
    payload = (
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=True, default=_json_default
        )
        + "\n"
    )
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _record(
    outcome: RuntimeOutcome,
    *,
    config: dict,
    repetition: int,
    started_at: str,
    finished_at: str,
    duration_ms: float,
    initial_world: dict,
) -> dict:
    score = outcome.score or {}
    events = [asdict(event) for event in outcome.events]
    return {
        "artifact_type": "agent_evaluation_run",
        "schema_version": 1,
        "configuration": config,
        "task_id": outcome.task_id,
        "repetition": repetition,
        "run_id": outcome.run_id,
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": round(duration_ms, 3),
        },
        "status": outcome.status.value,
        "termination_reason": (
            outcome.termination_reason.value if outcome.termination_reason else None
        ),
        "trace": events,
        "provider_retry_count": sum(
            event.kind is EventKind.PROVIDER_RETRY for event in outcome.events
        ),
        "model_turn_count": sum(event.usage is not None for event in outcome.events),
        "tool_call_count": sum(
            event.kind is EventKind.TOOL_CALL for event in outcome.events
        ),
        "contains_tool_errors": any(
            event.kind is EventKind.TOOL_ERROR for event in outcome.events
        ),
        "usage": outcome.usage,
        "response": outcome.final_response,
        "worlds": {"initial": initial_world, "final": outcome.world_state},
        "official_score": {
            "partial_credit": score.get("partial_credit", 0.0),
            "task_completed_correctly": score.get("task_completed_correctly", 0.0),
        },
        "assertion_evidence": score.get("assertions", []),
        "terminal_error": outcome.terminal_error,
    }


async def _run(
    tasks: list[str],
    config: dict,
    repetitions: int,
    directory: Path,
    runtime_factory: RuntimeFactory,
) -> None:
    if repetitions < 1:
        raise ValueError("Repetitions must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    existing = _existing_pairs(directory)
    catalog = TaskCatalog.from_sales_dataset()
    for task_id in tasks:
        initial_world = catalog.get_task(task_id).info["initial_state"]
        for repetition in range(1, repetitions + 1):
            pair = (config["identity"], task_id, repetition)
            if pair in existing:
                continue
            while True:
                started_at = datetime.now(timezone.utc).isoformat()
                started = monotonic()
                outcome = await runtime_factory().run(
                    RuntimeRequest(task_id=task_id, model_name=config["model"])
                )
                finished_at = datetime.now(timezone.utc).isoformat()
                if _infrastructure_failure(outcome):
                    continue
                record = _record(
                    outcome,
                    config=config,
                    repetition=repetition,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=(monotonic() - started) * 1000,
                    initial_world=initial_world,
                )
                task_slug = task_id.replace(".", "-")
                filename = f"{config['identity']}_{task_slug}_r{repetition:03}.json"
                _write_json(directory / filename, record)
                existing.add(pair)
                break


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "mean": round(statistics.mean(values), 3),
        "sample_standard_deviation": round(statistics.stdev(values), 3)
        if len(values) > 1
        else 0.0,
        "minimum": min(values),
        "maximum": max(values),
    }


def _range(values: list[float]) -> dict[str, float]:
    return {
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def _load_run_artifacts(directory: Path) -> list[tuple[str, dict]]:
    artifacts = []
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("artifact_type") == "agent_evaluation_run":
            artifacts.append((path.name, value))
    return artifacts


def _report_groups(directory: Path) -> list[dict]:
    grouped = defaultdict(list)
    for filename, record in _load_run_artifacts(directory):
        key = (record["configuration"]["identity"], record["task_id"])
        grouped[key].append((filename, record))
    groups = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda item: (item[1]["repetition"], item[0]))
        records = [record for _, record in rows]
        strict_count = sum(
            record["official_score"]["task_completed_correctly"] == 1.0
            for record in records
        )
        count = len(records)
        groups.append(
            {
                "configuration": records[0]["configuration"],
                "task_id": key[1],
                "coverage": {
                    "scorable_count": count,
                    "repetitions": [record["repetition"] for record in records],
                },
                "strict_completion": {
                    "count": strict_count,
                    "percentage": round(100 * strict_count / count, 3),
                },
                "partial_credit": _distribution(
                    [record["official_score"]["partial_credit"] for record in records]
                ),
                "tokens": _range(
                    [record["usage"]["total_tokens"] for record in records]
                ),
                "duration_ms": _range(
                    [record["timing"]["duration_ms"] for record in records]
                ),
                "model_turns": {
                    "median": statistics.median(
                        [record["model_turn_count"] for record in records]
                    ),
                    "maximum": max(record["model_turn_count"] for record in records),
                },
                "tool_calls": {
                    "median": statistics.median(
                        [record["tool_call_count"] for record in records]
                    ),
                    "maximum": max(record["tool_call_count"] for record in records),
                },
                "runs_containing_tool_errors": sum(
                    record["contains_tool_errors"] for record in records
                ),
                "termination_reasons": dict(
                    sorted(
                        Counter(
                            record["termination_reason"] for record in records
                        ).items()
                    )
                ),
                "artifacts": [filename for filename, _ in rows],
            }
        )
    return groups


def _markdown(groups: list[dict]) -> str:
    lines = ["# Offline Evaluation Report", "", "## Configuration", ""]
    configurations = {}
    for group in groups:
        config = group["configuration"]
        configurations[config["identity"]] = config
    for identity in sorted(configurations):
        config = configurations[identity]
        lines.extend(
            [
                f"### `{identity}`",
                "",
                f"- Model: `{config['model']}`",
                f"- Harness: `{config['harness_version']}`",
                f"- Prompts: `{config['prompt_version']}`",
                f"- Protocol: `{config['evaluation_protocol_version']}`",
                "- Execution limits: `"
                + json.dumps(
                    config["execution_limits"], sort_keys=True, separators=(",", ":")
                )
                + "`",
                "",
            ]
        )
    lines.extend(
        [
            "## Coverage",
            "",
            "| Configuration | Task | Scorable | Repetitions |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for group in groups:
        coverage = group["coverage"]
        repetitions = ", ".join(map(str, coverage["repetitions"]))
        lines.append(
            f"| `{group['configuration']['identity']}` | `{group['task_id']}` | "
            f"{coverage['scorable_count']} | {repetitions} |"
        )
    lines.extend(
        [
            "",
            "## Panel Summary",
            "",
            "| Configuration | Task | Strict | Partial mean | Token median | Duration median (ms) |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for group in groups:
        strict = group["strict_completion"]
        lines.append(
            f"| `{group['configuration']['identity']}` | `{group['task_id']}` | "
            f"{strict['count']}/{group['coverage']['scorable_count']} ({strict['percentage']:.3f}%) | "
            f"{group['partial_credit']['mean']:.3f} | {group['tokens']['median']} | "
            f"{group['duration_ms']['median']} |"
        )
    lines.extend(["", "## Per-task Results", ""])
    for group in groups:
        partial = group["partial_credit"]
        lines.extend(
            [
                f"### `{group['task_id']}` — `{group['configuration']['identity']}`",
                "",
                f"- Partial credit: mean {partial['mean']:.3f}, sample SD "
                f"{partial['sample_standard_deviation']:.3f}, range "
                f"{partial['minimum']}–{partial['maximum']}.",
                f"- Tokens: median {group['tokens']['median']}, range "
                f"{group['tokens']['minimum']}–{group['tokens']['maximum']}.",
                f"- Duration (ms): median {group['duration_ms']['median']}, range "
                f"{group['duration_ms']['minimum']}–{group['duration_ms']['maximum']}.",
                f"- Model turns: median {group['model_turns']['median']}, maximum "
                f"{group['model_turns']['maximum']}.",
                f"- Tool calls: median {group['tool_calls']['median']}, maximum "
                f"{group['tool_calls']['maximum']}.",
                f"- Runs containing tool errors: {group['runs_containing_tool_errors']}.",
                "",
            ]
        )
    lines.extend(["## Termination Evidence", ""])
    for group in groups:
        reasons = ", ".join(
            f"`{reason}`: {count}"
            for reason, count in group["termination_reasons"].items()
        )
        lines.append(
            f"- `{group['configuration']['identity']}` / `{group['task_id']}` — {reasons}."
        )
    lines.extend(["", "## Run Artifacts", ""])
    for group in groups:
        lines.append(
            f"### `{group['configuration']['identity']}` / `{group['task_id']}`"
        )
        lines.append("")
        lines.extend(f"- [{name}]({name})" for name in group["artifacts"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_report(directory: Path, markdown_path: Path, json_path: Path) -> None:
    groups = _report_groups(directory)
    if not groups:
        raise ValueError("No scorable evaluation artifacts found")
    _write_text(markdown_path, _markdown(groups))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(json_path, {"schema_version": 1, "groups": groups})


def main(
    argv: list[str] | None = None, *, runtime_factory: RuntimeFactory | None = None
) -> None:
    args = _parser().parse_args(argv)
    if args.command == "run":
        tasks, config = _load_inputs(args.manifest, args.config)
        factory = runtime_factory or (
            lambda: PlannerExecutorRuntime(model_client=OpenAIModelClient())
        )
        asyncio.run(_run(tasks, config, args.repetitions, args.artifacts_dir, factory))
    elif args.command == "report":
        _write_report(args.artifacts_dir, args.markdown, args.json)


if __name__ == "__main__":
    main()
