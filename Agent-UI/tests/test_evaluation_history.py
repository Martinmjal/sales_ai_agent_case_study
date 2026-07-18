import json

from agent_ui.app import create_app
from fastapi.testclient import TestClient
from mock_agent.contract import (
    EventKind,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    TerminationReason,
)
from mock_agent.evaluation import main
from mock_agent.plan_state_runtime import PLAN_STATE_LIMITS


TASK_ID = "sales.zoom_calendar_conflict"


def test_batch_executions_are_available_from_agent_ui_history(tmp_path):
    manifest = tmp_path / "manifest.json"
    config = tmp_path / "config.json"
    artifacts = tmp_path / "evaluation"
    sessions = tmp_path / "sessions"
    manifest.write_text(json.dumps({"tasks": [TASK_ID]}), encoding="utf-8")
    config.write_text(
        json.dumps(
            {
                "model": "scripted-model",
                "harness_version": "plan-state/test",
                "prompt_version": "plan-state-prompts/v1-test",
                "evaluation_protocol_version": "sales-panel/test",
                "execution_limits": PLAN_STATE_LIMITS,
            }
        ),
        encoding="utf-8",
    )
    run_ids = iter(("evaluation-run-1", "evaluation-run-2"))

    class Runtime:
        async def run(self, request, **_):
            run_id = next(run_ids)
            event = RuntimeEvent(
                sequence=1,
                kind=EventKind.COMPLETION,
                timestamp="2026-07-17T12:00:00+00:00",
                run_id=run_id,
                correlation_id=run_id,
                content={"termination_reason": "goal_completed"},
            )
            return RuntimeOutcome(
                status=ExitStatus.COMPLETED,
                task_id=request.task_id,
                run_id=run_id,
                events=(event,),
                final_response=f"Completed {run_id}",
                world_state={"run_id": run_id},
                score={
                    "partial_credit": 1.0,
                    "task_completed_correctly": 1.0,
                    "assertions": [{"passed": True}],
                },
                usage={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                termination_reason=TerminationReason.GOAL_COMPLETED,
            )

    command = [
        "run",
        "--manifest",
        str(manifest),
        "--config",
        str(config),
        "--repetitions",
        "2",
        "--artifacts-dir",
        str(artifacts),
        "--sessions-dir",
        str(sessions),
    ]
    main(command, runtime_factory=Runtime)

    with TestClient(create_app(sessions_dir=sessions)) as client:
        history = client.get("/api/sessions").json()["sessions"]
        details = [client.get(f"/api/sessions/{item['session_id']}").json() for item in history]

    assert len(history) == 2
    assert {item["session_id"] for item in history} == {
        "evaluation-run-1",
        "evaluation-run-2",
    }
    assert all(item["runtime_id"] == "custom" for item in history)
    assert all(item["task_id"] == TASK_ID for item in history)
    assert all(item["status"] == "Completed" for item in history)
    assert all(item["evaluation"]["task_completed_correctly"] == 1.0 for item in details)
    assert all(item["events"][0]["kind"] == "completion" for item in details)
    assert all(item["evaluation_run"]["repetition"] in {1, 2} for item in details)
    assert len(list(artifacts.glob("*.json"))) == 2
    assert len(list(sessions.glob("*.json"))) == 2

    next(sessions.glob("*.json")).unlink()
    main(
        command,
        runtime_factory=lambda: (_ for _ in ()).throw(
            AssertionError("persisted evaluation runs must not execute again")
        ),
    )
    with TestClient(create_app(sessions_dir=sessions)) as client:
        resumed_history = client.get("/api/sessions").json()["sessions"]

    assert len(resumed_history) == 2
