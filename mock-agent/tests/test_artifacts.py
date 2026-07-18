from dataclasses import replace
import json

import pytest

from mock_agent.artifacts import (
    ArtifactEvaluation,
    ArtifactSummary,
    ArtifactTiming,
    ArtifactValidationError,
    ArtifactWorlds,
    ImmutableArtifactError,
    RunArtifact,
    RunArtifactStore,
    UnsupportedArtifactVersionError,
    read_artifact,
    session_view_to_artifact,
)


def _artifact(*, status="completed", run_id="run-1"):
    finished_at = None if status == "running" else "2026-07-17T12:00:01+00:00"
    trace = (
        {
            "sequence": 1,
            "kind": "completion",
            "timestamp": "2026-07-17T12:00:01+00:00",
            "run_id": run_id,
            "correlation_id": run_id,
            "content": {"termination_reason": "goal_completed"},
        },
    ) if status != "running" else ()
    return RunArtifact(
        run_id=run_id,
        task={
            "task_id": "sales.zoom_calendar_conflict",
            "name": "Zoom Calendar Conflict",
            "prompt": [{"role": "user", "content": "Resolve it."}],
            "tools": ["zoom_update_meeting"],
            "assertions": [{"type": "zoom_meeting_field_equals"}],
            "tool_definitions": [],
        },
        configuration={
            "identity": "config-1",
            "model": "model-1",
            "harness_version": "plan-state/1",
            "prompt_version": "prompts/1",
            "evaluation_protocol_version": "single-run/1",
            "execution_limits": {"max_model_turns": 2},
            "runtime": {
                "id": "custom",
                "label": "Custom agent",
                "version": "plan-state/1",
            },
        },
        timing=ArtifactTiming(
            started_at="2026-07-17T12:00:00+00:00",
            updated_at=finished_at or "2026-07-17T12:00:00+00:00",
            finished_at=finished_at,
            duration_ms=None if status == "running" else 1000.0,
        ),
        status=status,
        termination_reason=None if status == "running" else "goal_completed",
        trace=trace,
        summary=ArtifactSummary(0, 0, 0, False),
        usage=None if status == "running" else {"total_tokens": 3},
        final_response=None if status == "running" else {"message": "done"},
        terminal_error=None,
        evaluation_error=None,
        worlds=ArtifactWorlds({"before": True}, None if status == "running" else {"after": True}),
        evaluation=ArtifactEvaluation(
            available=status != "running",
            official_score=(
                {}
                if status == "running"
                else {"partial_credit": 1.0, "task_completed_correctly": 1.0}
            ),
            assertion_evidence=(
                () if status == "running" else ({"passed": True},)
            ),
        ),
    )


def test_successful_and_partial_artifacts_round_trip_without_information_loss():
    successful = _artifact()
    partial = replace(
        successful,
        run_id="partial-run",
        status="stopped",
        termination_reason="budget_exhausted",
        trace=(
            {
                **successful.trace[0],
                "run_id": "partial-run",
                "correlation_id": "partial-run",
                "content": {"termination_reason": "budget_exhausted"},
            },
        ),
        final_response={"message": "partially done", "remaining": ["notify"]},
        terminal_error="budget reached",
        worlds=ArtifactWorlds({"before": True}, {"partial": True}),
        evaluation=ArtifactEvaluation(
            True,
            {"partial_credit": 0.5, "task_completed_correctly": 0.0},
            ({"passed": False, "evidence": {"expected": "notification"}},),
            {
                "configuration_identity": "config-1",
                "repetition": 2,
                "fresh_world": True,
                "resumed": True,
                "infrastructure_replacement_count": 1,
            },
        ),
    )

    assert RunArtifact.from_dict(successful.to_dict()) == successful
    assert RunArtifact.from_dict(partial.to_dict()) == partial


def test_atomic_active_snapshots_preserve_trace_and_terminal_artifacts_are_immutable(
    tmp_path,
):
    store = RunArtifactStore(tmp_path)
    active = _artifact(status="running")
    path = store.write(active)
    assert json.loads(path.read_text())["status"] == "running"

    event = {
        "sequence": 1,
        "kind": "model_turn",
        "timestamp": "2026-07-17T12:00:00.500000+00:00",
        "run_id": active.run_id,
        "correlation_id": "turn-1",
    }
    snapshot = replace(
        active,
        trace=(event,),
        timing=replace(
            active.timing, updated_at="2026-07-17T12:00:00.500000+00:00"
        ),
    )
    store.write(snapshot)
    changed_event = {**event, "kind": "tool_call"}
    with pytest.raises(ImmutableArtifactError, match="trace events"):
        store.write(replace(snapshot, trace=(changed_event,)))

    terminal = replace(
        snapshot,
        status="completed",
        termination_reason="goal_completed",
        timing=ArtifactTiming(
            active.timing.started_at,
            "2026-07-17T12:00:01+00:00",
            "2026-07-17T12:00:01+00:00",
            1000.0,
        ),
        final_response="done",
        worlds=ArtifactWorlds(active.worlds.initial, {"after": True}),
    )
    store.write(terminal)
    assert read_artifact(path) == terminal
    with pytest.raises(ImmutableArtifactError, match="Terminal artifact"):
        store.write(terminal)
    assert not list(tmp_path.glob("*.tmp"))

    second_store = RunArtifactStore(tmp_path / "collision")
    second_store.write(_artifact(status="running", run_id="first"), filename="run.json")
    with pytest.raises(ImmutableArtifactError, match="already belongs"):
        second_store.write(
            _artifact(status="running", run_id="second"), filename="run.json"
        )


def test_legacy_evaluation_and_session_are_read_but_only_canonical_is_written(
    tmp_path,
):
    legacy_evaluation = {
        "artifact_type": "agent_evaluation_run",
        "schema_version": 1,
        "configuration": {
            "identity": "legacy-config",
            "model": "legacy-model",
            "harness_version": "legacy/1",
            "prompt_version": "legacy-prompts/1",
            "evaluation_protocol_version": "legacy-panel/1",
            "execution_limits": {},
        },
        "task_id": "sales.zoom_calendar_conflict",
        "repetition": 3,
        "run_id": "legacy-evaluation",
        "timing": {
            "started_at": "2026-07-17T12:00:00+00:00",
            "finished_at": "2026-07-17T12:00:01+00:00",
            "duration_ms": 1000,
        },
        "status": "completed",
        "termination_reason": "goal_completed",
        "trace": [],
        "provider_retry_count": 0,
        "model_turn_count": 1,
        "tool_call_count": 0,
        "contains_tool_errors": False,
        "usage": {"total_tokens": 2},
        "response": "done",
        "worlds": {"initial": {}, "final": {}},
        "official_score": {"partial_credit": 1.0, "task_completed_correctly": 1.0},
        "assertion_evidence": [{"passed": True}],
        "terminal_error": None,
    }
    legacy_path = tmp_path / "legacy-evaluation.json"
    legacy_path.write_text(json.dumps(legacy_evaluation), encoding="utf-8")
    converted_evaluation = read_artifact(legacy_path)
    assert converted_evaluation.evaluation.context["repetition"] == 3

    legacy_session = {
        "schema_version": 1,
        "session_id": "legacy-session",
        "status": "Completed",
        "lifecycle": {
            "created_at": "2026-07-17T12:00:00+00:00",
            "updated_at": "2026-07-17T12:00:01+00:00",
            "completed_at": "2026-07-17T12:00:01+00:00",
            "terminal_error": None,
            "termination_reason": "goal_completed",
        },
        "task": {
            "task_id": "sales.zoom_calendar_conflict",
            "name": "Zoom Calendar Conflict",
            "prompt": [],
        },
        "agent": {"model": "legacy-model", "max_steps": 2, "agent_version": "legacy/1"},
        "events": [],
        "final_response": "done",
        "evaluation": {"partial_credit": 1.0, "assertions": []},
        "usage": {"total_tokens": 2},
        "initial_world": {},
        "final_world": {},
    }
    canonical = session_view_to_artifact(legacy_session)
    written = RunArtifactStore(tmp_path / "canonical").write(canonical)
    persisted = json.loads(written.read_text())
    assert persisted["artifact_type"] == "run_artifact"
    assert "session_id" not in persisted


def test_missing_malformed_and_unsupported_versions_are_rejected(tmp_path):
    malformed = tmp_path / "malformed.json"
    malformed.write_text("not json", encoding="utf-8")
    with pytest.raises(ArtifactValidationError, match="Cannot read artifact"):
        read_artifact(malformed)

    missing = tmp_path / "missing.json"
    missing.write_text(json.dumps({"artifact_type": "run_artifact", "schema_version": 1}))
    with pytest.raises(ArtifactValidationError, match="run_id"):
        read_artifact(missing)

    missing_reason = _artifact().to_dict()
    missing_reason["termination_reason"] = None
    missing_reason_path = tmp_path / "missing-reason.json"
    missing_reason_path.write_text(json.dumps(missing_reason), encoding="utf-8")
    with pytest.raises(ArtifactValidationError, match="termination_reason"):
        read_artifact(missing_reason_path)

    future = _artifact().to_dict()
    future["schema_version"] = 99
    future_path = tmp_path / "future.json"
    future_path.write_text(json.dumps(future), encoding="utf-8")
    with pytest.raises(UnsupportedArtifactVersionError, match="99"):
        read_artifact(future_path)
