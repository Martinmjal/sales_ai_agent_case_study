from __future__ import annotations

import inspect
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable, Literal
from uuid import uuid4

from sales_agent.contract import (
    CancellationSignal,
    EventKind,
    EventSink,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    RuntimeRequest,
    TerminationReason,
)
from sales_agent.model import ModelClient, ModelReply, ModelRequest, ProviderFailure


class BudgetExhausted(RuntimeError):
    def __init__(self, budget: str, limit: int | float):
        self.budget = budget
        self.limit = limit
        super().__init__(f"{budget} budget exhausted at {limit}")


class RunBudget:
    """The single owner of every bounded resource in one runtime execution."""

    def __init__(
        self,
        *,
        max_model_turns: int = 30,
        max_tool_calls: int = 64,
        max_plan_revisions: int = 3,
        deadline_seconds: float = 300,
        max_consecutive_no_progress_turns: int = 3,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if (
            min(
                max_model_turns,
                max_tool_calls,
                max_plan_revisions,
                max_consecutive_no_progress_turns,
            )
            < 1
        ):
            raise ValueError("Run budget limits must be positive")
        if deadline_seconds <= 0:
            raise ValueError("Run deadline must be positive")
        self.max_model_turns = max_model_turns
        self.max_tool_calls = max_tool_calls
        self.max_plan_revisions = max_plan_revisions
        self.deadline_seconds = deadline_seconds
        self.max_consecutive_no_progress_turns = max_consecutive_no_progress_turns
        self._clock = clock
        self._started_at = clock()
        self.model_turns = 0
        self.tool_calls = 0
        self.plan_revisions = 0
        self.consecutive_no_progress_turns = 0
        self.finalization_calls = 0

    def fresh(self) -> RunBudget:
        return RunBudget(
            max_model_turns=self.max_model_turns,
            max_tool_calls=self.max_tool_calls,
            max_plan_revisions=self.max_plan_revisions,
            deadline_seconds=self.deadline_seconds,
            max_consecutive_no_progress_turns=(self.max_consecutive_no_progress_turns),
            clock=self._clock,
        )

    def snapshot(self) -> dict[str, int | float]:
        return {
            "max_model_turns": self.max_model_turns,
            "max_tool_calls": self.max_tool_calls,
            "max_plan_revisions": self.max_plan_revisions,
            "deadline_seconds": self.deadline_seconds,
            "max_consecutive_no_progress_turns": (self.max_consecutive_no_progress_turns),
            "reserved_finalization_calls": 1,
        }

    def check_deadline(self) -> None:
        if self._clock() - self._started_at >= self.deadline_seconds:
            raise BudgetExhausted("deadline", self.deadline_seconds)

    def claim_model_turn(self) -> None:
        self.check_deadline()
        if self.model_turns >= self.max_model_turns:
            raise BudgetExhausted("model_turns", self.max_model_turns)
        self.model_turns += 1

    def claim_tool_calls(self, count: int) -> None:
        self.check_deadline()
        if count < 0:
            raise ValueError("Tool-call count cannot be negative")
        if self.tool_calls + count > self.max_tool_calls:
            raise BudgetExhausted("tool_calls", self.max_tool_calls)
        self.tool_calls += count

    def claim_plan_revision(self) -> None:
        self.check_deadline()
        if self.plan_revisions >= self.max_plan_revisions:
            raise BudgetExhausted("plan_revisions", self.max_plan_revisions)
        self.plan_revisions += 1

    def claim_finalization(self) -> None:
        if self.finalization_calls >= 1:
            raise BudgetExhausted("finalization_calls", 1)
        self.finalization_calls += 1

    def record_turn(self, *, progress: bool) -> Literal["continue", "warn", "finalize"]:
        if progress:
            self.consecutive_no_progress_turns = 0
            return "continue"
        self.consecutive_no_progress_turns += 1
        if self.consecutive_no_progress_turns == self.max_consecutive_no_progress_turns:
            return "warn"
        if self.consecutive_no_progress_turns > self.max_consecutive_no_progress_turns:
            return "finalize"
        return "continue"


class ModelProtocolError(RuntimeError):
    def __init__(self, role: str, errors: list[dict[str, Any]]):
        self.role = role
        self.errors = errors
        super().__init__(f"{role} returned invalid structured output twice")


class ModelFailure(RuntimeError):
    def __init__(self, error: Exception, *, infrastructure_failure: bool = False):
        self.error_type = type(error).__name__
        self.message = str(error)
        self.infrastructure_failure = infrastructure_failure
        super().__init__(f"{self.error_type}: {self.message}")


class AdapterInitializationError(RuntimeError):
    def __init__(self, error: Exception):
        self.error_type = type(error).__name__
        self.message = str(error)
        super().__init__(f"{self.error_type}: {self.message}")


class EventPersistenceError(RuntimeError):
    def __init__(self, event: RuntimeEvent, error: Exception):
        self.event_kind = event.kind.value
        self.event_sequence = event.sequence
        self.error_type = type(error).__name__
        self.message = str(error)
        super().__init__(f"{self.error_type}: {self.message}")


class RunCancelled(RuntimeError):
    def __init__(self, boundary: str):
        self.boundary = boundary
        super().__init__(f"Cancelled at {boundary}")


class RuntimeRun:
    """Generic model/event/outcome bookkeeping for an evaluator runtime run."""

    def __init__(
        self,
        *,
        session: Any,
        request: RuntimeRequest,
        model: ModelClient,
        budget: RunBudget,
        event_sink: EventSink | None,
        cancellation: CancellationSignal,
    ) -> None:
        self.session = session
        self.request = request
        self.model = model
        self.budget = budget
        self.event_sink = event_sink
        self.cancellation = cancellation
        self.run_id = str(uuid4())
        self.events: list[RuntimeEvent] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def emit(self, kind: EventKind, correlation_id: str, **values: Any) -> None:
        event = RuntimeEvent(
            sequence=len(self.events) + 1,
            kind=kind,
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=self.run_id,
            correlation_id=correlation_id,
            **values,
        )
        self.events.append(event)
        if self.event_sink is not None:
            try:
                result = self.event_sink(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                self.event_sink = None
                raise EventPersistenceError(event, error) from error

    async def ask(
        self, model_request: ModelRequest, *, finalization: bool = False
    ) -> tuple[ModelReply, float]:
        if self.cancellation.is_cancelled:
            raise RunCancelled("model_boundary")
        if finalization:
            self.budget.claim_finalization()
        else:
            self.budget.claim_model_turn()
        started = monotonic()
        try:
            reply = await self.model.respond(model_request)
        except ProviderFailure as error:
            for retry in error.retries:
                await self.emit(
                    EventKind.PROVIDER_RETRY,
                    str(uuid4()),
                    parent_id=self.run_id,
                    content=retry,
                )
            raise ModelFailure(error.error, infrastructure_failure=error.transient) from error
        except Exception as error:
            raise ModelFailure(error) from error
        for retry in reply.metadata.get("provider_retries", []):
            await self.emit(
                EventKind.PROVIDER_RETRY,
                str(uuid4()),
                parent_id=self.run_id,
                content=retry,
            )
        for key in self.usage:
            self.usage[key] += int(reply.usage.get(key, 0))
        if self.cancellation.is_cancelled:
            raise RunCancelled("model_boundary")
        if not finalization:
            self.budget.check_deadline()
        return reply, (monotonic() - started) * 1000

    async def fail(self, error: Exception, final_response: Any | None = None) -> RuntimeOutcome:
        try:
            return await self._fail_once(error, final_response)
        except EventPersistenceError as persistence_error:
            return await self._fail_once(persistence_error, final_response)

    async def _fail_once(
        self, error: Exception, final_response: Any | None = None
    ) -> RuntimeOutcome:
        terminal_error = None
        if isinstance(error, RunCancelled):
            status = ExitStatus.STOPPED
            reason = TerminationReason.CANCELLED
            await self.emit(
                EventKind.CANCELLATION,
                self.run_id,
                content={"boundary": error.boundary},
            )
        elif isinstance(error, ModelProtocolError):
            status = ExitStatus.FAILED
            reason = TerminationReason.MODEL_PROTOCOL_ERROR
            terminal_error = str(error)
            await self.emit(
                EventKind.PROTOCOL_ERROR,
                self.run_id,
                content={"role": error.role, "errors": error.errors},
            )
        elif isinstance(error, ModelFailure):
            status = ExitStatus.FAILED
            reason = TerminationReason.MODEL_ERROR
            terminal_error = str(error)
            await self.emit(
                EventKind.MODEL_ERROR,
                self.run_id,
                content={
                    "error_type": error.error_type,
                    "message": error.message,
                    "infrastructure_failure": error.infrastructure_failure,
                },
            )
        elif isinstance(error, AdapterInitializationError):
            status = ExitStatus.FAILED
            reason = TerminationReason.ADAPTER_INITIALIZATION_FAILED
            terminal_error = str(error)
            await self.emit(
                EventKind.ADAPTER_ERROR,
                self.run_id,
                content={
                    "error_type": error.error_type,
                    "message": error.message,
                },
            )
        elif isinstance(error, EventPersistenceError):
            status = ExitStatus.FAILED
            reason = TerminationReason.EVENT_PERSISTENCE_FAILED
            terminal_error = str(error)
            await self.emit(
                EventKind.EVENT_PERSISTENCE_ERROR,
                self.run_id,
                content={
                    "failed_event_kind": error.event_kind,
                    "failed_event_sequence": error.event_sequence,
                    "error_type": error.error_type,
                    "message": error.message,
                },
            )
        elif isinstance(error, BudgetExhausted):
            status = ExitStatus.STOPPED
            reason = TerminationReason.BUDGET_EXHAUSTED
            await self.emit(
                EventKind.BUDGET_EXHAUSTED,
                self.run_id,
                content={"budget": error.budget, "limit": error.limit},
            )
        else:
            status = ExitStatus.FAILED
            reason = TerminationReason.RUNTIME_ERROR
            terminal_error = f"{type(error).__name__}: {error}"
        return await self.finish(
            final_response,
            status=status,
            termination_reason=reason,
            terminal_error=terminal_error,
        )

    async def finish(
        self,
        final_response: Any | None,
        *,
        status: ExitStatus = ExitStatus.COMPLETED,
        termination_reason: TerminationReason = TerminationReason.GOAL_COMPLETED,
        terminal_error: str | None = None,
    ) -> RuntimeOutcome:
        score = None
        world = {}
        evaluation_error = None
        if self.session is not None:
            try:
                score, world = self.session.evaluate()
            except Exception as error:
                evaluation_error = f"{type(error).__name__}: {error}"
                try:
                    world = self.session.world_state()
                except Exception:
                    world = {}
                await self.emit(
                    EventKind.EVALUATION_ERROR,
                    self.run_id,
                    content={
                        "error_type": type(error).__name__,
                        "message": str(error),
                        "evaluation_available": False,
                    },
                )
        await self.emit(
            EventKind.COMPLETION,
            self.run_id,
            content={
                "status": status.value,
                "termination_reason": termination_reason.value,
                "evaluation_available": evaluation_error is None,
            },
            error=terminal_error,
        )
        return RuntimeOutcome(
            status=status,
            task_id=self.request.task_id,
            run_id=self.run_id,
            events=tuple(self.events),
            final_response=final_response,
            world_state=world,
            score=score,
            usage=self.usage,
            terminal_error=terminal_error,
            termination_reason=termination_reason,
            evaluation_error=evaluation_error,
        )
