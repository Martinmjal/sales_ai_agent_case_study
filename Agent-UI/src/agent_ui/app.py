from __future__ import annotations

import asyncio
import copy
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mock_agent.adapter import AutomationBenchAdapter
from mock_agent.catalog import TaskCatalog, TaskDefinition, UnknownTaskError
from mock_agent.contract import (
    AgentRuntime,
    CancellationSignal,
    ExitStatus,
    RuntimeEvent,
    RuntimeRequest,
)
from mock_agent.model import OpenAIModelClient
from mock_agent.planner_executor import PlannerExecutorRuntime

from agent_ui.store import SessionNotFoundError, SessionStore
from agent_ui.world_diff import world_change_evidence


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


@dataclass(frozen=True)
class AgentConfig:
    model: str = "gpt-5.6-sol"
    max_steps: int = 12
    agent_version: str = "planner-executor/0.2.0"


class CreateSessionRequest(BaseModel):
    task_id: str


class ActiveSessionError(RuntimeError):
    """Raised when another execution already owns the runtime."""


class SessionNotRunningError(RuntimeError):
    """Raised when execution control targets a session without a live owner."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_payload(event: RuntimeEvent) -> dict[str, Any]:
    return asdict(event)


def _task_payload(task: TaskDefinition) -> dict[str, Any]:
    return {
        "task_id": task.summary.task_id,
        "name": task.summary.task_id.removeprefix("sales.").replace("_", " ").title(),
        "example_id": task.summary.example_id,
        "prompt": [asdict(message) for message in task.summary.prompt],
        "tools": list(task.summary.tools),
        "assertion_count": task.summary.assertion_count,
    }


def _tool_definitions(
    task: TaskDefinition, adapter: AutomationBenchAdapter
) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in adapter.open(task.summary.task_id).agent_task.tools
    ]


def _summary(session: dict[str, Any]) -> dict[str, Any]:
    evaluation = session.get("evaluation") or {}
    return {
        "session_id": session["session_id"],
        "created_at": session["lifecycle"]["created_at"],
        "status": session["status"],
        "task_id": session["task"]["task_id"],
        "task_name": session["task"]["name"],
        "partial_credit": evaluation.get("partial_credit"),
    }


class ExecutionManager:
    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        catalog: TaskCatalog,
        adapter: AutomationBenchAdapter,
        store: SessionStore,
        config: AgentConfig,
    ) -> None:
        self.runtime = runtime
        self.catalog = catalog
        self.adapter = adapter
        self.store = store
        self.config = config
        self._active_session_id: str | None = None
        self._lock = asyncio.Lock()
        self._event_locks: dict[str, asyncio.Lock] = {}
        self._cancellations: dict[str, CancellationSignal] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def start(self, task_id: str) -> dict[str, Any]:
        async with self._lock:
            if self._active_session_id is not None:
                active = self.store.read(self._active_session_id)
                if active["status"] == "Running":
                    raise ActiveSessionError(self._active_session_id)
                self._active_session_id = None

            task = self.catalog.get_task(task_id)
            session = self.store.create(self._new_session(task))
            self._active_session_id = session["session_id"]
            self._event_locks[session["session_id"]] = asyncio.Lock()
            self._cancellations[session["session_id"]] = CancellationSignal()
            background = asyncio.create_task(self._execute(session["session_id"]))
            self._background_tasks.add(background)
            background.add_done_callback(self._background_tasks.discard)
            return _summary(session)

    async def stop(self, session_id: str) -> dict[str, Any]:
        async with self._lock:
            if self._active_session_id != session_id:
                raise SessionNotRunningError(session_id)
            session = self.store.read(session_id)
            if session["status"] != "Running":
                raise SessionNotRunningError(session_id)
            self._cancellations[session_id].cancel()
            return _summary(session)

    def interrupt_orphans(self) -> None:
        for session in self.store.list():
            if session["status"] != "Running":
                continue
            interrupted_at = _now()
            session["status"] = "Interrupted"
            session["lifecycle"].update(
                {
                    "updated_at": interrupted_at,
                    "completed_at": interrupted_at,
                    "terminal_error": "Execution owner was lost when the server stopped.",
                }
            )
            self.store.save(session)

    def _new_session(self, task: TaskDefinition) -> dict[str, Any]:
        created_at = _now()
        task_payload = _task_payload(task)
        task_payload.update(
            {
                "assertions": copy.deepcopy(task.info["assertions"]),
                "tool_definitions": _tool_definitions(task, self.adapter),
            }
        )
        return {
            "schema_version": 1,
            "session_id": str(uuid4()),
            "status": "Running",
            "lifecycle": {
                "created_at": created_at,
                "updated_at": created_at,
                "completed_at": None,
                "terminal_error": None,
                "termination_reason": None,
            },
            "task": task_payload,
            "agent": asdict(self.config),
            "events": [],
            "final_response": None,
            "evaluation": None,
            "usage": None,
            "initial_world": copy.deepcopy(task.info["initial_state"]),
            "final_world": None,
        }

    async def _execute(self, session_id: str) -> None:
        async def persist_event(event: RuntimeEvent) -> None:
            async with self._event_locks[session_id]:
                session = self.store.read(session_id)
                payload = _event_payload(event)
                payload["sequence"] = len(session["events"]) + 1
                session["events"].append(payload)
                session["lifecycle"]["updated_at"] = _now()
                self.store.save(session)

        session = self.store.read(session_id)
        try:
            outcome = await self.runtime.run(
                RuntimeRequest(
                    task_id=session["task"]["task_id"],
                    model_name=self.config.model,
                    max_steps=self.config.max_steps,
                ),
                event_sink=persist_event,
                cancellation=self._cancellations[session_id],
            )
            session = self.store.read(session_id)
            completed_at = _now()
            session.update(
                {
                    "status": {
                        ExitStatus.COMPLETED: "Completed",
                        ExitStatus.STOPPED: "Stopped",
                        ExitStatus.FAILED: "Failed",
                    }[outcome.status],
                    "final_response": outcome.final_response,
                    "evaluation": outcome.score,
                    "usage": outcome.usage,
                    "final_world": outcome.world_state,
                }
            )
            session["lifecycle"].update(
                {
                    "updated_at": completed_at,
                    "completed_at": completed_at,
                    "terminal_error": outcome.terminal_error,
                    "termination_reason": outcome.termination_reason.value
                    if outcome.termination_reason
                    else None,
                }
            )
            self.store.save(session)
        except Exception as error:
            session = self.store.read(session_id)
            completed_at = _now()
            session["status"] = "Failed"
            session["lifecycle"].update(
                {
                    "updated_at": completed_at,
                    "completed_at": completed_at,
                    "terminal_error": f"{type(error).__name__}: {error}",
                    "termination_reason": "runtime_error",
                }
            )
            self.store.save(session)
        finally:
            async with self._lock:
                if self._active_session_id == session_id:
                    self._active_session_id = None
                self._cancellations.pop(session_id, None)

    async def stream_events(self, session_id: str, after: int) -> Any:
        next_sequence = max(after + 1, 1)
        while True:
            session = self.store.read(session_id)
            for event in session["events"]:
                sequence = event["sequence"]
                if sequence < next_sequence:
                    continue
                yield (
                    f"id: {sequence}\n"
                    "event: runtime\n"
                    f"data: {json.dumps(event, ensure_ascii=True, default=str)}\n\n"
                )
                next_sequence = sequence + 1
            if session["status"] != "Running" and next_sequence > len(
                session["events"]
            ):
                yield (
                    "event: session\n"
                    f"data: {json.dumps({'status': session['status']})}\n\n"
                )
                return
            await asyncio.sleep(0.05)


def create_app(
    *,
    runtime: AgentRuntime | None = None,
    sessions_dir: Path | None = None,
    config: AgentConfig | None = None,
) -> FastAPI:
    catalog = TaskCatalog.from_sales_dataset()
    adapter = AutomationBenchAdapter(catalog=catalog)
    manager = ExecutionManager(
        runtime=runtime
        or PlannerExecutorRuntime(
            model_client=OpenAIModelClient(),
            adapter=adapter,
        ),
        catalog=catalog,
        adapter=adapter,
        store=SessionStore(sessions_dir or REPOSITORY_ROOT / "sessions"),
        config=config or AgentConfig(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        manager.interrupt_orphans()
        yield

    app = FastAPI(title="Agent UI", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIRECTORY / "index.html")

    @app.get("/api/tasks")
    async def list_tasks() -> dict[str, Any]:
        return {
            "tasks": [
                _task_payload(catalog.get_task(summary.task_id))
                for summary in catalog.list_tasks()
            ]
        }

    @app.post("/api/sessions", status_code=status.HTTP_202_ACCEPTED)
    async def create_session(request: CreateSessionRequest) -> dict[str, Any]:
        try:
            return await manager.start(request.task_id)
        except UnknownTaskError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ActiveSessionError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "An execution is already running",
                    "active_session_id": str(error),
                },
            ) from error

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        return {"sessions": [_summary(session) for session in manager.store.list()]}

    @app.post("/api/sessions/{session_id}/stop", status_code=status.HTTP_202_ACCEPTED)
    async def stop_session(session_id: str) -> dict[str, Any]:
        try:
            return await manager.stop(session_id)
        except (SessionNotFoundError, SessionNotRunningError) as error:
            raise HTTPException(
                status_code=409,
                detail="Only the active running session can be stopped",
            ) from error

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        try:
            return manager.store.read(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/sessions/{session_id}/world-changes")
    async def get_world_changes(session_id: str) -> dict[str, Any]:
        try:
            session = manager.store.read(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {
            "changes": world_change_evidence(session),
        }

    @app.get("/api/sessions/{session_id}/events")
    async def stream_session_events(
        session_id: str,
        last_event_id: int = Header(default=0, alias="Last-Event-ID"),
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        try:
            manager.store.read(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return StreamingResponse(
            manager.stream_events(session_id, max(last_event_id, after)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app
