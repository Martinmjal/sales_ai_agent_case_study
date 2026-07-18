from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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
    """Raised when a terminal artifact or an existing trace event would change."""


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


def active_artifact(
    *,
    run_id: str,
    task: dict[str, Any],
    configuration: dict[str, Any],
    started_at: str,
    initial_world: dict[str, Any],
) -> RunArtifact:
    return RunArtifact(
        run_id=run_id,
        task=copy.deepcopy(task),
        configuration=copy.deepcopy(configuration),
        timing=ArtifactTiming(started_at, started_at, None, None),
        status="running",
        termination_reason=None,
        trace=(),
        summary=summarize_trace(()),
        usage=None,
        final_response=None,
        terminal_error=None,
        evaluation_error=None,
        worlds=ArtifactWorlds(copy.deepcopy(initial_world), None),
        evaluation=ArtifactEvaluation(False, {}, ()),
    )


def read_artifact(path: Path, *, enrich_task: bool = False) -> RunArtifact:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactValidationError(f"Cannot read artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise ArtifactValidationError("Artifact must be a JSON object")
    if value.get("artifact_type") == ARTIFACT_TYPE:
        return RunArtifact.from_dict(value)
    if value.get("artifact_type") == "agent_evaluation_run":
        return _legacy_evaluation_artifact(value, enrich_task=enrich_task)
    if _looks_like_legacy_session(value):
        return _legacy_session_artifact(value)
    if _looks_like_runtime_outcome(value):
        return _legacy_runtime_outcome(value, enrich_task=enrich_task)
    if _looks_like_configured_run(value):
        return _legacy_configured_run(value, enrich_task=enrich_task)
    raise ArtifactValidationError(f"Unsupported artifact schema: {path}")


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
            try:
                current = read_artifact(destination)
            except ArtifactValidationError:
                current = None
            if current is not None:
                if current.run_id != validated.run_id:
                    raise ImmutableArtifactError(
                        f"Artifact filename already belongs to run: {current.run_id}"
                    )
                if current.status in TERMINAL_STATUSES:
                    raise ImmutableArtifactError(
                        f"Terminal artifact cannot be changed: {current.run_id}"
                    )
                current_trace = current.trace
                if (
                    len(validated.trace) < len(current_trace)
                    or validated.trace[: len(current_trace)] != current_trace
                ):
                    raise ImmutableArtifactError(
                        f"Existing trace events cannot be changed: {current.run_id}"
                    )
        atomic_write_json(destination, validated.to_dict())
        return destination


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


def artifact_to_report_record(artifact: RunArtifact) -> dict[str, Any]:
    context = artifact.evaluation.context or {}
    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "configuration": copy.deepcopy(artifact.configuration),
        "task_id": artifact.task["task_id"],
        "repetition": context.get("repetition"),
        "run_id": artifact.run_id,
        "timing": asdict(artifact.timing),
        "status": artifact.status,
        "termination_reason": artifact.termination_reason,
        "trace": copy.deepcopy(list(artifact.trace)),
        "provider_retry_count": artifact.summary.provider_retry_count,
        "model_turn_count": artifact.summary.model_turn_count,
        "tool_call_count": artifact.summary.tool_call_count,
        "contains_tool_errors": artifact.summary.contains_tool_errors,
        "usage": copy.deepcopy(artifact.usage),
        "response": copy.deepcopy(artifact.final_response),
        "worlds": asdict(artifact.worlds),
        "official_score": copy.deepcopy(artifact.evaluation.official_score),
        "assertion_evidence": copy.deepcopy(list(artifact.evaluation.assertion_evidence)),
        "terminal_error": artifact.terminal_error,
        "evaluation_available": artifact.evaluation.available,
        "evaluation_error": artifact.evaluation_error,
    }


def artifact_to_session_view(artifact: RunArtifact, *, artifact_filename: str) -> dict[str, Any]:
    configuration = artifact.configuration
    runtime = configuration.get("runtime") or {
        "id": "custom",
        "label": "Custom agent",
        "version": str(configuration.get("harness_version") or "Unknown"),
    }
    limits = configuration.get("execution_limits") or {}
    max_steps = limits.get("max_model_turns", limits.get("logical_model_calls", 0))
    if not isinstance(max_steps, int):
        max_steps = 0
    score = copy.deepcopy(artifact.evaluation.official_score)
    if artifact.evaluation.assertion_evidence_available:
        score["assertions"] = copy.deepcopy(list(artifact.evaluation.assertion_evidence))
    status = {
        "running": "Running",
        "completed": "Completed",
        "stopped": "Stopped",
        "failed": "Failed",
        "interrupted": "Interrupted",
    }[artifact.status]
    view = {
        "schema_version": 1,
        "session_id": artifact.run_id,
        "artifact_filename": artifact_filename,
        "artifact_type": ARTIFACT_TYPE,
        "status": status,
        "lifecycle": {
            "created_at": artifact.timing.started_at,
            "updated_at": artifact.timing.updated_at,
            "completed_at": artifact.timing.finished_at,
            "terminal_error": artifact.terminal_error,
            "evaluation_error": artifact.evaluation_error,
            "termination_reason": artifact.termination_reason,
        },
        "task": copy.deepcopy(artifact.task),
        "agent": {
            "model": str(configuration.get("model") or "Unknown"),
            "max_steps": max_steps,
            "agent_version": str(runtime.get("version") or "Unknown"),
        },
        "runtime": copy.deepcopy(runtime),
        "events": copy.deepcopy(list(artifact.trace)),
        "final_response": copy.deepcopy(artifact.final_response),
        "evaluation": score if artifact.evaluation.available else None,
        "usage": copy.deepcopy(artifact.usage),
        "initial_world": copy.deepcopy(artifact.worlds.initial),
        "final_world": copy.deepcopy(artifact.worlds.final),
    }
    context = artifact.evaluation.context
    if context is not None:
        view["evaluation_run"] = {
            "configuration_identity": context.get(
                "configuration_identity", configuration.get("identity")
            ),
            "repetition": context.get("repetition"),
            "evaluation_artifact": artifact_filename,
            "fresh_world": context.get("fresh_world"),
            "resumed": context.get("resumed"),
            "infrastructure_replacement_count": context.get("infrastructure_replacement_count", 0),
        }
    return view


def session_view_to_artifact(session: dict[str, Any]) -> RunArtifact:
    return _legacy_session_artifact(session)


def _legacy_evaluation_artifact(value: dict[str, Any], *, enrich_task: bool) -> RunArtifact:
    _require_legacy_version(value)
    task_id = _required_string(value, "task_id")
    task = _resolved_task_snapshot(task_id) if enrich_task else _minimal_task(task_id)
    configuration = copy.deepcopy(_required_dict(value, "configuration"))
    configuration.setdefault(
        "runtime",
        {
            "id": "custom",
            "label": "Custom agent",
            "version": str(configuration.get("harness_version") or "Unknown"),
        },
    )
    trace_value = value.get("trace")
    if not isinstance(trace_value, list):
        raise ArtifactValidationError("Legacy evaluation trace must be a list")
    trace = tuple(copy.deepcopy(trace_value))
    timing = _required_dict(value, "timing")
    started_at = timing.get("started_at")
    if not isinstance(started_at, str):
        started_at = "1970-01-01T00:00:00+00:00"
    finished_at = timing.get("finished_at")
    if not isinstance(finished_at, str):
        finished_at = started_at
    score = copy.deepcopy(value.get("official_score") or {})
    evidence = value.get("assertion_evidence") or []
    if not isinstance(evidence, list):
        raise ArtifactValidationError("Legacy assertion evidence must be a list")
    status = _required_string(value, "status").lower()
    termination_reason = _optional_string(value, "termination_reason")
    if status in TERMINAL_STATUSES and termination_reason is None:
        termination_reason = "legacy_unknown"
        configuration["legacy_termination_reason_unavailable"] = True
    artifact = RunArtifact(
        run_id=_required_string(value, "run_id"),
        task=task,
        configuration=configuration,
        timing=ArtifactTiming(
            started_at=started_at,
            updated_at=finished_at,
            finished_at=finished_at,
            duration_ms=_optional_number(timing, "duration_ms"),
        ),
        status=status,
        termination_reason=termination_reason,
        trace=trace,
        summary=ArtifactSummary(
            provider_retry_count=int(value.get("provider_retry_count", 0)),
            model_turn_count=int(value.get("model_turn_count", 0)),
            tool_call_count=int(value.get("tool_call_count", 0)),
            contains_tool_errors=bool(value.get("contains_tool_errors", False)),
        ),
        usage=copy.deepcopy(value.get("usage")),
        final_response=copy.deepcopy(value.get("response")),
        terminal_error=_optional_string(value, "terminal_error"),
        evaluation_error=_optional_string(value, "evaluation_error"),
        worlds=ArtifactWorlds(
            initial=copy.deepcopy(_required_dict(value, "worlds").get("initial", {})),
            final=copy.deepcopy(_required_dict(value, "worlds").get("final")),
        ),
        evaluation=ArtifactEvaluation(
            available=bool(value.get("evaluation_available", True)),
            official_score=score,
            assertion_evidence=tuple(copy.deepcopy(evidence)),
            context={
                "configuration_identity": configuration.get("identity"),
                "repetition": value.get("repetition"),
                "fresh_world": True,
                "resumed": False,
                "infrastructure_replacement_count": 0,
            },
        ),
    )
    return RunArtifact.from_dict(artifact.to_dict())


def _legacy_session_artifact(value: dict[str, Any]) -> RunArtifact:
    _require_legacy_version(value)
    lifecycle = _required_dict(value, "lifecycle")
    task = copy.deepcopy(_required_dict(value, "task"))
    task.setdefault("tools", [])
    task.setdefault("assertions", [])
    task.setdefault("tool_definitions", [])
    agent = _required_dict(value, "agent")
    runtime = copy.deepcopy(
        value.get("runtime")
        or {
            "id": str(agent.get("runtime_id") or "legacy"),
            "label": str(agent.get("runtime_label") or "Legacy runtime"),
            "version": str(agent.get("agent_version") or "Unknown"),
        }
    )
    limits = {"max_model_turns": int(agent.get("max_steps", 0))}
    configuration = {
        "model": str(agent.get("model") or "Unknown"),
        "harness_version": str(runtime.get("version") or "Unknown"),
        "prompt_version": "legacy-session",
        "evaluation_protocol_version": "legacy-session",
        "execution_limits": limits,
        "runtime": runtime,
    }
    evaluation_run = value.get("evaluation_run")
    if isinstance(evaluation_run, dict) and evaluation_run.get("configuration_identity"):
        configuration["identity"] = evaluation_run["configuration_identity"]
    else:
        configuration["identity"] = configuration_identity(configuration)
    trace_value = value.get("events")
    if not isinstance(trace_value, list):
        raise ArtifactValidationError("Legacy session events must be a list")
    trace = tuple(copy.deepcopy(trace_value))
    legacy_session_id = _required_string(value, "session_id")
    event_run_ids = {
        event.get("run_id")
        for event in trace
        if isinstance(event, dict) and isinstance(event.get("run_id"), str)
    }
    run_id = next(iter(event_run_ids)) if len(event_run_ids) == 1 else legacy_session_id
    if run_id != legacy_session_id:
        configuration["legacy_session_id"] = legacy_session_id
    evaluation = value.get("evaluation")
    if evaluation is not None and not isinstance(evaluation, dict):
        raise ArtifactValidationError("Legacy session evaluation must be an object")
    score = copy.deepcopy(evaluation or {})
    evidence = score.pop("assertions", [])
    status = _required_string(value, "status").lower()
    completed_at = lifecycle.get("completed_at")
    if status in TERMINAL_STATUSES and not isinstance(completed_at, str):
        completed_at = _required_string(lifecycle, "updated_at")
    termination_reason = _optional_string(lifecycle, "termination_reason")
    if status in TERMINAL_STATUSES and termination_reason is None:
        termination_reason = "legacy_unknown"
        configuration["legacy_termination_reason_unavailable"] = True
    context = None
    if isinstance(evaluation_run, dict):
        context = {
            "configuration_identity": evaluation_run.get("configuration_identity"),
            "repetition": evaluation_run.get("repetition"),
            "fresh_world": evaluation_run.get("fresh_world", True),
            "resumed": evaluation_run.get("resumed", False),
            "infrastructure_replacement_count": evaluation_run.get(
                "infrastructure_replacement_count", 0
            ),
        }
    artifact = RunArtifact(
        run_id=run_id,
        task=task,
        configuration=configuration,
        timing=ArtifactTiming(
            started_at=_required_string(lifecycle, "created_at"),
            updated_at=_required_string(lifecycle, "updated_at"),
            finished_at=completed_at,
            duration_ms=_duration_ms(_required_string(lifecycle, "created_at"), completed_at),
        ),
        status=status,
        termination_reason=termination_reason,
        trace=trace,
        summary=summarize_trace(trace),
        usage=copy.deepcopy(value.get("usage")),
        final_response=copy.deepcopy(value.get("final_response")),
        terminal_error=_optional_string(lifecycle, "terminal_error"),
        evaluation_error=_optional_string(lifecycle, "evaluation_error"),
        worlds=ArtifactWorlds(
            initial=copy.deepcopy(value.get("initial_world") or {}),
            final=copy.deepcopy(value.get("final_world")),
        ),
        evaluation=ArtifactEvaluation(
            available=evaluation is not None,
            official_score=score,
            assertion_evidence=tuple(copy.deepcopy(evidence)),
            context=context,
            assertion_evidence_available=(evaluation is not None and "assertions" in evaluation),
        ),
    )
    return RunArtifact.from_dict(artifact.to_dict())


def _legacy_runtime_outcome(value: dict[str, Any], *, enrich_task: bool) -> RunArtifact:
    task_id = _required_string(value, "task_id")
    task = _resolved_task_snapshot(task_id) if enrich_task else _minimal_task(task_id)
    events = value.get("events")
    if not isinstance(events, list):
        raise ArtifactValidationError("Legacy runtime events must be a list")
    trace = tuple(copy.deepcopy(events))
    timestamps = [event.get("timestamp") for event in trace if event.get("timestamp")]
    started_at = min(timestamps) if timestamps else "1970-01-01T00:00:00+00:00"
    finished_at = max(timestamps) if timestamps else started_at
    configuration = {
        "model": "Unknown",
        "harness_version": "legacy-runtime-outcome",
        "prompt_version": "legacy-runtime-outcome",
        "evaluation_protocol_version": "legacy-runtime-outcome",
        "execution_limits": {},
        "runtime": {
            "id": "legacy",
            "label": "Legacy runtime",
            "version": "legacy-runtime-outcome",
        },
    }
    configuration["identity"] = configuration_identity(configuration)
    score = copy.deepcopy(value.get("score") or {})
    evidence = score.pop("assertions", [])
    status = _required_string(value, "status").lower()
    termination_reason = _optional_string(value, "termination_reason")
    if status in TERMINAL_STATUSES and termination_reason is None:
        termination_reason = "legacy_unknown"
        configuration["legacy_termination_reason_unavailable"] = True
    artifact = RunArtifact(
        run_id=_required_string(value, "run_id"),
        task=task,
        configuration=configuration,
        timing=ArtifactTiming(
            started_at=started_at,
            updated_at=finished_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        ),
        status=status,
        termination_reason=termination_reason,
        trace=trace,
        summary=summarize_trace(trace),
        usage=copy.deepcopy(value.get("usage")),
        final_response=copy.deepcopy(value.get("final_response")),
        terminal_error=_optional_string(value, "terminal_error"),
        evaluation_error=_optional_string(value, "evaluation_error"),
        worlds=ArtifactWorlds(
            initial=_resolved_initial_world(task_id) if enrich_task else {},
            final=copy.deepcopy(value.get("world_state")),
        ),
        evaluation=ArtifactEvaluation(
            available=value.get("score") is not None,
            official_score=score,
            assertion_evidence=tuple(copy.deepcopy(evidence)),
        ),
    )
    return RunArtifact.from_dict(artifact.to_dict())


def _legacy_configured_run(value: dict[str, Any], *, enrich_task: bool) -> RunArtifact:
    task_id = _required_string(value, "task")
    task = _resolved_task_snapshot(task_id) if enrich_task else _minimal_task(task_id)
    task["example_id"] = value.get("example_id")
    task["tools"] = copy.deepcopy(value.get("tools") or [])
    canonical_legacy = json.dumps(value, sort_keys=True, separators=(",", ":"))
    run_id = f"legacy-configured-{sha256(canonical_legacy.encode()).hexdigest()[:24]}"
    messages = value.get("messages")
    if not isinstance(messages, list):
        raise ArtifactValidationError("Legacy configured-run messages must be a list")
    trace = tuple(
        {
            "sequence": index,
            "kind": "legacy_message",
            "timestamp": "1970-01-01T00:00:00+00:00",
            "run_id": run_id,
            "correlation_id": f"legacy-message-{index}",
            "content": copy.deepcopy(message),
        }
        for index, message in enumerate(messages, start=1)
    )
    score = copy.deepcopy(value.get("score") or {})
    evidence = score.pop("assertions", [])
    strict = score.get("task_completed_correctly") == 1.0
    configuration = {
        "model": str(value.get("model") or "Unknown"),
        "harness_version": "legacy-configured-run",
        "prompt_version": "legacy-configured-run",
        "evaluation_protocol_version": "legacy-configured-run",
        "execution_limits": {},
        "runtime": {
            "id": "legacy",
            "label": "Legacy configured run",
            "version": "legacy-configured-run",
        },
        "legacy_timing_unavailable": True,
    }
    configuration["identity"] = configuration_identity(configuration)
    final_response = None
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("type") == "ai":
            final_response = copy.deepcopy(message.get("content"))
            break
    artifact = RunArtifact(
        run_id=run_id,
        task=task,
        configuration=configuration,
        timing=ArtifactTiming(
            started_at="1970-01-01T00:00:00+00:00",
            updated_at="1970-01-01T00:00:00+00:00",
            finished_at="1970-01-01T00:00:00+00:00",
            duration_ms=None,
        ),
        status="completed" if strict else "stopped",
        termination_reason="goal_completed" if strict else "partial",
        trace=trace,
        summary=ArtifactSummary(
            provider_retry_count=0,
            model_turn_count=sum(
                isinstance(message, dict) and message.get("type") == "ai" for message in messages
            ),
            tool_call_count=sum(
                isinstance(block, dict) and block.get("type") == "function_call"
                for message in messages
                if isinstance(message, dict) and isinstance(message.get("content"), list)
                for block in message["content"]
            ),
            contains_tool_errors=False,
        ),
        usage=copy.deepcopy(value.get("usage")),
        final_response=final_response,
        terminal_error=None,
        evaluation_error=None,
        worlds=ArtifactWorlds(
            initial=_resolved_initial_world(task_id) if enrich_task else {},
            final=copy.deepcopy(value.get("end_state")),
        ),
        evaluation=ArtifactEvaluation(
            available=value.get("score") is not None,
            official_score=score,
            assertion_evidence=tuple(copy.deepcopy(evidence)),
        ),
    )
    return RunArtifact.from_dict(artifact.to_dict())


def _resolved_task_snapshot(task_id: str) -> dict[str, Any]:
    from sales_agent.adapter import AutomationBenchAdapter
    from sales_agent.catalog import TaskCatalog

    catalog = TaskCatalog.from_sales_dataset()
    task = catalog.get_task(task_id)
    tools = AutomationBenchAdapter(catalog=catalog).open(task_id).agent_task.tools
    definitions = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tools
    ]
    return task_snapshot(task, tool_definitions=definitions)


def _resolved_initial_world(task_id: str) -> dict[str, Any]:
    from sales_agent.catalog import TaskCatalog

    return copy.deepcopy(TaskCatalog.from_sales_dataset().get_task(task_id).info["initial_state"])


def _minimal_task(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "name": task_id.removeprefix("sales.").replace("_", " ").title(),
        "prompt": [],
        "tools": [],
        "assertions": [],
        "tool_definitions": [],
    }


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


def _looks_like_legacy_session(value: dict[str, Any]) -> bool:
    return all(key in value for key in ("session_id", "lifecycle", "task", "events"))


def _looks_like_runtime_outcome(value: dict[str, Any]) -> bool:
    return all(key in value for key in ("run_id", "task_id", "status", "events"))


def _looks_like_configured_run(value: dict[str, Any]) -> bool:
    return all(key in value for key in ("task", "model", "messages", "end_state"))


def _require_legacy_version(value: dict[str, Any]) -> None:
    if value.get("schema_version") != 1:
        raise UnsupportedArtifactVersionError(
            f"Unsupported legacy artifact schema version: {value.get('schema_version')!r}"
        )


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


def _duration_ms(started_at: str, finished_at: str | None) -> float | None:
    if finished_at is None:
        return None
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    return round((finished - started).total_seconds() * 1000, 3)


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Cannot serialize {type(value).__name__}")
