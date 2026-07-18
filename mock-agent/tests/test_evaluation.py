import json
import os
from pathlib import Path

import pytest

from mock_agent import evaluation
from mock_agent.artifacts import (
    ArtifactEvaluation,
    ArtifactSummary,
    ArtifactTiming,
    ArtifactWorlds,
    RunArtifact,
)
from mock_agent.contract import (
    EventKind,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    TerminationReason,
)
from mock_agent.evaluation import main
from mock_agent.main import main as single_run_main
from mock_agent.plan_state_runtime import PLAN_STATE_LIMITS


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
                "harness_version": "plan-state/1.0.0",
                "prompt_version": "plan-state-prompts/v1",
                "evaluation_protocol_version": "sales-panel/v1",
                "execution_limits": PLAN_STATE_LIMITS,
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
    assert [
        record["evaluation"]["context"]["repetition"] for record in records
    ] == [1, 2]
    assert all(record["artifact_type"] == "run_artifact" for record in records)
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
    assert records[0]["summary"]["provider_retry_count"] == 0
    assert records[0]["summary"]["model_turn_count"] == 1
    assert records[0]["summary"]["tool_call_count"] == 0
    assert records[0]["usage"]["total_tokens"] == 7
    assert records[0]["final_response"] == "done"
    assert records[0]["worlds"]["final"] == {"attempt": "observed-1"}
    assert (
        records[0]["evaluation"]["official_score"]["task_completed_correctly"]
        == 1.0
    )
    assert records[0]["evaluation"]["assertion_evidence"] == [{"passed": True}]
    assert records[0]["task"]["prompt"]
    assert records[0]["evaluation"]["context"] == {
        "configuration_identity": records[0]["configuration"]["identity"],
        "repetition": 1,
        "fresh_world": True,
        "resumed": False,
        "infrastructure_replacement_count": 1,
    }

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
        if json.loads(path.read_text())["evaluation"]["context"]["repetition"] == 2
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
    assert resumed[1]["evaluation"]["context"]["resumed"] is True


def test_evaluation_command_loads_project_credentials(tmp_path, monkeypatch):
    project = tmp_path / "mock-agent"
    project.mkdir()
    (tmp_path / ".env").write_text(
        "LIBRA_INTERVIEW_API_KEY=repository-key\n", encoding="utf-8"
    )
    (project / ".env").write_text(
        "LIBRA_BASE_URL=https://libra.example/v1\n", encoding="utf-8"
    )
    monkeypatch.delenv("LIBRA_INTERVIEW_API_KEY", raising=False)
    monkeypatch.delenv("LIBRA_BASE_URL", raising=False)
    monkeypatch.setattr(evaluation, "PROJECT_ROOT", project, raising=False)
    monkeypatch.setattr(evaluation, "REPOSITORY_ROOT", tmp_path, raising=False)
    manifest, config = _inputs(tmp_path)

    class Runtime:
        async def run(self, request, **_):
            assert os.environ["LIBRA_INTERVIEW_API_KEY"] == "repository-key"
            assert os.environ["LIBRA_BASE_URL"] == "https://libra.example/v1"
            return _outcome("credentials-loaded")

    main(
        [
            "run",
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--repetitions",
            "1",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ],
        runtime_factory=Runtime,
    )


def test_single_run_and_evaluator_write_the_same_canonical_schema(tmp_path, capsys):
    single_directory = tmp_path / "single-runs"
    single_path = single_directory / "single-run.json"

    class SingleRuntime:
        async def run(self, request, **_):
            return _outcome("single-run")

    single_run_main(
        [
            "--task-id",
            TASK_ID,
            "--model",
            "scripted-model",
            "--artifacts-dir",
            str(single_directory),
            "--viewer-base-url",
            "http://viewer/",
        ],
        runtime_factory=SingleRuntime,
    )
    output = capsys.readouterr().out
    assert "artifact:" in output
    assert "viewer: http://viewer/?run_id=single-run" in output

    manifest, config = _inputs(tmp_path)
    evaluation_directory = tmp_path / "evaluation"

    class EvaluationRuntime:
        async def run(self, request, **_):
            return _outcome("evaluation-run")

    main(
        [
            "run",
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--repetitions",
            "1",
            "--artifacts-dir",
            str(evaluation_directory),
        ],
        runtime_factory=EvaluationRuntime,
    )

    single = json.loads(single_path.read_text())
    evaluated = json.loads(next(evaluation_directory.glob("*.json")).read_text())
    assert single["artifact_type"] == evaluated["artifact_type"] == "run_artifact"
    assert single["schema_version"] == evaluated["schema_version"] == 1
    assert single.keys() == evaluated.keys()
    assert single["task"].keys() == evaluated["task"].keys()


def test_evaluator_no_longer_accepts_sessions_dir():
    with pytest.raises(SystemExit):
        evaluation._parser().parse_args(
            [
                "run",
                "--manifest",
                "manifest.json",
                "--config",
                "config.json",
                "--repetitions",
                "1",
                "--artifacts-dir",
                "artifacts",
                "--sessions-dir",
                "sessions",
            ]
        )


def test_committed_evaluation_corpus_is_canonical_unique_and_report_reproducible(
    tmp_path,
):
    project_root = Path(__file__).resolve().parents[1]
    repository_root = project_root.parent
    artifacts = project_root / "results" / "evaluation"
    paths = sorted(
        path for path in artifacts.glob("*.json") if path.name != "report.json"
    )
    records = [json.loads(path.read_text()) for path in paths]

    assert len(records) == 61
    assert all(record["artifact_type"] == "run_artifact" for record in records)
    assert len({record["run_id"] for record in records}) == len(records)
    assert {
        record["configuration"]["identity"] for record in records
    } == {"a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c"}
    assert not list((repository_root / "sessions").glob("evaluation_*.json"))

    generated_markdown = tmp_path / "report.md"
    generated_json = tmp_path / "report.json"
    selected_tasks = [
        "sales.contract_renewal_coordinator",
        "sales.event_to_opportunity_pipeline",
        "sales.full_sales_cycle_orchestrator",
        "sales.cross_platform_account_health_score",
        "sales.demo_scheduling",
    ]
    evaluation._write_report(
        artifacts, generated_markdown, generated_json, selected_tasks
    )
    assert generated_markdown.read_bytes() == (artifacts / "report.md").read_bytes()
    assert generated_json.read_bytes() == (artifacts / "report.json").read_bytes()


def test_report_is_configuration_isolated_statistically_correct_and_byte_stable(
    tmp_path,
):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    def write_artifact(
        filename,
        *,
        task_id=TASK_ID,
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
            "runtime": {
                "id": "custom",
                "label": "Custom agent",
                "version": "harness/v1",
            },
        }
        if identity == "config-b":
            configuration["prompt_version"] = "prompts/v2"
        payload = RunArtifact(
            run_id=f"{identity}-{repetition}",
            task={
                "task_id": task_id,
                "name": task_id,
                "prompt": [],
                "tools": [],
                "assertions": [],
                "tool_definitions": [],
            },
            configuration=configuration,
            timing=ArtifactTiming(
                started_at="2026-07-17T12:00:00+00:00",
                updated_at="2026-07-17T12:00:01+00:00",
                finished_at="2026-07-17T12:00:01+00:00",
                duration_ms=duration,
            ),
            status="completed",
            termination_reason=reason,
            trace=(),
            summary=ArtifactSummary(0, turns, tool_calls, tool_error),
            usage={"total_tokens": tokens},
            final_response="done",
            terminal_error=None,
            evaluation_error=None,
            worlds=ArtifactWorlds({}, {}),
            evaluation=ArtifactEvaluation(
                available=True,
                official_score={
                    "partial_credit": partial,
                    "task_completed_correctly": strict,
                },
                assertion_evidence=(),
                context={
                    "configuration_identity": identity,
                    "repetition": repetition,
                    "fresh_world": True,
                    "resumed": False,
                    "infrastructure_replacement_count": 0,
                },
            ),
        ).to_dict()
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
    write_artifact(
        "second-task.json",
        task_id="sales.contract_renewal_coordinator",
        identity="config-a",
        repetition=1,
        partial=0.5,
        strict=0.0,
        tokens=40,
        duration=400,
        turns=4,
        tool_calls=8,
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
    group = next(
        item
        for item in report["groups"]
        if item["configuration"]["identity"] == "config-a"
        and item["task_id"] == TASK_ID
    )

    assert len(report["groups"]) == 3
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
    panel = report["panels"][0]
    assert panel["configuration"]["identity"] == "config-a"
    assert panel["coverage"] == {"scorable_count": 4, "task_count": 2}
    assert panel["strict_completion"] == {"count": 2, "percentage": 50.0}
    assert panel["partial_credit"] == {
        "maximum": 1.0,
        "mean": 0.5,
        "minimum": 0.0,
        "sample_standard_deviation": 0.408,
    }
    assert panel["tokens"] == {"maximum": 100, "median": 30.0, "minimum": 10}
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
    assert "| `config-a` | 2 | 4 | 2/4 (50.000%) |" in markdown
    assert all(name in markdown for name in ("a.json", "m.json", "z.json"))

    main(command)
    assert markdown_path.read_bytes() == first_markdown
    assert json_path.read_bytes() == first_json

    filtered_json_path = tmp_path / "filtered-report.json"
    main(
        [
            *command[:-1],
            str(filtered_json_path),
            "--task-id",
            "sales.contract_renewal_coordinator",
        ]
    )
    filtered_report = json.loads(filtered_json_path.read_text())
    assert [group["task_id"] for group in filtered_report["groups"]] == [
        "sales.contract_renewal_coordinator"
    ]
    assert filtered_report["panels"][0]["coverage"] == {
        "scorable_count": 1,
        "task_count": 1,
    }
