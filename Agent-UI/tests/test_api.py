import asyncio
from contextlib import contextmanager
import json
import socket
from threading import Event
from threading import Thread
from time import sleep

from agent_ui.app import (
    BASELINE_RUNTIME_ID,
    DEFAULT_RUNTIME_ID,
    PLAN_STATE_RUNTIME_ID,
    AgentConfig,
    RuntimeRegistration,
    create_app,
)
from agent_ui.store import ImmutableSessionError, SessionStore
from fastapi.testclient import TestClient
import httpx
from mock_agent.contract import EventKind, ExitStatus, RuntimeEvent, RuntimeOutcome
from mock_agent.model import ModelReply
from mock_agent.planner_executor import PlannerExecutorRuntime
import pytest
import uvicorn


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)

    async def respond(self, _request):
        return next(self.replies)


def scripted_runtime():
    return PlannerExecutorRuntime(
        model_client=ScriptedModel(
            [
                ModelReply(
                    content={
                        "goal": "Inspect the task.",
                        "steps": [
                            {
                                "id": "inspect",
                                "objective": "Inspect the task.",
                                "required_evidence": [
                                    {
                                        "requirement": "A grounded result",
                                        "source_tools": ["zoom_list_meetings"],
                                    }
                                ],
                            }
                        ],
                    },
                    usage={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                ),
                ModelReply(
                    content={
                        "summary": "The task was inspected.",
                        "evidence": [],
                        "actions": [],
                        "errors": [],
                    },
                    usage={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                ),
                ModelReply(
                    content={
                        "decision": "goal_completed",
                        "final_response": "Scripted final response.",
                    },
                    usage={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                ),
            ]
        )
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


class ControlledRuntime:
    def __init__(self, boundary):
        self.boundary = boundary
        self.started = Event()
        self.release = Event()

    async def run(self, request, *, event_sink=None, cancellation=None):
        events = [
            RuntimeEvent(
                sequence=1,
                kind=(
                    EventKind.MODEL_TURN
                    if self.boundary == "model"
                    else EventKind.TOOL_CALL
                ),
                timestamp="2026-07-16T02:00:00+00:00",
                run_id=f"{self.boundary}-run",
                correlation_id=f"{self.boundary}-boundary",
                name="update_account" if self.boundary == "tool" else None,
                content="Working" if self.boundary == "model" else None,
                arguments={"account_id": "account-1"}
                if self.boundary == "tool"
                else None,
            )
        ]
        if event_sink is not None:
            await event_sink(events[0])
        self.started.set()
        await asyncio.to_thread(self.release.wait)
        if self.boundary == "tool":
            events.append(
                RuntimeEvent(
                    sequence=2,
                    kind=EventKind.TOOL_RESULT,
                    timestamp="2026-07-16T02:00:01+00:00",
                    run_id="tool-run",
                    correlation_id="tool-boundary",
                    name="update_account",
                    result={"updated": True},
                )
            )
            if event_sink is not None:
                await event_sink(events[-1])
        status = (
            ExitStatus.STOPPED if cancellation.is_cancelled else ExitStatus.COMPLETED
        )
        return RuntimeOutcome(
            status=status,
            task_id=request.task_id,
            run_id=f"{self.boundary}-run",
            events=tuple(events),
            final_response=None,
            world_state={"boundary": self.boundary},
            score={"partial_credit": 0.5, "assertions": []},
            usage={"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
        )


class FatalRuntime:
    async def run(self, request, *, event_sink=None, cancellation=None):
        if event_sink is not None:
            await event_sink(
                RuntimeEvent(
                    sequence=1,
                    kind=EventKind.TOOL_ERROR,
                    timestamp="2026-07-16T02:00:00+00:00",
                    run_id="fatal-run",
                    correlation_id="failed-call",
                    name="update_account",
                    error="CRM rejected account-1 exactly as emitted",
                )
            )
        raise RuntimeError("scripted runtime failure")


@contextmanager
def live_server(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    config = uvicorn.Config(app, log_level="error", lifespan="on")
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
        runtime=scripted_runtime(),
        sessions_dir=tmp_path,
        config=AgentConfig(
            model="scripted-test",
            max_steps=12,
            agent_version="planner-executor/0.2.0",
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
    assert artifact["lifecycle"]["termination_reason"] == "goal_completed"
    assert artifact["runtime"] == {
        "id": "custom",
        "label": "Custom agent",
        "version": "planner-executor/0.2.0",
    }
    assert artifact["agent"]["agent_version"] == artifact["runtime"]["version"]
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


def test_runtime_registry_validates_selection_and_defaults_to_custom(tmp_path):
    runtime = BlockingRuntime()
    app = create_app(runtime=runtime, sessions_dir=tmp_path)

    with TestClient(app) as client:
        registry = client.get("/api/runtimes")
        invalid = client.post(
            "/api/sessions",
            json={
                "task_id": "sales.zoom_calendar_conflict",
                "runtime_id": "not-registered",
            },
        )
        started = client.post(
            "/api/sessions",
            json={"task_id": "sales.zoom_calendar_conflict"},
        )
        assert runtime.started.wait(timeout=2)
        artifact = client.get(f"/api/sessions/{started.json()['session_id']}").json()
        runtime.release.set()

    assert registry.status_code == 200
    assert registry.json() == {
        "default_runtime_id": DEFAULT_RUNTIME_ID,
        "runtimes": [
            {
                "id": DEFAULT_RUNTIME_ID,
                "label": "Custom agent",
                "version": "planner-executor/0.2.0",
            },
            {
                "id": PLAN_STATE_RUNTIME_ID,
                "label": "Plan-state agent",
                "version": "plan-state/0.1.0",
            },
            {
                "id": BASELINE_RUNTIME_ID,
                "label": "Mock/baseline agent",
                "version": "baseline/0.1.0",
            },
        ],
    }
    assert invalid.status_code == 422
    assert "Unknown runtime ID: not-registered" in invalid.json()["detail"]
    assert started.status_code == 202
    assert artifact["runtime"]["id"] == DEFAULT_RUNTIME_ID
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_runtime_selection_is_frozen_per_session_and_persisted_in_history(tmp_path):
    custom = BlockingRuntime()
    baseline = PacedRuntime()
    registry = {
        DEFAULT_RUNTIME_ID: RuntimeRegistration(
            runtime_id=DEFAULT_RUNTIME_ID,
            label="Custom agent",
            version="custom/test-1",
            runtime=custom,
        ),
        BASELINE_RUNTIME_ID: RuntimeRegistration(
            runtime_id=BASELINE_RUNTIME_ID,
            label="Mock/baseline agent",
            version="baseline/test-2",
            runtime=baseline,
        ),
    }
    app = create_app(runtime_registry=registry, sessions_dir=tmp_path)

    with TestClient(app) as client:
        first = client.post(
            "/api/sessions",
            json={
                "task_id": "sales.zoom_calendar_conflict",
                "runtime_id": DEFAULT_RUNTIME_ID,
            },
        )
        assert custom.started.wait(timeout=2)
        rejected = client.post(
            "/api/sessions",
            json={
                "task_id": "sales.multi_hop_lookup",
                "runtime_id": BASELINE_RUNTIME_ID,
            },
        )
        running = client.get(f"/api/sessions/{first.json()['session_id']}").json()
        custom.release.set()
        for _ in range(100):
            completed = client.get(
                f"/api/sessions/{first.json()['session_id']}"
            ).json()
            if completed["status"] == "Completed":
                break
            sleep(0.01)

        second = client.post(
            "/api/sessions",
            json={
                "task_id": "sales.multi_hop_lookup",
                "runtime_id": BASELINE_RUNTIME_ID,
            },
        )
        for _ in range(100):
            baseline_artifact = client.get(
                f"/api/sessions/{second.json()['session_id']}"
            ).json()
            if baseline_artifact["status"] == "Completed":
                break
            sleep(0.01)
        summaries = client.get("/api/sessions").json()["sessions"]

    assert rejected.status_code == 409
    assert running["runtime"] == {
        "id": DEFAULT_RUNTIME_ID,
        "label": "Custom agent",
        "version": "custom/test-1",
    }
    assert completed["runtime"] == running["runtime"]
    assert baseline_artifact["runtime"] == {
        "id": BASELINE_RUNTIME_ID,
        "label": "Mock/baseline agent",
        "version": "baseline/test-2",
    }
    assert baseline_artifact["agent"]["agent_version"] == "baseline/test-2"
    assert {
        summary["session_id"]: (
            summary["runtime_id"],
            summary["runtime_label"],
            summary["runtime_version"],
        )
        for summary in summaries
    } == {
        first.json()["session_id"]: (
            DEFAULT_RUNTIME_ID,
            "Custom agent",
            "custom/test-1",
        ),
        second.json()["session_id"]: (
            BASELINE_RUNTIME_ID,
            "Mock/baseline agent",
            "baseline/test-2",
        ),
    }


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


def test_history_skips_unsupported_artifacts_and_terminal_sessions_are_immutable(
    tmp_path,
):
    store = SessionStore(tmp_path)
    terminal = store.create(
        {
            "schema_version": 1,
            "session_id": "completed-session",
            "status": "Completed",
            "lifecycle": {
                "created_at": "2026-07-15T12:00:00+00:00",
                "updated_at": "2026-07-15T12:01:00+00:00",
                "completed_at": "2026-07-15T12:01:00+00:00",
                "terminal_error": None,
            },
            "task": {
                "task_id": "sales.zoom_calendar_conflict",
                "name": "Zoom Calendar Conflict",
                "prompt": [{"role": "user", "content": "Resolve the conflict."}],
            },
            "agent": {
                "model": "scripted-test",
                "max_steps": 12,
                "agent_version": "mock-agent/0.1.0",
            },
            "events": [],
            "final_response": "Resolved.",
            "evaluation": {"partial_credit": 1.0},
            "usage": None,
            "initial_world": {},
            "final_world": {},
        }
    )
    (tmp_path / "malformed.json").write_text("not json", encoding="utf-8")
    (tmp_path / "unsupported.json").write_text(
        json.dumps({"schema_version": 99, "session_id": "future-session"}),
        encoding="utf-8",
    )

    changed = {**terminal, "status": "Failed"}
    with pytest.raises(ImmutableSessionError):
        store.save(changed)

    with TestClient(create_app(sessions_dir=tmp_path)) as client:
        history = client.get("/api/sessions")

    assert history.status_code == 200
    assert [session["session_id"] for session in history.json()["sessions"]] == [
        "completed-session"
    ]


def test_execution_control_preserves_safe_boundary_state_and_fatal_evidence(tmp_path):
    task_id = "sales.zoom_calendar_conflict"

    for boundary in ("model", "tool"):
        runtime = ControlledRuntime(boundary)
        app = create_app(runtime=runtime, sessions_dir=tmp_path / boundary)
        with TestClient(app) as client:
            started = client.post("/api/sessions", json={"task_id": task_id})
            session_id = started.json()["session_id"]
            assert runtime.started.wait(timeout=2)

            stop = client.post(f"/api/sessions/{session_id}/stop")
            runtime.release.set()
            for _ in range(100):
                artifact = client.get(f"/api/sessions/{session_id}").json()
                if artifact["status"] == "Stopped":
                    break
                sleep(0.01)

            repeated_stop = client.post(f"/api/sessions/{session_id}/stop")

        assert stop.status_code == 202
        assert artifact["status"] == "Stopped"
        assert artifact["final_world"] == {"boundary": boundary}
        assert artifact["evaluation"]["partial_credit"] == 0.5
        assert [event["kind"] for event in artifact["events"]] == (
            ["model_turn"] if boundary == "model" else ["tool_call", "tool_result"]
        )
        assert repeated_stop.status_code == 409

    app = create_app(runtime=FatalRuntime(), sessions_dir=tmp_path / "fatal")
    with TestClient(app) as client:
        started = client.post("/api/sessions", json={"task_id": task_id})
        session_id = started.json()["session_id"]
        for _ in range(100):
            artifact = client.get(f"/api/sessions/{session_id}").json()
            if artifact["status"] == "Failed":
                break
            sleep(0.01)

    assert artifact["status"] == "Failed"
    assert artifact["evaluation"] is None
    assert artifact["events"][0]["error"] == "CRM rejected account-1 exactly as emitted"
    assert artifact["lifecycle"]["terminal_error"] == (
        "RuntimeError: scripted runtime failure"
    )
