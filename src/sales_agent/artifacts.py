from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from sales_agent.catalog import TaskDefinition
from sales_agent.contract import EventKind, RuntimeOutcome

ARTIFACT_TYPE = "run_artifact"
SCHEMA_VERSION = 1
TERMINAL_STATUSES = frozenset({"completed", "stopped", "failed", "interrupted"})


class ArtifactError(ValueError):
    """Base class for canonical artifact failures."""


class ArtifactValidationError(ArtifactError):
    """Raised when an artifact does not satisfy a supported schema."""


class UnsupportedArtifactVersionError(ArtifactError):
    """Raised when a canonical artifact uses an unknown schema version."""


class ImmutableArtifactError(RuntimeError):
    """Raised when an artifact destination already exists."""


@dataclass(frozen=True)
class ArtifactTiming:
    started_at: str
    updated_at: str
    finished_at: str | None
    duration_ms: float | None


@dataclass(frozen=True)
class ArtifactSummary:
    provider_retry_count: int
    model_turn_count: int
    tool_call_count: int
    contains_tool_errors: bool


@dataclass(frozen=True)
class ArtifactWorlds:
    initial: dict[str, Any]
    final: dict[str, Any] | None


@dataclass(frozen=True)
class ArtifactEvaluation:
    available: bool
    official_score: dict[str, Any]
    assertion_evidence: tuple[dict[str, Any], ...]
    context: dict[str, Any] | None = None
    assertion_evidence_available: bool = True


@dataclass(frozen=True)
class RunArtifact:
    """Immutable, typed serialization boundary shared by every run consumer."""

    run_id: str
    task: dict[str, Any]
    configuration: dict[str, Any]
    timing: ArtifactTiming
    status: str
    termination_reason: str | None
    trace: tuple[dict[str, Any], ...]
    summary: ArtifactSummary
    usage: dict[str, int] | None
    final_response: Any
    terminal_error: str | None
    evaluation_error: str | None
    worlds: ArtifactWorlds
    evaluation: ArtifactEvaluation

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "task": copy.deepcopy(self.task),
            "configuration": copy.deepcopy(self.configuration),
            "timing": asdict(self.timing),
            "status": self.status,
            "termination_reason": self.termination_reason,
            "trace": copy.deepcopy(list(self.trace)),
            "summary": asdict(self.summary),
            "usage": copy.deepcopy(self.usage),
            "final_response": copy.deepcopy(self.final_response),
            "terminal_error": self.terminal_error,
            "evaluation_error": self.evaluation_error,
            "worlds": asdict(self.worlds),
            "evaluation": {
                "available": self.evaluation.available,
                "official_score": copy.deepcopy(self.evaluation.official_score),
                "assertion_evidence": copy.deepcopy(list(self.evaluation.assertion_evidence)),
                "context": copy.deepcopy(self.evaluation.context),
                "assertion_evidence_available": (self.evaluation.assertion_evidence_available),
            },
        }

    @classmethod
    def from_dict(cls, value: Any) -> RunArtifact:
        if not isinstance(value, dict):
            raise ArtifactValidationError("Artifact must be a JSON object")
        if value.get("artifact_type") != ARTIFACT_TYPE:
            raise ArtifactValidationError("Artifact type must be run_artifact")
        version = value.get("schema_version")
        if version != SCHEMA_VERSION:
            raise UnsupportedArtifactVersionError(
                f"Unsupported run artifact schema version: {version!r}"
            )
        run_id = _required_string(value, "run_id")
        task = _required_dict(value, "task")
        _required_string(task, "task_id")
        _required_string(task, "name")
        for key in ("prompt", "tools", "assertions", "tool_definitions"):
            if not isinstance(task.get(key), list):
                raise ArtifactValidationError(f"task.{key} must be a list")
        configuration = _required_dict(value, "configuration")
        for key in (
            "identity",
            "model",
            "harness_version",
            "prompt_version",
            "evaluation_protocol_version",
        ):
            _required_string(configuration, key)
        _required_dict(configuration, "execution_limits")
        runtime = _required_dict(configuration, "runtime")
        for key in ("id", "label", "version"):
            _required_string(runtime, key)
        timing_value = _required_dict(value, "timing")
        timing = ArtifactTiming(
            started_at=_required_string(timing_value, "started_at"),
            updated_at=_required_string(timing_value, "updated_at"),
            finished_at=_optional_string(timing_value, "finished_at"),
            duration_ms=_optional_number(timing_value, "duration_ms"),
        )
        status = _required_string(value, "status")
        if status not in {"running", *TERMINAL_STATUSES}:
            raise ArtifactValidationError(f"Unsupported run status: {status!r}")
        if status in TERMINAL_STATUSES and timing.finished_at is None:
            raise ArtifactValidationError("Terminal artifacts require timing.finished_at")
        if status == "running" and timing.finished_at is not None:
            raise ArtifactValidationError("Running artifacts cannot have timing.finished_at")
        termination_reason = _optional_string(value, "termination_reason")
        if status in TERMINAL_STATUSES and termination_reason is None:
            raise ArtifactValidationError(
                "Terminal artifacts require an explicit termination_reason"
            )
        if status == "running" and termination_reason is not None:
            raise ArtifactValidationError("Running artifacts cannot have a termination_reason")
        trace_value = value.get("trace")
        if not isinstance(trace_value, list):
            raise ArtifactValidationError("trace must be a list")
        trace = tuple(_validate_trace(trace_value, run_id))
        summary_value = _required_dict(value, "summary")
        summary = ArtifactSummary(
            provider_retry_count=_required_nonnegative_int(summary_value, "provider_retry_count"),
            model_turn_count=_required_nonnegative_int(summary_value, "model_turn_count"),
            tool_call_count=_required_nonnegative_int(summary_value, "tool_call_count"),
            contains_tool_errors=_required_bool(summary_value, "contains_tool_errors"),
        )
        usage = value.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ArtifactValidationError("usage must be an object or null")
        worlds_value = _required_dict(value, "worlds")
        initial = _required_dict(worlds_value, "initial")
        final = worlds_value.get("final")
        if final is not None and not isinstance(final, dict):
            raise ArtifactValidationError("worlds.final must be an object or null")
        evaluation_value = _required_dict(value, "evaluation")
        available = _required_bool(evaluation_value, "available")
        official_score = _required_dict(evaluation_value, "official_score")
        evidence = evaluation_value.get("assertion_evidence")
        if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
            raise ArtifactValidationError("evaluation.assertion_evidence must be a list")
        context = evaluation_value.get("context")
        if context is not None and not isinstance(context, dict):
            raise ArtifactValidationError("evaluation.context must be an object or null")
        if context is not None:
            _required_string(context, "configuration_identity")
            repetition = _required_nonnegative_int(context, "repetition")
            if repetition == 0:
                raise ArtifactValidationError("evaluation.context.repetition must be positive")
            _required_bool(context, "fresh_world")
            _required_bool(context, "resumed")
            _required_nonnegative_int(context, "infrastructure_replacement_count")
        assertion_evidence_available = evaluation_value.get("assertion_evidence_available", True)
        if not isinstance(assertion_evidence_available, bool):
            raise ArtifactValidationError(
                "evaluation.assertion_evidence_available must be a boolean"
            )
        return cls(
            run_id=run_id,
            task=copy.deepcopy(task),
            configuration=copy.deepcopy(configuration),
            timing=timing,
            status=status,
            termination_reason=termination_reason,
            trace=copy.deepcopy(trace),
            summary=summary,
            usage=copy.deepcopy(usage),
            final_response=copy.deepcopy(value.get("final_response")),
            terminal_error=_optional_string(value, "terminal_error"),
            evaluation_error=_optional_string(value, "evaluation_error"),
            worlds=ArtifactWorlds(initial=copy.deepcopy(initial), final=copy.deepcopy(final)),
            evaluation=ArtifactEvaluation(
                available=available,
                official_score=copy.deepcopy(official_score),
                assertion_evidence=copy.deepcopy(tuple(evidence)),
                context=copy.deepcopy(context),
                assertion_evidence_available=assertion_evidence_available,
            ),
        )


def task_snapshot(
    task: TaskDefinition, *, tool_definitions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "task_id": task.summary.task_id,
        "name": task.summary.task_id.removeprefix("sales.").replace("_", " ").title(),
        "example_id": task.summary.example_id,
        "prompt": [asdict(message) for message in task.summary.prompt],
        "tools": list(task.summary.tools),
        "assertion_count": task.summary.assertion_count,
        "assertions": copy.deepcopy(task.info["assertions"]),
        "tool_definitions": copy.deepcopy(tool_definitions or []),
    }


def configuration_identity(configuration: dict[str, Any]) -> str:
    canonical = json.dumps(
        {key: value for key, value in configuration.items() if key != "identity"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode()).hexdigest()


def summarize_trace(trace: tuple[dict[str, Any], ...]) -> ArtifactSummary:
    return ArtifactSummary(
        provider_retry_count=sum(
            event.get("kind") == EventKind.PROVIDER_RETRY.value for event in trace
        ),
        model_turn_count=sum(event.get("usage") is not None for event in trace),
        tool_call_count=sum(event.get("kind") == EventKind.TOOL_CALL.value for event in trace),
        contains_tool_errors=any(
            event.get("kind") == EventKind.TOOL_ERROR.value for event in trace
        ),
    )


def artifact_from_outcome(
    outcome: RuntimeOutcome,
    *,
    task: dict[str, Any],
    configuration: dict[str, Any],
    started_at: str,
    finished_at: str,
    duration_ms: float,
    initial_world: dict[str, Any],
    evaluation_context: dict[str, Any] | None = None,
) -> RunArtifact:
    trace = tuple(asdict(event) for event in outcome.events)
    score = copy.deepcopy(outcome.score or {})
    assertions = tuple(score.pop("assertions", []))
    return RunArtifact(
        run_id=outcome.run_id,
        task=copy.deepcopy(task),
        configuration=copy.deepcopy(configuration),
        timing=ArtifactTiming(
            started_at=started_at,
            updated_at=finished_at,
            finished_at=finished_at,
            duration_ms=round(duration_ms, 3),
        ),
        status=outcome.status.value,
        termination_reason=(
            outcome.termination_reason.value
            if outcome.termination_reason
            else {
                "completed": "goal_completed",
                "stopped": "cancelled",
                "failed": "runtime_error",
            }[outcome.status.value]
        ),
        trace=trace,
        summary=summarize_trace(trace),
        usage=copy.deepcopy(outcome.usage),
        final_response=copy.deepcopy(outcome.final_response),
        terminal_error=outcome.terminal_error,
        evaluation_error=outcome.evaluation_error,
        worlds=ArtifactWorlds(
            initial=copy.deepcopy(initial_world),
            final=copy.deepcopy(outcome.world_state),
        ),
        evaluation=ArtifactEvaluation(
            available=outcome.score is not None,
            official_score=score,
            assertion_evidence=copy.deepcopy(assertions),
            context=copy.deepcopy(evaluation_context),
            assertion_evidence_available=(
                outcome.score is not None and "assertions" in outcome.score
            ),
        ),
    )


def read_artifact(path: Path) -> RunArtifact:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactValidationError(f"Cannot read artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise ArtifactValidationError("Artifact must be a JSON object")
    return RunArtifact.from_dict(value)


class RunArtifactStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, artifact: RunArtifact, *, filename: str | None = None) -> Path:
        validated = RunArtifact.from_dict(artifact.to_dict())
        resolved_filename = filename or f"{validated.run_id}.json"
        if Path(resolved_filename).name != resolved_filename or not resolved_filename.endswith(
            ".json"
        ):
            raise ArtifactValidationError("Artifact filename must be a JSON basename")
        destination = self.directory / resolved_filename
        if destination.exists():
            raise ImmutableArtifactError(f"Artifact destination already exists: {destination}")
        _atomic_create_json(destination, validated.to_dict())
        return destination


def _atomic_create_json(path: Path, value: Any) -> None:
    payload = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            default=_json_default,
        )
        + "\n"
    )
    _atomic_create_text(path, payload)


def _atomic_create_text(path: Path, payload: str) -> None:
    """Atomically create ``path`` without ever replacing an existing destination."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError as error:
            raise ImmutableArtifactError(f"Artifact destination already exists: {path}") from error
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def atomic_write_json(path: Path, value: Any) -> None:
    payload = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            default=_json_default,
        )
        + "\n"
    )
    atomic_write_text(path, payload)


def atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _validate_trace(trace: list[Any], run_id: str) -> list[dict[str, Any]]:
    validated = []
    previous = 0
    for index, event in enumerate(trace):
        if not isinstance(event, dict):
            raise ArtifactValidationError(f"trace[{index}] must be an object")
        sequence = event.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise ArtifactValidationError(f"trace[{index}].sequence must be an integer")
        if sequence <= previous:
            raise ArtifactValidationError("Trace sequence numbers must be monotonic")
        event_run_id = event.get("run_id")
        if event_run_id is not None and event_run_id != run_id:
            raise ArtifactValidationError("Trace event run_id must match artifact run_id")
        previous = sequence
        validated.append(copy.deepcopy(event))
    return validated


def _required_dict(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ArtifactValidationError(f"{key} must be an object")
    return item


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ArtifactValidationError(f"{key} must be a non-empty string")
    return item


def _optional_string(value: dict[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise ArtifactValidationError(f"{key} must be a string or null")
    return item


def _optional_number(value: dict[str, Any], key: str) -> float | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, (int, float)) or isinstance(item, bool):
        raise ArtifactValidationError(f"{key} must be a number or null")
    return float(item)


def _required_nonnegative_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ArtifactValidationError(f"{key} must be a non-negative integer")
    return item


def _required_bool(value: dict[str, Any], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ArtifactValidationError(f"{key} must be a boolean")
    return item


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Cannot serialize {type(value).__name__}")
