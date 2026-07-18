from __future__ import annotations

from datetime import datetime, timezone
import inspect
from time import monotonic
from typing import Any
from uuid import uuid4

from mock_agent.contract import (
    CancellationSignal,
    EventKind,
    EventSink,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    RuntimeRequest,
    TerminationReason,
)
from mock_agent.model import ModelClient, ModelReply, ModelRequest, ProviderFailure


class BudgetExhausted(RuntimeError):
    def __init__(self, budget: str, limit: int):
        self.budget = budget
        self.limit = limit
        super().__init__(f"{budget} budget exhausted at {limit}")


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
        logical_model_call_limit: int,
        event_sink: EventSink | None,
        cancellation: CancellationSignal,
    ) -> None:
        self.session = session
        self.request = request
        self.model = model
        self.logical_model_call_limit = logical_model_call_limit
        self.event_sink = event_sink
        self.cancellation = cancellation
        self.run_id = str(uuid4())
        self.events: list[RuntimeEvent] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self.logical_model_calls = 0

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
            result = self.event_sink(event)
            if inspect.isawaitable(result):
                await result

    async def ask(self, model_request: ModelRequest) -> tuple[ModelReply, float]:
        if self.cancellation.is_cancelled:
            raise RunCancelled("model_boundary")
        if self.logical_model_calls >= self.logical_model_call_limit:
            raise BudgetExhausted("logical_model_calls", self.logical_model_call_limit)
        self.logical_model_calls += 1
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
            raise ModelFailure(
                error.error, infrastructure_failure=error.transient
            ) from error
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
        return reply, (monotonic() - started) * 1000

    async def fail(
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
        await self.emit(
            EventKind.COMPLETION,
            self.run_id,
            content={
                "status": status.value,
                "termination_reason": termination_reason.value,
            },
            error=terminal_error,
        )
        score, world = self.session.evaluate()
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
        )
