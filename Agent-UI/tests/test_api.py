import asyncio
from contextlib import contextmanager
import json
import socket
from threading import Event
from threading import Thread
from time import sleep

from agent_ui.app import AgentConfig, create_app
from fastapi.testclient import TestClient
import httpx
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from mock_agent.contract import EventKind, ExitStatus, RuntimeEvent, RuntimeOutcome
from mock_agent.runtime import MockAgentRuntime
import uvicorn


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


class PacedRuntime:
    async def run(self, request, *, event_sink=None, cancellation=None):
        events = (
            RuntimeEvent(
                sequence=40,
                kind=EventKind.MODEL_TURN,
                timestamp="2026-07-16T01:00:00+00:00",
                run_id="paced-run",
                correlation_id="turn-1",
                content="Checking the account.",
            ),
            RuntimeEvent(
                sequence=90,
                kind=EventKind.TOOL_CALL,
                timestamp="2026-07-16T01:00:01+00:00",
                run_id="paced-run",
                correlation_id="call-1",
                parent_id="turn-1",
                name="search_accounts",
                arguments={"name": "Acme"},
            ),
            RuntimeEvent(
                sequence=140,
                kind=EventKind.TOOL_RESULT,
                timestamp="2026-07-16T01:00:02+00:00",
                run_id="paced-run",
                correlation_id="call-1",
                name="search_accounts",
                result={"id": "account-1"},
            ),
        )
        for event in events:
            if event_sink is not None:
                await event_sink(event)
            await asyncio.sleep(0.08)
        return RuntimeOutcome(
            status=ExitStatus.COMPLETED,
            task_id=request.task_id,
            run_id="paced-run",
            events=events,
            final_response="Account located.",
            world_state={},
            score={
                "partial_credit": 1.0,
                "task_completed_correctly": 1.0,
                "assertions": [],
            },
            usage={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        )


@contextmanager
def live_server(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    config = uvicorn.Config(app, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=2)


def next_sse_event(lines):
    event = {}
    for line in lines:
        if not line:
            if event:
                return event
            continue
        field, value = line.split(":", 1)
        event[field] = value.lstrip()
    raise AssertionError("SSE stream ended before the next event")


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


def test_execution_stream_resumes_after_disconnect_without_losing_events(tmp_path):
    app = create_app(runtime=PacedRuntime(), sessions_dir=tmp_path)

    with (
        live_server(app) as base_url,
        httpx.Client(base_url=base_url, timeout=3) as client,
    ):
        started = client.post(
            "/api/sessions",
            json={"task_id": "sales.zoom_calendar_conflict"},
        )
        session_id = started.json()["session_id"]

        with client.stream("GET", f"/api/sessions/{session_id}/events") as stream:
            assert stream.status_code == 200
            first = next_sse_event(stream.iter_lines())

        materialized = client.get(f"/api/sessions/{session_id}").json()
        assert materialized["events"][0]["sequence"] == 1

        with client.stream(
            "GET",
            f"/api/sessions/{session_id}/events",
            headers={"Last-Event-ID": first["id"]},
        ) as stream:
            resumed = [first]
            lines = stream.iter_lines()
            while len(resumed) < 3:
                resumed.append(next_sse_event(lines))

        for _ in range(100):
            completed = client.get(f"/api/sessions/{session_id}").json()
            if completed["status"] == "Completed":
                break
            sleep(0.01)

    assert [int(event["id"]) for event in resumed] == [1, 2, 3]
    assert [json.loads(event["data"])["sequence"] for event in resumed] == [1, 2, 3]
    assert completed["status"] == "Completed"
    assert [event["sequence"] for event in completed["events"]] == [1, 2, 3]
