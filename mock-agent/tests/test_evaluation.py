import json
from pathlib import Path

from mock_agent.contract import (
    EventKind,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    TerminationReason,
)
from mock_agent.evaluation import main


TASK_ID = "sales.zoom_calendar_conflict"


def _event(run_id, kind, *, content=None, usage=None):
    return RuntimeEvent(
        sequence=1,
        kind=kind,
        timestamp="2026-07-16T12:00:00+00:00",
        run_id=run_id,
        correlation_id=run_id,
        content=content,
        usage=usage,
    )


def _outcome(run_id, *, infrastructure=False, failed=False):
    if infrastructure:
        events = (
            _event(
                run_id,
                EventKind.MODEL_ERROR,
                content={"infrastructure_failure": True},
            ),
        )
        return RuntimeOutcome(
            status=ExitStatus.FAILED,
            task_id=TASK_ID,
            run_id=run_id,
            events=events,
            final_response=None,
            world_state={"attempt": run_id},
            score={"partial_credit": 0.0, "task_completed_correctly": 0.0},
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            terminal_error="endpoint unavailable",
            termination_reason=TerminationReason.MODEL_ERROR,
        )
    reason = (
        TerminationReason.RUNTIME_ERROR if failed else TerminationReason.GOAL_COMPLETED
    )
    return RuntimeOutcome(
        status=ExitStatus.FAILED if failed else ExitStatus.COMPLETED,
        task_id=TASK_ID,
        run_id=run_id,
        events=(
            _event(
                run_id,
                EventKind.COMPLETION,
                content={"termination_reason": reason.value},
                usage={"total_tokens": 7},
            ),
        ),
        final_response=None if failed else "done",
        world_state={"attempt": run_id},
        score={
            "partial_credit": 0.0 if failed else 1.0,
            "task_completed_correctly": 0.0 if failed else 1.0,
            "assertions": [{"passed": not failed}],
        },
        usage={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
        terminal_error="agent failed" if failed else None,
        termination_reason=reason,
    )


def _inputs(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    config = tmp_path / "config.json"
    manifest.write_text(json.dumps({"tasks": [TASK_ID]}), encoding="utf-8")
    config.write_text(
        json.dumps(
            {
                "model": "scripted-model",
                "harness_version": "planner-executor/0.3.0",
                "prompt_version": "planner-executor-prompts/v2",
                "evaluation_protocol_version": "sales-panel/v1",
                "execution_limits": {
                    "plan_steps": 6,
                    "executor_tool_turns_per_attempt": 4,
                    "reserved_outcome_calls_per_saturated_attempt": 1,
                    "step_retries": 1,
                    "replans": 1,
                    "logical_model_calls": 30,
                    "provider_retries": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest, config


def test_evaluation_replaces_infrastructure_attempts_and_resumes_missing_runs(
    tmp_path,
):
    manifest, config = _inputs(tmp_path)
    artifacts = tmp_path / "artifacts"
    scripted = iter(
        [
            _outcome("infra", infrastructure=True),
            _outcome("observed-1"),
            _outcome("observed-2", failed=True),
        ]
    )
    runtime_instances = []

    class Runtime:
        def __init__(self):
            self.calls = 0

        async def run(self, request, **_):
            self.calls += 1
            if request.task_id == TASK_ID and request.model_name == "scripted-model":
                if len(runtime_instances) == 3:
                    assert len(list(artifacts.glob("*.json"))) == 1
            return next(scripted)

    def runtime_factory():
        runtime = Runtime()
        runtime_instances.append(runtime)
        return runtime

    main(
        [
            "run",
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--repetitions",
            "2",
            "--artifacts-dir",
            str(artifacts),
        ],
        runtime_factory=runtime_factory,
    )

    records = [
        json.loads(path.read_text()) for path in sorted(artifacts.glob("*.json"))
    ]
    assert [record["run_id"] for record in records] == ["observed-1", "observed-2"]
    assert [record["repetition"] for record in records] == [1, 2]
    assert records[1]["termination_reason"] == "runtime_error"
    assert all(record["configuration"]["identity"] for record in records)
    assert all(instance.calls == 1 for instance in runtime_instances)
    assert {
        "model",
        "harness_version",
        "prompt_version",
        "evaluation_protocol_version",
        "execution_limits",
    } <= records[0]["configuration"].keys()
    assert records[0]["trace"][0]["kind"] == "completion"
    assert records[0]["provider_retry_count"] == 0
    assert records[0]["model_turn_count"] == 1
    assert records[0]["tool_call_count"] == 0
    assert records[0]["usage"]["total_tokens"] == 7
    assert records[0]["response"] == "done"
    assert records[0]["worlds"]["final"] == {"attempt": "observed-1"}
    assert records[0]["official_score"]["task_completed_correctly"] == 1.0
    assert records[0]["assertion_evidence"] == [{"passed": True}]

    main(
        [
            "run",
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--repetitions",
            "2",
            "--artifacts-dir",
            str(artifacts),
        ],
        runtime_factory=lambda: (_ for _ in ()).throw(
            AssertionError("completed repetitions must be skipped")
        ),
    )

    repetition_two = next(
        path
        for path in artifacts.glob("*.json")
        if json.loads(path.read_text())["repetition"] == 2
    )
    repetition_two.unlink()

    class ReplacementRuntime:
        async def run(self, request, **_):
            assert request.task_id == TASK_ID
            return _outcome("observed-2-replacement")

    main(
        [
            "run",
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--repetitions",
            "2",
            "--artifacts-dir",
            str(artifacts),
        ],
        runtime_factory=ReplacementRuntime,
    )
    resumed = [
        json.loads(path.read_text()) for path in sorted(artifacts.glob("*.json"))
    ]
    assert [record["run_id"] for record in resumed] == [
        "observed-1",
        "observed-2-replacement",
    ]


def test_report_is_configuration_isolated_statistically_correct_and_byte_stable(
    tmp_path,
):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    def write_artifact(
        filename,
        *,
        identity,
        repetition,
        partial,
        strict,
        tokens,
        duration,
        turns,
        tool_calls,
        tool_error,
        reason,
    ):
        configuration = {
            "identity": identity,
            "model": "model-a",
            "harness_version": "harness/v1",
            "prompt_version": "prompts/v1",
            "evaluation_protocol_version": "panel/v1",
            "execution_limits": {"logical_model_calls": 24},
        }
        if identity == "config-b":
            configuration["prompt_version"] = "prompts/v2"
        payload = {
            "artifact_type": "agent_evaluation_run",
            "schema_version": 1,
            "configuration": configuration,
            "task_id": TASK_ID,
            "repetition": repetition,
            "run_id": f"{identity}-{repetition}",
            "timing": {"duration_ms": duration},
            "status": "completed",
            "termination_reason": reason,
            "trace": [],
            "provider_retry_count": 0,
            "model_turn_count": turns,
            "tool_call_count": tool_calls,
            "contains_tool_errors": tool_error,
            "usage": {"total_tokens": tokens},
            "response": "done",
            "worlds": {"initial": {}, "final": {}},
            "official_score": {
                "partial_credit": partial,
                "task_completed_correctly": strict,
            },
            "assertion_evidence": [],
            "terminal_error": None,
        }
        (artifacts / filename).write_text(json.dumps(payload), encoding="utf-8")

    write_artifact(
        "z.json",
        identity="config-a",
        repetition=3,
        partial=1.0,
        strict=1.0,
        tokens=100,
        duration=900,
        turns=3,
        tool_calls=6,
        tool_error=False,
        reason="goal_completed",
    )
    write_artifact(
        "a.json",
        identity="config-a",
        repetition=1,
        partial=0.0,
        strict=0.0,
        tokens=10,
        duration=100,
        turns=1,
        tool_calls=2,
        tool_error=True,
        reason="budget_exhausted",
    )
    write_artifact(
        "m.json",
        identity="config-a",
        repetition=2,
        partial=0.5,
        strict=1.0,
        tokens=20,
        duration=200,
        turns=2,
        tool_calls=4,
        tool_error=False,
        reason="goal_completed",
    )
    write_artifact(
        "other-config.json",
        identity="config-b",
        repetition=1,
        partial=0.25,
        strict=0.0,
        tokens=30,
        duration=300,
        turns=2,
        tool_calls=1,
        tool_error=False,
        reason="goal_completed",
    )
    markdown_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    command = [
        "report",
        "--artifacts-dir",
        str(artifacts),
        "--markdown",
        str(markdown_path),
        "--json",
        str(json_path),
    ]

    main(command)
    first_markdown = markdown_path.read_bytes()
    first_json = json_path.read_bytes()
    report = json.loads(first_json)
    group = report["groups"][0]

    assert len(report["groups"]) == 2
    assert group["configuration"]["identity"] == "config-a"
    assert group["coverage"] == {"repetitions": [1, 2, 3], "scorable_count": 3}
    assert group["strict_completion"] == {"count": 2, "percentage": 66.667}
    assert group["partial_credit"] == {
        "maximum": 1.0,
        "mean": 0.5,
        "minimum": 0.0,
        "sample_standard_deviation": 0.5,
    }
    assert group["tokens"] == {"maximum": 100, "median": 20, "minimum": 10}
    assert group["duration_ms"] == {
        "maximum": 900,
        "median": 200,
        "minimum": 100,
    }
    assert group["model_turns"] == {"maximum": 3, "median": 2}
    assert group["tool_calls"] == {"maximum": 6, "median": 4}
    assert group["runs_containing_tool_errors"] == 1
    assert group["termination_reasons"] == {
        "budget_exhausted": 1,
        "goal_completed": 2,
    }
    markdown = first_markdown.decode()
    for heading in (
        "## Configuration",
        "## Coverage",
        "## Panel Summary",
        "## Per-task Results",
        "## Termination Evidence",
        "## Run Artifacts",
    ):
        assert heading in markdown
    assert all(name in markdown for name in ("a.json", "m.json", "z.json"))

    main(command)
    assert markdown_path.read_bytes() == first_markdown
    assert json_path.read_bytes() == first_json
