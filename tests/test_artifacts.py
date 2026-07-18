import json
from dataclasses import replace
from pathlib import Path

import pytest

from sales_agent.artifacts import (
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
)


def _artifact(*, status="completed", run_id="run-1"):
    finished_at = None if status == "running" else "2026-07-17T12:00:01+00:00"
    trace = (
        (
            {
                "sequence": 1,
                "kind": "completion",
                "timestamp": "2026-07-17T12:00:01+00:00",
                "run_id": run_id,
                "correlation_id": run_id,
                "content": {"termination_reason": "goal_completed"},
            },
        )
        if status != "running"
        else ()
    )
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
            assertion_evidence=(() if status == "running" else ({"passed": True},)),
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


def test_artifact_writes_are_atomic_and_never_replace_an_existing_destination(tmp_path):
    store = RunArtifactStore(tmp_path)
    artifact = _artifact()
    path = store.write(artifact)
    original = path.read_bytes()
    assert read_artifact(path) == artifact

    with pytest.raises(ImmutableArtifactError, match="already exists"):
        store.write(artifact)
    assert path.read_bytes() == original

    with pytest.raises(ImmutableArtifactError, match="already exists"):
        store.write(_artifact(run_id="different-run"), filename=path.name)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))

    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(b"{not-json\n")
    malformed_original = malformed.read_bytes()
    with pytest.raises(ImmutableArtifactError, match="already exists"):
        store.write(_artifact(run_id="malformed"), filename=malformed.name)
    assert malformed.read_bytes() == malformed_original


def test_artifact_serializes_nested_tool_exceptions_as_structured_json(tmp_path):
    artifact = _artifact()
    tool_error = ValueError("Unsupported query filter")
    event = {
        "sequence": 1,
        "kind": "tool_error",
        "timestamp": "2026-07-17T12:00:01+00:00",
        "run_id": artifact.run_id,
        "correlation_id": "tool-call-1",
        "name": "salesforce_query",
        "result": {"error": tool_error},
        "error": {
            "type": "tool_reported_error",
            "reported_error": tool_error,
        },
    }
    artifact = replace(
        artifact,
        trace=(event,),
        summary=ArtifactSummary(0, 0, 0, True),
    )

    path = RunArtifactStore(tmp_path).write(artifact)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    expected = {"type": "ValueError", "message": "Unsupported query filter"}

    assert persisted["trace"][0]["result"]["error"] == expected
    assert persisted["trace"][0]["error"]["reported_error"] == expected
    assert read_artifact(path).trace[0]["result"]["error"] == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"artifact_type": "agent_evaluation_run", "schema_version": 1},
        {"schema_version": 1, "session_id": "session", "lifecycle": {}, "events": []},
        {"run_id": "runtime", "task_id": "task", "status": "completed", "events": []},
        {"task": "task", "model": "model", "messages": [], "end_state": {}},
    ],
)
def test_historical_artifact_formats_are_rejected_as_unsupported(tmp_path, payload):
    path = tmp_path / "historical.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="Artifact type must be run_artifact"):
        read_artifact(path)


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


def test_every_checked_in_run_and_evaluation_observation_is_canonical():
    project_root = Path(__file__).resolve().parents[1]
    results = project_root / "results"
    paths = [
        *results.glob("*.json"),
        *(results / "development").glob("*.json"),
        *(results / "runs").glob("*.json"),
        *(path for path in (results / "evaluation").glob("*.json") if path.name != "report.json"),
    ]

    assert paths
    assert all(read_artifact(path).to_dict()["artifact_type"] == "run_artifact" for path in paths)
