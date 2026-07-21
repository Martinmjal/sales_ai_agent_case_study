import json
import os
from pathlib import Path

import pytest

from sales_agent import config as runtime_config
from sales_agent import evaluation
from sales_agent.artifacts import (
    ArtifactEvaluation,
    ArtifactSummary,
    ArtifactTiming,
    ArtifactWorlds,
    RunArtifact,
)
from sales_agent.contract import (
    EventKind,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    TerminationReason,
)
from sales_agent.evaluation import main
from sales_agent.evaluation.records import EvaluationConfiguration, completed_triples
from sales_agent.evaluation.runner import MAX_INFRASTRUCTURE_REPLACEMENTS
from sales_agent.main import main as single_run_main
from sales_agent.plan_state_runtime import PLAN_STATE_LIMITS

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


def _outcome(run_id, *, infrastructure=False, adapter=False, failed=False):
    if infrastructure or adapter:
        events = (
            _event(
                run_id,
                EventKind.ADAPTER_ERROR if adapter else EventKind.MODEL_ERROR,
                content=(
                    {"message": "adapter unavailable"}
                    if adapter
                    else {"infrastructure_failure": True}
                ),
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
            termination_reason=(
                TerminationReason.ADAPTER_INITIALIZATION_FAILED
                if adapter
                else TerminationReason.MODEL_ERROR
            ),
        )
    reason = TerminationReason.RUNTIME_ERROR if failed else TerminationReason.GOAL_COMPLETED
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


def _write_evaluation_artifact(
    path: Path,
    configuration: EvaluationConfiguration,
    *,
    repetition: int,
    identity: str | None = None,
    run_id: str | None = None,
    score: dict | None = None,
) -> None:
    artifact_identity = identity or configuration.identity
    artifact_configuration = configuration.artifact_values()
    artifact_configuration["identity"] = artifact_identity
    payload = RunArtifact(
        run_id=run_id or f"run-{artifact_identity[:8]}-{repetition}-{path.stem}",
        task={
            "task_id": TASK_ID,
            "name": TASK_ID,
            "prompt": [],
            "tools": [],
            "assertions": [],
            "tool_definitions": [],
        },
        configuration=artifact_configuration,
        timing=ArtifactTiming(
            started_at="2026-07-17T12:00:00+00:00",
            updated_at="2026-07-17T12:00:01+00:00",
            finished_at="2026-07-17T12:00:01+00:00",
            duration_ms=100,
        ),
        status="completed",
        termination_reason="goal_completed",
        trace=(),
        summary=ArtifactSummary(0, 1, 0, False),
        usage={"total_tokens": 10},
        final_response="done",
        terminal_error=None,
        evaluation_error=None,
        worlds=ArtifactWorlds({}, {}),
        evaluation=ArtifactEvaluation(
            available=True,
            official_score=score or {"partial_credit": 1.0, "task_completed_correctly": 1.0},
            assertion_evidence=(),
            context={
                "configuration_identity": artifact_identity,
                "repetition": repetition,
                "fresh_world": True,
                "resumed": False,
                "infrastructure_replacement_count": 0,
            },
        ),
    ).to_dict()
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evaluation_immediate_success_writes_one_observation_without_replacements(tmp_path):
    manifest, config = _inputs(tmp_path)
    artifacts = tmp_path / "artifacts"
    calls = []

    class Runtime:
        async def run(self, request, **_):
            calls.append(request)
            return _outcome("immediate-success")

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
            str(artifacts),
        ],
        runtime_factory=Runtime,
    )

    records = [json.loads(path.read_text()) for path in artifacts.glob("*.json")]
    assert len(calls) == 1
    assert [record["run_id"] for record in records] == ["immediate-success"]
    assert records[0]["evaluation"]["context"]["infrastructure_replacement_count"] == 0


def test_persistent_infrastructure_failure_is_bounded_persisted_and_resumable(tmp_path):
    manifest, config_path = _inputs(tmp_path)
    config = EvaluationConfiguration.read(config_path)
    artifacts = tmp_path / "artifacts"
    attempts = iter(
        _outcome(f"persistent-infra-{index}", adapter=True)
        for index in range(MAX_INFRASTRUCTURE_REPLACEMENTS + 1)
    )
    calls = []

    class FailingRuntime:
        async def run(self, request, **_):
            calls.append(request)
            return next(attempts)

    command = [
        "run",
        "--manifest",
        str(manifest),
        "--config",
        str(config_path),
        "--repetitions",
        "1",
        "--artifacts-dir",
        str(artifacts),
    ]
    with pytest.raises(SystemExit) as raised:
        main(command, runtime_factory=FailingRuntime)

    assert len(calls) == MAX_INFRASTRUCTURE_REPLACEMENTS + 1
    assert "Infrastructure replacement limit exhausted" in str(raised.value)
    assert f"after {MAX_INFRASTRUCTURE_REPLACEMENTS} replacements" in str(raised.value)
    diagnostics = [json.loads(path.read_text()) for path in artifacts.glob("*.json")]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic["run_id"] == f"persistent-infra-{MAX_INFRASTRUCTURE_REPLACEMENTS}"
    assert diagnostic["evaluation"]["available"] is False
    assert diagnostic["evaluation"]["official_score"] == {}
    assert (
        diagnostic["evaluation"]["context"]["infrastructure_replacement_count"]
        == MAX_INFRASTRUCTURE_REPLACEMENTS
    )
    assert diagnostic["trace"][0]["kind"] == "adapter_error"
    assert diagnostic["terminal_error"] == "endpoint unavailable"
    assert "Infrastructure replacement limit exhausted" in diagnostic["evaluation_error"]
    assert completed_triples(artifacts, config) == set()

    resumed_calls = []

    class RecoveredRuntime:
        async def run(self, request, **_):
            resumed_calls.append(request)
            return _outcome("recovered-after-exhaustion")

    main(command, runtime_factory=RecoveredRuntime)

    persisted = [json.loads(path.read_text()) for path in artifacts.glob("*.json")]
    recovered = next(record for record in persisted if record["evaluation"]["available"])
    assert len(resumed_calls) == 1
    assert len(persisted) == 2
    assert recovered["run_id"] == "recovered-after-exhaustion"
    assert recovered["evaluation"]["context"]["resumed"] is True
    assert recovered["evaluation"]["context"]["infrastructure_replacement_count"] == 0
    assert completed_triples(artifacts, config) == {(config.identity, TASK_ID, 1)}

    main(
        [
            "report",
            "--manifest",
            str(manifest),
            "--config",
            str(config_path),
            "--repetitions",
            "1",
            "--artifacts-dir",
            str(artifacts),
            "--markdown",
            str(tmp_path / "report.md"),
            "--json",
            str(tmp_path / "report.json"),
        ]
    )
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["complete"] is True
    assert report["coverage"]["scorable_observation_count"] == 1
    assert len(report["coverage"]["unscorable"]) == 1


def test_evaluation_replaces_infrastructure_attempts_and_resumes_missing_runs(
    tmp_path,
):
    manifest, config = _inputs(tmp_path)
    artifacts = tmp_path / "artifacts"
    scripted = iter(
        [
            _outcome("infra-1", infrastructure=True),
            _outcome("infra-2", infrastructure=True),
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
                if len(runtime_instances) == 4:
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

    records = [json.loads(path.read_text()) for path in sorted(artifacts.glob("*.json"))]
    assert [record["run_id"] for record in records] == ["observed-1", "observed-2"]
    assert [record["evaluation"]["context"]["repetition"] for record in records] == [
        1,
        2,
    ]
    assert all(record["artifact_type"] == "run_artifact" for record in records)
    assert records[1]["termination_reason"] == "runtime_error"
    assert records[1]["evaluation"]["available"] is True
    assert records[1]["evaluation"]["context"]["infrastructure_replacement_count"] == 0
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
    assert records[0]["evaluation"]["official_score"]["task_completed_correctly"] == 1.0
    assert records[0]["evaluation"]["assertion_evidence"] == [{"passed": True}]
    assert records[0]["task"]["prompt"]
    assert records[0]["evaluation"]["context"] == {
        "configuration_identity": records[0]["configuration"]["identity"],
        "repetition": 1,
        "fresh_world": True,
        "resumed": False,
        "infrastructure_replacement_count": MAX_INFRASTRUCTURE_REPLACEMENTS,
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
    resumed = [json.loads(path.read_text()) for path in sorted(artifacts.glob("*.json"))]
    assert [record["run_id"] for record in resumed] == [
        "observed-1",
        "observed-2-replacement",
    ]
    assert resumed[1]["evaluation"]["context"]["resumed"] is True


def test_evaluation_command_loads_root_credentials(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "SALES_AGENT_PROVIDER_API_KEY=repository-key\n"
        "SALES_AGENT_PROVIDER_BASE_URL=https://provider.example/v1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SALES_AGENT_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("SALES_AGENT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.setattr(runtime_config, "REPOSITORY_ROOT", tmp_path)
    manifest, config = _inputs(tmp_path)

    class Runtime:
        async def run(self, request, **_):
            assert os.environ["SALES_AGENT_PROVIDER_API_KEY"] == "repository-key"
            assert os.environ["SALES_AGENT_PROVIDER_BASE_URL"] == ("https://provider.example/v1")
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
    assert "viewer: http://viewer/runs/single-run" in output

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
        evaluation.parser().parse_args(
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


def test_final_coverage_rejects_missing_duplicate_out_of_range_and_mixed_records(
    tmp_path,
):
    manifest, config_path = _inputs(tmp_path)
    config = EvaluationConfiguration.read(config_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_evaluation_artifact(artifacts / "r1.json", config, repetition=1)
    base = [
        "report",
        "--manifest",
        str(manifest),
        "--config",
        str(config_path),
        "--repetitions",
        "2",
        "--artifacts-dir",
        str(artifacts),
        "--markdown",
        str(tmp_path / "report.md"),
        "--json",
        str(tmp_path / "report.json"),
    ]

    with pytest.raises(ValueError, match=f"missing scorable observations: {TASK_ID}/r2"):
        main(base)

    main([*base, "--exploratory"])
    exploratory = json.loads((tmp_path / "report.json").read_text())
    assert exploratory["complete"] is False
    assert exploratory["coverage"]["missing"] == [{"task_id": TASK_ID, "repetition": 2}]

    duplicate = artifacts / "duplicate-r1.json"
    _write_evaluation_artifact(duplicate, config, repetition=1)
    with pytest.raises(ValueError, match="Duplicate evaluation observations"):
        main([*base, "--exploratory"])
    duplicate.unlink()

    out_of_range = artifacts / "r3.json"
    _write_evaluation_artifact(out_of_range, config, repetition=3)
    with pytest.raises(ValueError, match="Out-of-range evaluation repetitions"):
        main([*base, "--exploratory"])
    out_of_range.unlink()

    _write_evaluation_artifact(artifacts / "r2.json", config, repetition=2)
    _write_evaluation_artifact(
        artifacts / "foreign.json",
        config,
        repetition=1,
        identity="b" * 64,
    )
    with pytest.raises(ValueError, match="mixed configurations"):
        main(base)
    (artifacts / "foreign.json").unlink()

    incompatible = json.loads((artifacts / "r2.json").read_text())
    incompatible["configuration"]["prompt_version"] = "different-prompts/v1"
    (artifacts / "r2.json").write_text(json.dumps(incompatible), encoding="utf-8")
    with pytest.raises(ValueError, match="Configuration identity payload mismatch"):
        main(base)


def test_historical_artifact_is_rejected_without_rewrite(tmp_path):
    manifest, config_path = _inputs(tmp_path)
    config = EvaluationConfiguration.read(config_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    legacy = artifacts / "legacy.json"
    legacy.write_text(
        json.dumps(
            {
                "artifact_type": "agent_evaluation_run",
                "schema_version": 1,
                "run_id": "legacy-run",
                "task_id": TASK_ID,
                "configuration": config.artifact_values(),
                "repetition": 1,
                "timing": {
                    "started_at": "2026-07-17T12:00:00+00:00",
                    "finished_at": "2026-07-17T12:00:01+00:00",
                    "duration_ms": 100,
                },
                "status": "completed",
                "termination_reason": "goal_completed",
                "trace": [],
                "usage": {"total_tokens": 10},
                "worlds": {"initial": {}, "final": {}},
                "official_score": {
                    "partial_credit": 1.0,
                    "task_completed_correctly": 1.0,
                },
                "assertion_evidence": [],
                "evaluation_available": True,
            }
        ),
        encoding="utf-8",
    )
    original = legacy.read_bytes()

    assert completed_triples(artifacts) == set()
    with pytest.raises(ValueError, match="missing scorable observations"):
        main(
            [
                "report",
                "--manifest",
                str(manifest),
                "--config",
                str(config_path),
                "--repetitions",
                "1",
                "--artifacts-dir",
                str(artifacts),
                "--markdown",
                str(tmp_path / "report.md"),
                "--json",
                str(tmp_path / "report.json"),
            ]
        )

    assert legacy.read_bytes() == original
    assert sorted(path.name for path in artifacts.iterdir()) == ["legacy.json"]
    assert not (tmp_path / "report.md").exists()


def test_committed_evaluation_corpus_is_canonical_unique_and_report_reproducible(
    tmp_path,
):
    project_root = Path(__file__).resolve().parents[1]
    artifacts = project_root / "results" / "evaluation"
    paths = sorted(path for path in artifacts.glob("*.json") if path.name != "report.json")
    records = [json.loads(path.read_text()) for path in paths]

    assert len(records) == 61
    assert all(record["artifact_type"] == "run_artifact" for record in records)
    assert len({record["run_id"] for record in records}) == len(records)
    assert {record["configuration"]["identity"] for record in records} == {
        "a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c"
    }
    historical_config = project_root / "evaluation" / "config.planner-executor-v2.json"
    assert (
        EvaluationConfiguration.read(historical_config).identity
        == "a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c"
    )
    assert not list((project_root / "sessions").glob("evaluation_*.json"))

    generated_markdown = tmp_path / "report.md"
    generated_json = tmp_path / "report.json"
    selected_tasks = [
        "sales.contract_renewal_coordinator",
        "sales.event_to_opportunity_pipeline",
        "sales.full_sales_cycle_orchestrator",
        "sales.cross_platform_account_health_score",
        "sales.demo_scheduling",
    ]
    main(
        [
            "report",
            "--manifest",
            str(project_root / "evaluation" / "manifest.json"),
            "--config",
            str(historical_config),
            "--repetitions",
            "10",
            "--artifacts-dir",
            str(artifacts),
            "--markdown",
            str(generated_markdown),
            "--json",
            str(generated_json),
            "--exploratory",
            *[argument for task in selected_tasks for argument in ("--task-id", task)],
        ]
    )
    generated = json.loads(generated_json.read_text())
    committed = json.loads((artifacts / "report.json").read_text())
    for report in (generated, committed):
        for group in report["groups"]:
            for artifact in group["artifacts"]:
                artifact.pop("path")
    assert generated == committed
    assert "INCOMPLETE EXPLORATORY ANALYSIS" in generated_markdown.read_text()


def test_report_is_configuration_isolated_statistically_correct_and_byte_stable(
    tmp_path,
):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    manifest_path, config_path = _inputs(tmp_path)
    configuration = EvaluationConfiguration.read(config_path)

    def write_artifact(
        filename,
        *,
        task_id=TASK_ID,
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
        payload = RunArtifact(
            run_id=f"{task_id}-{repetition}",
            task={
                "task_id": task_id,
                "name": task_id,
                "prompt": [],
                "tools": [],
                "assertions": [],
                "tool_definitions": [],
            },
            configuration=configuration.artifact_values(),
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
                    "configuration_identity": configuration.identity,
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
    markdown_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    command = [
        "report",
        "--manifest",
        str(manifest_path),
        "--config",
        str(config_path),
        "--repetitions",
        "3",
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
        if item["configuration"]["identity"] == configuration.identity
        and item["task_id"] == TASK_ID
    )

    assert report["mode"] == "final"
    assert report["complete"] is True
    assert report["coverage"]["coverage_complete"] is True
    assert len(report["groups"]) == 1
    assert group["configuration"]["identity"] == configuration.identity
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
    assert panel["configuration"]["identity"] == configuration.identity
    assert panel["coverage"] == {"scorable_count": 3, "task_count": 1}
    assert panel["strict_completion"] == {"count": 2, "percentage": 66.667}
    assert panel["partial_credit"] == {
        "maximum": 1.0,
        "mean": 0.5,
        "minimum": 0.0,
        "sample_standard_deviation": 0.5,
    }
    assert panel["tokens"] == {"maximum": 100, "median": 20, "minimum": 10}
    markdown = first_markdown.decode()
    assert json.dumps(report["panels"], indent=2, sort_keys=True) in markdown
    assert (
        json.dumps(
            {"selection": report["selection"], "coverage": report["coverage"]},
            indent=2,
            sort_keys=True,
        )
        in markdown
    )
    for heading in (
        "## Configuration",
        "## Coverage",
        "## Panel Summary",
        "## Per-task Results",
        "## Termination Evidence",
        "## Run Artifacts",
    ):
        assert heading in markdown
    assert configuration.identity in markdown
    assert '"percentage": 66.667' in markdown
    assert all(name in markdown for name in ("a.json", "m.json", "z.json"))

    main(command)
    assert markdown_path.read_bytes() == first_markdown
    assert json_path.read_bytes() == first_json

    assert all(
        (json_path.parent / artifact["path"]).resolve().is_file() for artifact in group["artifacts"]
    )
    assert all(
        artifact["viewer_url"].endswith(f"/runs/{artifact['run_id']}")
        for artifact in group["artifacts"]
    )

    with pytest.raises(ValueError, match="require --exploratory"):
        main([*command, "--task-id", TASK_ID])

    exploratory_json = tmp_path / "exploratory.json"
    exploratory_markdown = tmp_path / "exploratory.md"
    main(
        [
            *command[:-3],
            str(exploratory_markdown),
            "--json",
            str(exploratory_json),
            "--exploratory",
            "--task-id",
            TASK_ID,
        ]
    )
    exploratory = json.loads(exploratory_json.read_text())
    assert exploratory["mode"] == "exploratory"
    assert exploratory["complete"] is False
    assert exploratory["selection"]["task_filters"] == [TASK_ID]
    assert "INCOMPLETE EXPLORATORY ANALYSIS" in exploratory_markdown.read_text()
