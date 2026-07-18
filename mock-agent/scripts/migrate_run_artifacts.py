from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from mock_agent.artifacts import (
    ARTIFACT_TYPE,
    RunArtifact,
    atomic_write_json,
    read_artifact,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIRECTORY = REPOSITORY_ROOT / "mock-agent" / "results"
EVALUATION_DIRECTORY = RESULTS_DIRECTORY / "evaluation"
RUNS_DIRECTORY = RESULTS_DIRECTORY / "runs"
LEGACY_SESSIONS_DIRECTORY = REPOSITORY_ROOT / "sessions"


def _is_canonical(path: Path) -> bool:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value.get("artifact_type") == ARTIFACT_TYPE


def _migrate_in_place(path: Path) -> RunArtifact:
    raw = json.loads(path.read_text(encoding="utf-8"))
    missing_termination_reason = (
        raw.get("artifact_type") == ARTIFACT_TYPE
        and raw.get("status") in {"completed", "stopped", "failed", "interrupted"}
        and raw.get("termination_reason") is None
    )
    if missing_termination_reason:
        raw["termination_reason"] = "legacy_unknown"
        raw["configuration"]["legacy_termination_reason_unavailable"] = True
        artifact = RunArtifact.from_dict(raw)
    else:
        artifact = read_artifact(path, enrich_task=True)
    task = dict(artifact.task)
    removed_duplicate_world = task.pop("initial_world", None) is not None
    missing_evidence_marker = (
        raw.get("artifact_type") == ARTIFACT_TYPE
        and "assertion_evidence_available" not in raw.get("evaluation", {})
    )
    if removed_duplicate_world:
        artifact = replace(artifact, task=task)
    if (
        not _is_canonical(path)
        or removed_duplicate_world
        or missing_evidence_marker
        or missing_termination_reason
    ):
        atomic_write_json(path, artifact.to_dict())
    return artifact


def main() -> None:
    evaluation_run_ids = set()
    for path in sorted(EVALUATION_DIRECTORY.glob("*.json")):
        if path.name == "report.json":
            continue
        artifact = _migrate_in_place(path)
        if artifact.evaluation.context is None:
            raise ValueError(f"Expected evaluation metadata in {path}")
        evaluation_run_ids.add(artifact.run_id)

    for path in sorted((RESULTS_DIRECTORY / "development").glob("*.json")):
        _migrate_in_place(path)

    configured_run = (
        RESULTS_DIRECTORY
        / "sales.zoom_calendar_conflict.gpt-5.6-sol.configured-run.json"
    )
    if configured_run.exists():
        _migrate_in_place(configured_run)

    RUNS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for path in sorted(RUNS_DIRECTORY.glob("*.json")):
        _migrate_in_place(path)
    for path in sorted(LEGACY_SESSIONS_DIRECTORY.glob("*.json")):
        artifact = read_artifact(path, enrich_task=True)
        if path.name.startswith("evaluation_"):
            if artifact.run_id not in evaluation_run_ids:
                raise ValueError(f"Cannot prove duplicate evaluation artifact: {path}")
            path.unlink()
            continue
        destination = RUNS_DIRECTORY / f"{artifact.run_id}.json"
        if destination.exists():
            existing = RunArtifact.from_dict(
                json.loads(destination.read_text(encoding="utf-8"))
            )
            if existing != artifact:
                raise ValueError(f"Conflicting canonical artifact: {destination}")
        else:
            atomic_write_json(destination, artifact.to_dict())
        path.unlink()

    keep = LEGACY_SESSIONS_DIRECTORY / ".gitkeep"
    if keep.exists() and not any(
        path != keep for path in LEGACY_SESSIONS_DIRECTORY.iterdir()
    ):
        keep.unlink()


if __name__ == "__main__":
    main()
