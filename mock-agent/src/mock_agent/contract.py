from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class EventKind(str, Enum):
    PLANNING = "planning"
    PLAN_CREATED = "plan_created"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_RETRY = "step_retry"
    REPLAN = "replan"
    EXECUTOR_TURN = "executor_turn"
    REVIEW = "review"
    MODEL_TURN = "model_turn"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    PROTOCOL_CORRECTION = "protocol_correction"
    PROTOCOL_ERROR = "protocol_error"
    PROVIDER_RETRY = "provider_retry"
    MODEL_ERROR = "model_error"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLATION = "cancellation"
    COMPLETION = "completion"


class ExitStatus(str, Enum):
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class TerminationReason(str, Enum):
    GOAL_COMPLETED = "goal_completed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    MODEL_PROTOCOL_ERROR = "model_protocol_error"
    MODEL_ERROR = "model_error"
    RUNTIME_ERROR = "runtime_error"


@dataclass(frozen=True)
class RuntimeRequest:
    task_id: str
    model_name: str
    max_steps: int = 12


@dataclass(frozen=True)
class RuntimeEvent:
    sequence: int
    kind: EventKind
    timestamp: str
    run_id: str
    correlation_id: str
    parent_id: str | None = None
    name: str | None = None
    content: Any = None
    arguments: dict[str, Any] | None = None
    result: Any = None
    error: Any = None
    usage: dict[str, int] | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeOutcome:
    status: ExitStatus
    task_id: str
    run_id: str
    events: tuple[RuntimeEvent, ...]
    final_response: Any | None
    world_state: dict[str, Any]
    score: dict[str, Any] | None
    usage: dict[str, int]
    terminal_error: str | None = None
    termination_reason: TerminationReason | None = None


class CancellationSignal:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


EventSink = Callable[[RuntimeEvent], Any]


class AgentRuntime(Protocol):
    async def run(
        self,
        request: RuntimeRequest,
        *,
        event_sink: EventSink | None = None,
        cancellation: CancellationSignal | None = None,
    ) -> RuntimeOutcome: ...
