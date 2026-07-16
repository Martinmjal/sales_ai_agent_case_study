from __future__ import annotations

from datetime import datetime, timezone
import inspect
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from mock_agent.adapter import AutomationBenchAdapter
from mock_agent.contract import (
    CancellationSignal,
    EventKind,
    EventSink,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    RuntimeRequest,
)
from mock_agent.model import ModelClient, ModelReply, ModelRequest


PLANNER_PROMPT = """planner/v1
Create a linear plan of at most six steps. Each step needs a stable ID, one objective,
and explicit observable completion evidence. Use only the supplied task and tools.
"""
EXECUTOR_PROMPT = """executor/v1
Execute only the current step. Use declared tools for evidence or actions. You may call
multiple tools in one turn. When done, return exact evidence with source call IDs.
"""
REVIEWER_PROMPT = """reviewer/v1
Review the step outcome against its required evidence. Decide step_completed,
retry_step, replan, or goal_completed. Only goal_completed may return the final response.
"""


class PlanStep(BaseModel):
    id: str
    objective: str
    required_evidence: list[str] = Field(min_length=1)


class Plan(BaseModel):
    goal: str
    steps: list[PlanStep] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def unique_step_ids(self):
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Plan step IDs must be unique")
        return self


class Evidence(BaseModel):
    fact: str
    source_call_id: str


class StepOutcome(BaseModel):
    summary: str
    evidence: list[Evidence]
    actions: list[str]
    errors: list[str]


class Review(BaseModel):
    decision: Literal["step_completed", "retry_step", "replan", "goal_completed"]
    feedback: str | None = None
    final_response: str | None = None

    @model_validator(mode="after")
    def completed_goal_has_response(self):
        if self.decision == "goal_completed" and not self.final_response:
            raise ValueError("goal_completed requires final_response")
        return self


class PlannerExecutorRuntime:
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
        run_id = str(uuid4())
        events: list[RuntimeEvent] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        final_response = None

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

        async def ask(model_request: ModelRequest) -> tuple[ModelReply, float]:
            started = monotonic()
            reply = await self._model.respond(model_request)
            for key in usage:
                usage[key] += int(reply.usage.get(key, 0))
            return reply, (monotonic() - started) * 1000

        prompt = tuple(
            {"role": item.role, "content": item.content} for item in task.prompt
        )
        try:
            await emit(EventKind.PLANNING, run_id)
            reply, duration = await ask(
                ModelRequest(
                    role="planner",
                    model_name=request.model_name,
                    instructions=PLANNER_PROMPT,
                    input=prompt,
                    response_model=Plan,
                )
            )
            plan = Plan.model_validate(reply.content)
            plan_id = str(uuid4())
            await emit(
                EventKind.PLAN_CREATED,
                plan_id,
                parent_id=run_id,
                content=plan.model_dump(),
                usage=reply.usage or None,
                duration_ms=duration,
            )
            accepted: list[dict[str, Any]] = []

            for step in plan.steps:
                if cancellation.is_cancelled:
                    return await self._finish(
                        session,
                        request,
                        run_id,
                        events,
                        usage,
                        final_response,
                        ExitStatus.STOPPED,
                        emit,
                    )
                await emit(
                    EventKind.STEP_STARTED,
                    step.id,
                    parent_id=plan_id,
                    content=step.model_dump(),
                )
                transcript: list[dict[str, Any]] = []
                outcome = None
                for _ in range(4):
                    executor_input = prompt + (
                        {
                            "role": "user",
                            "content": {
                                "goal": plan.goal,
                                "current_step": step.model_dump(),
                                "accepted_evidence": accepted,
                                "local_transcript": transcript,
                            },
                        },
                    )
                    turn, duration = await ask(
                        ModelRequest(
                            role="executor",
                            model_name=request.model_name,
                            instructions=EXECUTOR_PROMPT,
                            input=executor_input,
                            tools=task.tools,
                            response_model=StepOutcome,
                        )
                    )
                    turn_id = str(uuid4())
                    await emit(
                        EventKind.EXECUTOR_TURN,
                        turn_id,
                        parent_id=step.id,
                        content=turn.content,
                        usage=turn.usage or None,
                        duration_ms=duration,
                        metadata=turn.metadata,
                    )
                    if not turn.tool_calls:
                        outcome = StepOutcome.model_validate(turn.content)
                        break
                    for call in turn.tool_calls:
                        await emit(
                            EventKind.TOOL_CALL,
                            call.id,
                            parent_id=turn_id,
                            name=call.name,
                            arguments=call.arguments,
                        )
                    for call in turn.tool_calls:
                        started = monotonic()
                        result = await task.dispatcher.dispatch(
                            call.name, call.arguments
                        )
                        duration = (monotonic() - started) * 1000
                        transcript.append(
                            {
                                "tool_call_id": call.id,
                                "name": call.name,
                                "arguments": call.arguments,
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
                            duration_ms=duration,
                        )
                if outcome is None:
                    raise RuntimeError(
                        f"Executor turn limit reached for step {step.id}"
                    )

                review_reply, duration = await ask(
                    ModelRequest(
                        role="reviewer",
                        model_name=request.model_name,
                        instructions=REVIEWER_PROMPT,
                        input=prompt
                        + (
                            {
                                "role": "user",
                                "content": {
                                    "goal": plan.goal,
                                    "step": step.model_dump(),
                                    "outcome": outcome.model_dump(),
                                    "accepted_evidence": accepted,
                                },
                            },
                        ),
                        response_model=Review,
                    )
                )
                review = Review.model_validate(review_reply.content)
                review_id = str(uuid4())
                await emit(
                    EventKind.REVIEW,
                    review_id,
                    parent_id=step.id,
                    content=review.model_dump(),
                    usage=review_reply.usage or None,
                    duration_ms=duration,
                )
                if review.decision == "goal_completed":
                    final_response = review.final_response
                    break
                if review.decision != "step_completed":
                    raise RuntimeError(
                        f"Unsupported review decision in first slice: {review.decision}"
                    )
                accepted.append(
                    {
                        "step_id": step.id,
                        "summary": outcome.summary,
                        "evidence": [item.model_dump() for item in outcome.evidence],
                        "actions": outcome.actions,
                    }
                )

            if final_response is None:
                raise RuntimeError("Planner did not declare goal_completed")
            return await self._finish(
                session,
                request,
                run_id,
                events,
                usage,
                final_response,
                ExitStatus.COMPLETED,
                emit,
            )
        except Exception as error:
            return await self._finish(
                session,
                request,
                run_id,
                events,
                usage,
                final_response,
                ExitStatus.FAILED,
                emit,
                f"{type(error).__name__}: {error}",
            )

    @staticmethod
    async def _finish(
        session,
        request,
        run_id,
        events,
        usage,
        final_response,
        status,
        emit,
        terminal_error=None,
    ):
        await emit(
            EventKind.COMPLETION,
            run_id,
            content={"status": status.value},
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
        )
