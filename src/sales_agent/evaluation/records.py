from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from sales_agent.artifacts import ArtifactValidationError, RunArtifact, read_artifact
from sales_agent.plan_state_runtime import PLAN_STATE_LIMITS

CONFIGURATION_FIELDS = (
    "model",
    "harness_version",
    "prompt_version",
    "evaluation_protocol_version",
    "execution_limits",
)


@dataclass(frozen=True)
class EvaluationManifest:
    tasks: tuple[str, ...]
    metadata: dict[str, Any]

    @classmethod
    def read(cls, path: Path) -> EvaluationManifest:
        value = json.loads(path.read_text(encoding="utf-8"))
        tasks = value.get("tasks")
        if (
            not isinstance(tasks, list)
            or not tasks
            or not all(isinstance(task, str) and task for task in tasks)
        ):
            raise ValueError("Manifest must contain a non-empty string task list")
        if len(set(tasks)) != len(tasks):
            raise ValueError("Manifest task IDs must be unique")
        return cls(tuple(tasks), {key: value[key] for key in sorted(value) if key != "tasks"})


@dataclass(frozen=True)
class EvaluationConfiguration:
    values: dict[str, Any]
    identity: str

    @classmethod
    def read(cls, path: Path) -> EvaluationConfiguration:
        value = json.loads(path.read_text(encoding="utf-8"))
        missing = [field for field in CONFIGURATION_FIELDS if field not in value]
        if missing:
            raise ValueError(f"Configuration is missing: {', '.join(missing)}")
        configured_identity = value.get("identity")
        if configured_identity is not None and (
            not isinstance(configured_identity, str)
            or len(configured_identity) != 64
            or any(character not in "0123456789abcdef" for character in configured_identity)
        ):
            raise ValueError("Configured identity must be a lowercase SHA-256 digest")
        identity_values = {key: item for key, item in value.items() if key != "identity"}
        canonical = json.dumps(identity_values, sort_keys=True, separators=(",", ":"))
        derived_identity = sha256(canonical.encode()).hexdigest()
        if configured_identity and configured_identity != derived_identity:
            raise ValueError("Configured identity does not match the configuration payload")
        return cls(value, configured_identity or derived_identity)

    def require_frozen_execution_limits(self) -> None:
        if self.values["execution_limits"] != PLAN_STATE_LIMITS:
            raise ValueError(f"Execution limits must equal the frozen limits: {PLAN_STATE_LIMITS}")

    def artifact_values(self) -> dict[str, Any]:
        return {
            **self.values,
            "identity": self.identity,
            "runtime": {
                "id": "custom",
                "label": "Custom agent",
                "version": self.values["harness_version"],
            },
        }

    def matches_artifact(self, artifact_configuration: dict[str, Any]) -> bool:
        return all(
            artifact_configuration.get(field) == self.values[field]
            for field in CONFIGURATION_FIELDS
        )


@dataclass(frozen=True)
class EvaluationRecord:
    filename: str
    artifact: RunArtifact
    configuration_identity: str
    task_id: str
    repetition: int

    @property
    def scorable(self) -> bool:
        score = self.artifact.evaluation.official_score
        return (
            self.artifact.evaluation.available
            and {
                "partial_credit",
                "task_completed_correctly",
            }
            <= score.keys()
        )


def load_records(directory: Path) -> list[EvaluationRecord]:
    """Read canonical evaluator observations."""

    records: list[EvaluationRecord] = []
    for path in sorted(directory.glob("*.json")):
        try:
            artifact = read_artifact(path)
        except (ArtifactValidationError, KeyError, TypeError, ValueError):
            continue
        context = artifact.evaluation.context or {}
        has_metadata = "configuration_identity" in context or "repetition" in context
        if not has_metadata:
            continue
        identity = context.get("configuration_identity")
        repetition = context.get("repetition")
        configured_identity = artifact.configuration.get("identity")
        if not isinstance(identity, str) or not identity:
            raise ValueError(f"{path.name}: missing evaluation configuration identity")
        if identity != configured_identity:
            raise ValueError(
                f"{path.name}: evaluation identity {identity!r} does not match "
                f"artifact configuration identity {configured_identity!r}"
            )
        if not isinstance(repetition, int) or isinstance(repetition, bool):
            raise ValueError(f"{path.name}: repetition must be an integer")
        if context.get("fresh_world") is not True:
            raise ValueError(f"{path.name}: evaluation fresh_world must be true")
        records.append(
            EvaluationRecord(
                filename=path.name,
                artifact=artifact,
                configuration_identity=identity,
                task_id=artifact.task["task_id"],
                repetition=repetition,
            )
        )
    return records


def completed_triples(
    directory: Path, config: EvaluationConfiguration | None = None
) -> set[tuple[str, str, int]]:
    records = load_records(directory)
    if config:
        mismatches = [
            record.filename
            for record in records
            if record.configuration_identity == config.identity
            and not config.matches_artifact(record.artifact.configuration)
        ]
        if mismatches:
            raise ValueError("Configuration identity payload mismatch: " + ", ".join(mismatches))
    return {
        (record.configuration_identity, record.task_id, record.repetition) for record in records
    }
