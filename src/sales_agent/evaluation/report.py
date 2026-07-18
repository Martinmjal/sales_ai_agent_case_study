from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sales_agent.artifacts import atomic_write_json, atomic_write_text
from sales_agent.evaluation.records import (
    EvaluationConfiguration,
    EvaluationManifest,
    EvaluationRecord,
    load_records,
)


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "mean": round(statistics.mean(values), 3),
        "sample_standard_deviation": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
        "minimum": min(values),
        "maximum": max(values),
    }


def _range(values: list[float]) -> dict[str, float]:
    return {
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def _report_record(record: EvaluationRecord) -> dict[str, Any]:
    artifact = record.artifact
    return {
        "configuration": artifact.configuration,
        "task_id": artifact.task["task_id"],
        "repetition": record.repetition,
        "timing": {
            "duration_ms": artifact.timing.duration_ms,
        },
        "model_turn_count": artifact.summary.model_turn_count,
        "tool_call_count": artifact.summary.tool_call_count,
        "contains_tool_errors": artifact.summary.contains_tool_errors,
        "usage": artifact.usage,
        "official_score": artifact.evaluation.official_score,
        "termination_reason": artifact.termination_reason,
    }


def _statistics(values: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(values)
    strict_count = sum(row["official_score"]["task_completed_correctly"] == 1.0 for row in values)
    return {
        "strict_completion": {
            "count": strict_count,
            "percentage": round(100 * strict_count / count, 3),
        },
        "partial_credit": _distribution(
            [row["official_score"]["partial_credit"] for row in values]
        ),
        "tokens": _range([row["usage"]["total_tokens"] for row in values]),
        "duration_ms": _range([row["timing"]["duration_ms"] for row in values]),
        "model_turns": {
            "median": statistics.median([row["model_turn_count"] for row in values]),
            "maximum": max(row["model_turn_count"] for row in values),
        },
        "tool_calls": {
            "median": statistics.median([row["tool_call_count"] for row in values]),
            "maximum": max(row["tool_call_count"] for row in values),
        },
        "runs_containing_tool_errors": sum(row["contains_tool_errors"] for row in values),
        "termination_reasons": dict(
            sorted(Counter(row["termination_reason"] for row in values).items())
        ),
    }


def _validate_selection(
    records: list[EvaluationRecord],
    manifest: EvaluationManifest,
    config: EvaluationConfiguration,
    repetitions: int,
    task_ids: list[str] | None,
    exploratory: bool,
) -> tuple[list[EvaluationRecord], dict[str, Any]]:
    if repetitions < 1:
        raise ValueError("Repetitions must be positive")
    if task_ids and not exploratory:
        raise ValueError("--task-id filters require --exploratory mode")
    selected_tasks = list(dict.fromkeys(task_ids or manifest.tasks))
    unknown = [task for task in selected_tasks if task not in manifest.tasks]
    if unknown:
        raise ValueError(f"Task filters are not in the manifest: {', '.join(unknown)}")
    configured = [r for r in records if r.configuration_identity == config.identity]
    mismatches = [
        record.filename
        for record in configured
        if not config.matches_artifact(record.artifact.configuration)
    ]
    if mismatches:
        raise ValueError("Configuration identity payload mismatch: " + ", ".join(mismatches))
    foreign = sorted(
        {
            r.configuration_identity
            for r in records
            if r.task_id in selected_tasks and r.configuration_identity != config.identity
        }
    )
    unexpected = sorted({r.task_id for r in configured if r.task_id not in manifest.tasks})
    out_of_range = sorted(
        (r.task_id, r.repetition, r.filename)
        for r in configured
        if r.task_id in selected_tasks and not 1 <= r.repetition <= repetitions
    )
    if out_of_range:
        details = ", ".join(f"{task}/r{rep} ({name})" for task, rep, name in out_of_range)
        raise ValueError(f"Out-of-range evaluation repetitions: {details}")
    selected = [
        r for r in configured if r.task_id in selected_tasks and 1 <= r.repetition <= repetitions
    ]
    selected_scorable = [record for record in selected if record.scorable]
    by_triple: dict[tuple[str, int], list[EvaluationRecord]] = defaultdict(list)
    for record in selected_scorable:
        by_triple[(record.task_id, record.repetition)].append(record)
    duplicates = {key: value for key, value in by_triple.items() if len(value) > 1}
    if duplicates:
        details = "; ".join(
            f"{task}/r{rep}: {', '.join(r.filename for r in rows)}"
            for (task, rep), rows in sorted(duplicates.items())
        )
        raise ValueError(f"Duplicate evaluation observations: {details}")
    expected = [(task, rep) for task in selected_tasks for rep in range(1, repetitions + 1)]
    scorable = {(r.task_id, r.repetition) for r in selected if r.scorable}
    missing = [(task, rep) for task, rep in expected if (task, rep) not in scorable]
    unscorable = sorted((r.task_id, r.repetition, r.filename) for r in selected if not r.scorable)
    if not exploratory:
        errors = []
        if foreign:
            errors.append("mixed configurations: " + ", ".join(foreign))
        if unexpected:
            errors.append("tasks outside manifest: " + ", ".join(unexpected))
        if missing:
            errors.append(
                "missing scorable observations: "
                + ", ".join(f"{task}/r{rep}" for task, rep in missing)
            )
        if errors:
            raise ValueError("Incomplete final evaluation panel; " + "; ".join(errors))
    if not selected_scorable:
        raise ValueError("No scorable evaluation artifacts found for the selection")
    coverage_complete = not (missing or foreign or unexpected)
    coverage = {
        "coverage_complete": coverage_complete,
        "expected_observation_count": len(expected),
        "scorable_observation_count": len(selected_scorable),
        "missing": [{"task_id": task, "repetition": rep} for task, rep in missing],
        "unscorable": [
            {"task_id": task, "repetition": rep, "artifact": name} for task, rep, name in unscorable
        ],
        "excluded_configuration_identities": foreign,
        "unexpected_tasks": unexpected,
    }
    return selected_scorable, {
        "mode": "exploratory" if exploratory else "final",
        "complete": not exploratory and coverage_complete,
        "selection": {
            "configuration_identity": config.identity,
            "manifest": {**manifest.metadata, "tasks": list(manifest.tasks)},
            "repetitions": repetitions,
            "task_filters": list(task_ids or []),
            "selected_tasks": selected_tasks,
        },
        "coverage": coverage,
    }


def _groups(
    records: list[EvaluationRecord],
    directory: Path,
    report_directory: Path,
    viewer_base_url: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[EvaluationRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.configuration_identity, record.task_id)].append(record)
    groups = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda row: (row.repetition, row.filename))
        values = [_report_record(row) for row in rows]
        count = len(values)
        groups.append(
            {
                "configuration": values[0]["configuration"],
                "task_id": key[1],
                "coverage": {
                    "scorable_count": count,
                    "repetitions": [row.repetition for row in rows],
                },
                **_statistics(values),
                "artifacts": [
                    {
                        "filename": row.filename,
                        "run_id": row.artifact.run_id,
                        "viewer_url": f"{viewer_base_url.rstrip('/')}/runs/{quote(row.artifact.run_id, safe='')}",
                        "path": Path(
                            os.path.relpath(
                                (directory / row.filename).resolve(),
                                report_directory.resolve(),
                            )
                        ).as_posix(),
                    }
                    for row in rows
                ],
            }
        )
    return groups


def _panel(records: list[EvaluationRecord]) -> list[dict[str, Any]]:
    values = [_report_record(record) for record in records]
    return [
        {
            "configuration": values[0]["configuration"],
            "coverage": {
                "task_count": len({row["task_id"] for row in values}),
                "scorable_count": len(values),
            },
            **_statistics(values),
        }
    ]


def _markdown(report: dict[str, Any]) -> str:
    selection, coverage = report["selection"], report["coverage"]
    title = "# Offline Evaluation Report"
    if report["mode"] == "exploratory":
        title += " — INCOMPLETE EXPLORATORY ANALYSIS"
    lines = [title, "", "## Report Status", ""]
    if report["mode"] == "exploratory":
        lines += ["> This output is exploratory and is not a complete final panel.", ""]
    lines += [
        f"- Mode: `{report['mode']}`",
        f"- Complete: `{'yes' if report['complete'] else 'no'}`",
        f"- Configuration: `{selection['configuration_identity']}`",
        f"- Expected repetitions per selected task: {selection['repetitions']}",
        "- Applied task filters: "
        + (", ".join(f"`{x}`" for x in selection["task_filters"]) or "none"),
        f"- Coverage complete: `{'yes' if coverage['coverage_complete'] else 'no'}`",
        "",
        "## Configuration",
        "",
        "```json",
        json.dumps(report["panels"][0]["configuration"], indent=2, sort_keys=True),
        "```",
        "",
        "## Coverage",
        "",
        "```json",
        json.dumps({"selection": selection, "coverage": coverage}, indent=2, sort_keys=True),
        "```",
        "",
        "## Panel Summary",
        "",
        "```json",
        json.dumps(report["panels"], indent=2, sort_keys=True),
        "```",
        "",
        "## Per-task Results",
        "",
    ]
    config = report["panels"][0]["configuration"]
    for group in report["groups"]:
        lines += [
            f"### `{group['task_id']}` — `{config['identity']}`",
            "",
            "```json",
            json.dumps(
                {
                    key: value
                    for key, value in group.items()
                    if key not in {"configuration", "artifacts"}
                },
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
        ]
    lines += ["## Termination Evidence", ""]
    for group in report["groups"]:
        reasons = ", ".join(
            f"`{reason}`: {count}" for reason, count in group["termination_reasons"].items()
        )
        lines.append(f"- `{config['identity']}` / `{group['task_id']}` — {reasons}.")
    lines += ["", "## Run Artifacts", ""]
    for group in report["groups"]:
        lines += [f"### `{config['identity']}` / `{group['task_id']}`", ""]
        lines += [
            f"- [View run]({artifact['viewer_url']}) · [{artifact['filename']}]({artifact['path']})"
            for artifact in group["artifacts"]
        ]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(
    directory: Path,
    markdown_path: Path,
    json_path: Path,
    manifest: EvaluationManifest,
    config: EvaluationConfiguration,
    repetitions: int,
    *,
    task_ids: list[str] | None = None,
    exploratory: bool = False,
    viewer_base_url: str = "http://127.0.0.1:8000",
) -> None:
    if markdown_path.parent.resolve() != json_path.parent.resolve():
        raise ValueError("Markdown and JSON reports must share an output directory")
    records, metadata = _validate_selection(
        load_records(directory), manifest, config, repetitions, task_ids, exploratory
    )
    report = {
        "schema_version": 2,
        **metadata,
        "panels": _panel(records),
        "groups": _groups(records, directory, json_path.parent, viewer_base_url),
    }
    atomic_write_text(markdown_path, _markdown(report))
    atomic_write_json(json_path, report)
