from __future__ import annotations

from datetime import datetime, timezone
import inspect
from time import monotonic
from typing import Any
from uuid import uuid4

from mock_agent.adapter import AutomationBenchAdapter
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
from mock_agent.model import ModelClient, ModelRequest, ProviderFailure


BASELINE_PROMPT = """baseline/v1
Solve the supplied task directly. Use only the declared tools, inspect tool results before
continuing, and return a concise final response when the task is complete.
"""


class BaselineRuntime:
    """A minimal framework-free model/tool loop used as a comparison runtime."""

    def __init__(
        self,
        *,
        model_client: ModelClient,
        adapter: AutomationBenchAdapter | None = None,
    ) -> None:
        self._model = model_client
        self._adapter = adapter or AutomationBenchAdapter()

    async def run(
        self,
        request: RuntimeRequest,
        *,
        event_sink: EventSink | None = None,
        cancellation: CancellationSignal | None = None,
    ) -> RuntimeOutcome:
        cancellation = cancellation or CancellationSignal()
        session = self._adapter.open(request.task_id)
        task = session.agent_task
        run_id = request.run_id or str(uuid4())
        events: list[RuntimeEvent] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        final_response: Any = None
        transcript = tuple(
            {"role": item.role, "content": item.content} for item in task.prompt
        )

        async def emit(kind: EventKind, correlation_id: str, **values: Any) -> None:
            event = RuntimeEvent(
                sequence=len(events) + 1,
                kind=kind,
                timestamp=datetime.now(timezone.utc).isoformat(),
                run_id=run_id,
                correlation_id=correlation_id,
                **values,
            )
            events.append(event)
            if event_sink is not None:
                result = event_sink(event)
                if inspect.isawaitable(result):
                    await result

        async def finish(
            status: ExitStatus,
            termination_reason: TerminationReason,
            terminal_error: str | None = None,
        ) -> RuntimeOutcome:
            await emit(
                EventKind.COMPLETION,
                run_id,
                content={
                    "status": status.value,
                    "termination_reason": termination_reason.value,
                },
                error=terminal_error,
            )
            score, world = session.evaluate()
            return RuntimeOutcome(
                status=status,
                task_id=request.task_id,
                run_id=run_id,
                events=tuple(events),
                final_response=final_response,
                world_state=world,
                score=score,
                usage=usage,
                terminal_error=terminal_error,
                termination_reason=termination_reason,
            )

        try:
            for _ in range(request.max_steps):
                if cancellation.is_cancelled:
                    await emit(
                        EventKind.CANCELLATION,
                        run_id,
                        content={"boundary": "model_boundary"},
                    )
                    return await finish(
                        ExitStatus.STOPPED, TerminationReason.CANCELLED
                    )

                started = monotonic()
                reply = await self._model.respond(
                    ModelRequest(
                        role="baseline",
                        model_name=request.model_name,
                        instructions=BASELINE_PROMPT,
                        input=transcript,
                        tools=task.tools,
                    )
                )
                duration_ms = (monotonic() - started) * 1000
                for key in usage:
                    usage[key] += int(reply.usage.get(key, 0))
                turn_id = str(uuid4())
                await emit(
                    EventKind.MODEL_TURN,
                    turn_id,
                    content=reply.content,
                    usage=reply.usage or None,
                    duration_ms=duration_ms,
                    metadata=reply.metadata,
                )

                if not reply.tool_calls:
                    final_response = reply.content
                    return await finish(
                        ExitStatus.COMPLETED, TerminationReason.GOAL_COMPLETED
                    )

                for call in reply.tool_calls:
                    await emit(
                        EventKind.TOOL_CALL,
                        call.id,
                        parent_id=turn_id,
                        name=call.name,
                        arguments=call.arguments,
                    )
                if cancellation.is_cancelled:
                    await emit(
                        EventKind.CANCELLATION,
                        run_id,
                        content={"boundary": "tool_batch_boundary"},
                    )
                    return await finish(
                        ExitStatus.STOPPED, TerminationReason.CANCELLED
                    )

                tool_results = []
                for call in reply.tool_calls:
                    started = monotonic()
                    result = await task.dispatcher.dispatch(call.name, call.arguments)
                    result_duration_ms = (monotonic() - started) * 1000
                    tool_results.append(
                        {
                            "tool_call_id": call.id,
                            "name": call.name,
                            "result": result.value,
                            "error": result.error,
                        }
                    )
                    await emit(
                        EventKind.TOOL_ERROR
                        if result.error
                        else EventKind.TOOL_RESULT,
                        call.id,
                        name=call.name,
                        result=result.value,
                        error=result.error,
                        duration_ms=result_duration_ms,
                    )

                transcript += (
                    {
                        "role": "assistant",
                        "content": {
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "name": call.name,
                                    "arguments": call.arguments,
                                }
                                for call in reply.tool_calls
                            ]
                        },
                    },
                    {"role": "user", "content": {"tool_results": tool_results}},
                )

            await emit(
                EventKind.BUDGET_EXHAUSTED,
                run_id,
                content={"budget": "model_turns", "limit": request.max_steps},
            )
            return await finish(
                ExitStatus.STOPPED, TerminationReason.BUDGET_EXHAUSTED
            )
        except ProviderFailure as error:
            for retry in error.retries:
                await emit(
                    EventKind.PROVIDER_RETRY,
                    str(uuid4()),
                    parent_id=run_id,
                    content=retry,
                )
            terminal_error = f"{type(error.error).__name__}: {error.error}"
            await emit(
                EventKind.MODEL_ERROR,
                run_id,
                content={
                    "error_type": type(error.error).__name__,
                    "message": str(error.error),
                    "infrastructure_failure": error.transient,
                },
            )
            return await finish(
                ExitStatus.FAILED,
                TerminationReason.MODEL_ERROR,
                terminal_error,
            )
        except Exception as error:
            terminal_error = f"{type(error).__name__}: {error}"
            await emit(
                EventKind.MODEL_ERROR,
                run_id,
                content={
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "infrastructure_failure": False,
                },
            )
            return await finish(
                ExitStatus.FAILED,
                TerminationReason.MODEL_ERROR,
                terminal_error,
            )
