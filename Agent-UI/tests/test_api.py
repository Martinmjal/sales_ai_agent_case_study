import asyncio
import json
from threading import Event
from time import sleep

from agent_ui.app import AgentConfig, create_app
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from mock_agent.runtime import MockAgentRuntime
from mock_agent.contract import ExitStatus, RuntimeOutcome


def scripted_agent(_messages):
    return AIMessage(
        content="Scripted final response.",
        usage_metadata={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
    )


class BlockingRuntime:
    def __init__(self):
        self.started = Event()
        self.release = Event()

    async def run(self, request, *, event_sink=None, cancellation=None):
        self.started.set()
        await asyncio.to_thread(self.release.wait)
        return RuntimeOutcome(
            status=ExitStatus.COMPLETED,
            task_id=request.task_id,
            run_id="scripted-blocking-run",
            events=(),
            final_response="Released.",
            world_state={},
            score={
                "partial_credit": 0.0,
                "task_completed_correctly": 0.0,
                "assertions": [],
            },
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )


def test_evaluator_can_run_a_catalog_task_and_reopen_its_artifact(tmp_path):
    app = create_app(
        runtime=MockAgentRuntime(agent_model=RunnableLambda(scripted_agent)),
        sessions_dir=tmp_path,
        config=AgentConfig(
            model="scripted-test",
            max_steps=12,
            agent_version="mock-agent/0.1.0",
        ),
    )

    with TestClient(app) as client:
        tasks = client.get("/api/tasks")
        assert tasks.status_code == 200
        assert len(tasks.json()["tasks"]) == 100

        started = client.post(
            "/api/sessions",
            json={"task_id": "sales.zoom_calendar_conflict"},
        )
        assert started.status_code == 202
        session_id = started.json()["session_id"]

        for _ in range(100):
            session = client.get(f"/api/sessions/{session_id}")
            if session.json()["status"] == "Completed":
                break
            sleep(0.01)

        artifact = session.json()
        summaries = client.get("/api/sessions").json()["sessions"]

    assert artifact["final_response"] == "Scripted final response."
    assert artifact["evaluation"] is not None
    assert {
        "schema_version",
        "session_id",
        "lifecycle",
        "task",
        "agent",
        "events",
        "usage",
        "initial_world",
        "final_world",
    } <= artifact.keys()
    assert summaries[0]["session_id"] == session_id
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == artifact


def test_second_execution_is_rejected_while_one_is_running(tmp_path):
    runtime = BlockingRuntime()
    app = create_app(runtime=runtime, sessions_dir=tmp_path)

    with TestClient(app) as client:
        first = client.post(
            "/api/sessions",
            json={"task_id": "sales.zoom_calendar_conflict"},
        )
        assert runtime.started.wait(timeout=2)

        second = client.post(
            "/api/sessions",
            json={"task_id": "sales.multi_hop_lookup"},
        )

        runtime.release.set()

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["detail"]["active_session_id"] == first.json()["session_id"]
