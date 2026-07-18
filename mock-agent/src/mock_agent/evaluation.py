from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import statistics
from time import monotonic
from typing import Callable

from dotenv import load_dotenv

from mock_agent.adapter import AutomationBenchAdapter
from mock_agent.artifacts import (
    ArtifactValidationError,
    RunArtifactStore,
    artifact_from_outcome,
    artifact_to_report_record,
    atomic_write_json,
    atomic_write_text,
    read_artifact,
    task_snapshot,
)
from mock_agent.catalog import TaskCatalog
from mock_agent.contract import AgentRuntime, EventKind, RuntimeOutcome, RuntimeRequest
from mock_agent.model import OpenAIModelClient
from mock_agent.plan_state_runtime import PLAN_STATE_LIMITS, PlanStateRuntime


RuntimeFactory = Callable[[], AgentRuntime]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parent
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
    report.add_argument("--task-id", dest="task_ids", action="append")
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
    if config["execution_limits"] != PLAN_STATE_LIMITS:
        raise ValueError(
            f"Execution limits must equal the frozen limits: {PLAN_STATE_LIMITS}"
        )
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return tasks, {**config, "identity": sha256(canonical.encode()).hexdigest()}


def _existing_pairs(directory: Path) -> set[tuple[str, str, int]]:
    return {
        (
            record["configuration"]["identity"],
            record["task_id"],
            int(record["repetition"]),
        )
        for _, record in _load_run_artifacts(directory, include_unscorable=True)
    }


def _infrastructure_failure(outcome: RuntimeOutcome) -> bool:
    return any(
        event.kind is EventKind.MODEL_ERROR
        and isinstance(event.content, dict)
        and event.content.get("infrastructure_failure") is True
        for event in outcome.events
    )


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
    resuming = any(
        identity == config["identity"]
        and task_id in tasks
        and repetition <= repetitions
        for identity, task_id, repetition in existing
    )
    catalog = TaskCatalog.from_sales_dataset()
    adapter = AutomationBenchAdapter(catalog=catalog)
    store = RunArtifactStore(directory)
    artifact_config = {
        **config,
        "runtime": {
            "id": "custom",
            "label": "Custom agent",
            "version": config["harness_version"],
        },
    }
    for task_id in tasks:
        task = catalog.get_task(task_id)
        initial_world = task.info["initial_state"]
        tools = adapter.open(task_id).agent_task.tools
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
        for repetition in range(1, repetitions + 1):
            pair = (config["identity"], task_id, repetition)
            if pair in existing:
                continue
            infrastructure_replacements = 0
            while True:
                started_at = datetime.now(timezone.utc).isoformat()
                started = monotonic()
                outcome = await runtime_factory().run(
                    RuntimeRequest(task_id=task_id, model_name=config["model"])
                )
                finished_at = datetime.now(timezone.utc).isoformat()
                if _infrastructure_failure(outcome):
                    infrastructure_replacements += 1
                    continue
                artifact = artifact_from_outcome(
                    outcome,
                    task=snapshot,
                    configuration=artifact_config,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=(monotonic() - started) * 1000,
                    initial_world=initial_world,
                    evaluation_context={
                        "configuration_identity": config["identity"],
                        "repetition": repetition,
                        "fresh_world": True,
                        "resumed": resuming,
                        "infrastructure_replacement_count": infrastructure_replacements,
                    },
                )
                task_slug = task_id.replace(".", "-")
                filename = f"{config['identity']}_{task_slug}_r{repetition:03}.json"
                store.write(artifact, filename=filename)
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


def _load_run_artifacts(
    directory: Path,
    task_ids: list[str] | None = None,
    *,
    include_unscorable: bool = False,
) -> list[tuple[str, dict]]:
    artifacts = []
    for path in sorted(directory.glob("*.json")):
        try:
            artifact = read_artifact(path)
            record = artifact_to_report_record(artifact)
        except (ArtifactValidationError, KeyError, TypeError, ValueError):
            continue
        repetition = record.get("repetition")
        if isinstance(repetition, int) and (
            task_ids is None or record.get("task_id") in task_ids
        ) and (
            include_unscorable
            or (
                record["evaluation_available"]
                and {
                    "partial_credit",
                    "task_completed_correctly",
                }
                <= record["official_score"].keys()
            )
        ):
            artifacts.append((path.name, record))
    return artifacts


def _report_groups(directory: Path, task_ids: list[str] | None = None) -> list[dict]:
    grouped = defaultdict(list)
    for filename, record in _load_run_artifacts(directory, task_ids):
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


def _panel_summaries(directory: Path, task_ids: list[str] | None = None) -> list[dict]:
    grouped = defaultdict(list)
    for _, record in _load_run_artifacts(directory, task_ids):
        grouped[record["configuration"]["identity"]].append(record)
    panels = []
    for identity in sorted(grouped):
        records = grouped[identity]
        count = len(records)
        strict_count = sum(
            record["official_score"]["task_completed_correctly"] == 1.0
            for record in records
        )
        panels.append(
            {
                "configuration": records[0]["configuration"],
                "coverage": {
                    "task_count": len({record["task_id"] for record in records}),
                    "scorable_count": count,
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
            }
        )
    return panels


def _markdown(groups: list[dict], panels: list[dict]) -> str:
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
            "| Configuration | Tasks | Scorable | Strict | Partial mean | Token median | Duration median (ms) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for panel in panels:
        coverage = panel["coverage"]
        strict = panel["strict_completion"]
        lines.append(
            f"| `{panel['configuration']['identity']}` | {coverage['task_count']} | "
            f"{coverage['scorable_count']} | {strict['count']}/{coverage['scorable_count']} "
            f"({strict['percentage']:.3f}%) | {panel['partial_credit']['mean']:.3f} | "
            f"{panel['tokens']['median']} | {panel['duration_ms']['median']} |"
        )
    lines.extend(["", "## Per-task Results", ""])
    for group in groups:
        partial = group["partial_credit"]
        lines.extend(
            [
                f"### `{group['task_id']}` — `{group['configuration']['identity']}`",
                "",
                f"- Strict completion: {group['strict_completion']['count']}/"
                f"{group['coverage']['scorable_count']} "
                f"({group['strict_completion']['percentage']:.3f}%).",
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


def _write_report(
    directory: Path,
    markdown_path: Path,
    json_path: Path,
    task_ids: list[str] | None = None,
) -> None:
    groups = _report_groups(directory, task_ids)
    if not groups:
        raise ValueError("No scorable evaluation artifacts found")
    panels = _panel_summaries(directory, task_ids)
    atomic_write_text(markdown_path, _markdown(groups, panels))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        json_path, {"schema_version": 1, "panels": panels, "groups": groups}
    )


def main(
    argv: list[str] | None = None, *, runtime_factory: RuntimeFactory | None = None
) -> None:
    args = _parser().parse_args(argv)
    if args.command == "run":
        load_dotenv(PROJECT_ROOT / ".env")
        load_dotenv(REPOSITORY_ROOT / ".env")
        tasks, config = _load_inputs(args.manifest, args.config)
        factory = runtime_factory or (
            lambda: PlanStateRuntime(model_client=OpenAIModelClient())
        )
        asyncio.run(
            _run(
                tasks,
                config,
                args.repetitions,
                args.artifacts_dir,
                factory,
            )
        )
    elif args.command == "report":
        _write_report(args.artifacts_dir, args.markdown, args.json, args.task_ids)


if __name__ == "__main__":
    main()
