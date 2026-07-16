from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import inspect
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError, model_validator

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
from mock_agent.model import ModelClient, ModelReply, ModelRequest, ProviderFailure


PLANNER_PROMPT = """planner/v1
Create a linear plan of at most six steps. Each step needs a stable ID, one objective,
and explicit observable completion evidence. Use only the supplied task and tools.
"""
REPLAN_PROMPT = (
    PLANNER_PROMPT
    + """\
Treat completed steps as immutable and return only remaining work. Never repeat calls listed
as side_effects_must_not_repeat in the failed-step record.
"""
)
EXECUTOR_PROMPT = """executor/v1
Execute only the current step. Use declared tools for evidence or actions. You may call
multiple tools in one turn. When done, return exact evidence with source call IDs.
On retry, keep the local transcript intact, apply planner feedback, and do not repeat a
successful side effect merely because the step was rejected.
"""
REVIEWER_PROMPT = """reviewer/v1
Review the step outcome against its required evidence. Decide step_completed,
retry_step, replan, or goal_completed. Only goal_completed may return the final response.
"""


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
    def __init__(self, error: Exception):
        self.error_type = type(error).__name__
        self.message = str(error)
        super().__init__(f"{self.error_type}: {self.message}")


class RunCancelled(RuntimeError):
    def __init__(self, boundary: str):
        self.boundary = boundary
        super().__init__(f"Cancelled at {boundary}")


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
        logical_model_calls = 0

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
            nonlocal logical_model_calls
            if cancellation.is_cancelled:
                raise RunCancelled("model_boundary")
            if logical_model_calls == 24:
                raise BudgetExhausted("logical_model_calls", 24)
            logical_model_calls += 1
            started = monotonic()
            try:
                reply = await self._model.respond(model_request)
            except ProviderFailure as error:
                for retry in error.retries:
                    await emit(
                        EventKind.PROVIDER_RETRY,
                        str(uuid4()),
                        parent_id=run_id,
                        content=retry,
                    )
                raise ModelFailure(error.error) from error
            except Exception as error:
                raise ModelFailure(error) from error
            for retry in reply.metadata.get("provider_retries", []):
                await emit(
                    EventKind.PROVIDER_RETRY,
                    str(uuid4()),
                    parent_id=run_id,
                    content=retry,
                )
            for key in usage:
                usage[key] += int(reply.usage.get(key, 0))
            if cancellation.is_cancelled:
                raise RunCancelled("model_boundary")
            return reply, (monotonic() - started) * 1000

        async def ask_validated(
            model_request: ModelRequest,
            response_model: type[BaseModel],
            parent_id: str,
        ) -> tuple[BaseModel, ModelReply, float]:
            current_request = model_request
            for attempt in (1, 2):
                reply, duration = await ask(current_request)
                try:
                    return response_model.model_validate(reply.content), reply, duration
                except ValidationError as error:
                    errors = error.errors(include_url=False, include_input=False)
                    if attempt == 2:
                        raise ModelProtocolError(model_request.role, errors) from error
                    correction = {
                        "role": model_request.role,
                        "attempt": 2,
                        "invalid_output": reply.content,
                        "errors": errors,
                    }
                    correction_id = str(uuid4())
                    await emit(
                        EventKind.PROTOCOL_CORRECTION,
                        correction_id,
                        parent_id=parent_id,
                        content=correction,
                    )
                    current_request = replace(
                        current_request,
                        input=current_request.input
                        + (
                            {
                                "role": "user",
                                "content": {"protocol_correction": correction},
                            },
                        ),
                    )
            raise AssertionError("unreachable")

        prompt = tuple(
            {"role": item.role, "content": item.content} for item in task.prompt
        )
        try:
            await emit(EventKind.PLANNING, run_id)
            plan, reply, duration = await ask_validated(
                ModelRequest(
                    role="planner",
                    model_name=request.model_name,
                    instructions=PLANNER_PROMPT,
                    input=prompt,
                    response_model=Plan,
                ),
                Plan,
                run_id,
            )
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
            steps = list(plan.steps)
            step_index = 0
            replans = 0
            step_retries = 0

            while step_index < len(steps):
                step = steps[step_index]
                if cancellation.is_cancelled:
                    raise RunCancelled("model_boundary")
                await emit(
                    EventKind.STEP_STARTED,
                    step.id,
                    parent_id=plan_id,
                    content=step.model_dump(),
                )
                transcript: list[dict[str, Any]] = []
                retries = 0
                review_feedback = None
                previous_outcome = None
                replanned = False
                while True:
                    outcome = None
                    for _ in range(4):
                        executor_input = prompt + (
                            {
                                "role": "user",
                                "content": {
                                    "goal": plan.goal,
                                    "current_step": step.model_dump(),
                                    "accepted_evidence": list(accepted),
                                    "local_transcript": transcript,
                                    "previous_outcome": previous_outcome,
                                    "review_feedback": review_feedback,
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
                        if cancellation.is_cancelled:
                            raise RunCancelled("model_boundary")
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
                        if cancellation.is_cancelled:
                            raise RunCancelled("tool_batch_boundary")
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
                        if cancellation.is_cancelled:
                            raise RunCancelled("tool_batch_boundary")
                    if outcome is None:
                        raise BudgetExhausted("executor_turns_per_attempt", 4)

                    review, review_reply, duration = await ask_validated(
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
                                        "accepted_evidence": list(accepted),
                                    },
                                },
                            ),
                            response_model=Review,
                        ),
                        Review,
                        step.id,
                    )
                    review_id = str(uuid4())
                    await emit(
                        EventKind.REVIEW,
                        review_id,
                        parent_id=step.id,
                        content=review.model_dump(),
                        usage=review_reply.usage or None,
                        duration_ms=duration,
                    )
                    if cancellation.is_cancelled:
                        raise RunCancelled("model_boundary")
                    if review.decision == "goal_completed":
                        final_response = review.final_response
                        break
                    if review.decision == "retry_step":
                        if step_retries == 1:
                            raise BudgetExhausted("step_retries", 1)
                        step_retries += 1
                        retries += 1
                        previous_outcome = outcome.model_dump()
                        review_feedback = review.feedback
                        await emit(
                            EventKind.STEP_RETRY,
                            step.id,
                            parent_id=review_id,
                            content={
                                "attempt": retries + 1,
                                "feedback": review.feedback,
                            },
                        )
                        continue
                    if review.decision == "replan":
                        if replans == 1:
                            raise BudgetExhausted("replans", 1)
                        failed_step = {
                            "step": step.model_dump(),
                            "summary": outcome.summary,
                            "useful_facts": [
                                item.model_dump() for item in outcome.evidence
                            ],
                            "performed_actions": outcome.actions,
                            "side_effects_must_not_repeat": [
                                {
                                    "tool_call_id": item["tool_call_id"],
                                    "name": item["name"],
                                    "arguments": item["arguments"],
                                    "result": item["result"],
                                }
                                for item in transcript
                                if item["error"] is None
                            ],
                            "errors": outcome.errors,
                            "tool_errors": [
                                {
                                    "tool_call_id": item["tool_call_id"],
                                    "name": item["name"],
                                    "error": item["error"],
                                }
                                for item in transcript
                                if item["error"] is not None
                            ],
                            "invalidation_reason": review.feedback,
                        }
                        completed_steps = list(accepted)
                        replan_id = str(uuid4())
                        await emit(
                            EventKind.REPLAN,
                            replan_id,
                            parent_id=review_id,
                            content={
                                "completed_steps": completed_steps,
                                "failed_step": failed_step,
                            },
                        )
                        plan, replan_reply, duration = await ask_validated(
                            ModelRequest(
                                role="planner",
                                model_name=request.model_name,
                                instructions=REPLAN_PROMPT,
                                input=prompt
                                + (
                                    {
                                        "role": "user",
                                        "content": {
                                            "completed_steps": completed_steps,
                                            "failed_step": failed_step,
                                        },
                                    },
                                ),
                                response_model=Plan,
                            ),
                            Plan,
                            replan_id,
                        )
                        plan_id = str(uuid4())
                        await emit(
                            EventKind.PLAN_CREATED,
                            plan_id,
                            parent_id=replan_id,
                            content=plan.model_dump(),
                            usage=replan_reply.usage or None,
                            duration_ms=duration,
                        )
                        steps = list(plan.steps)
                        step_index = 0
                        replans += 1
                        replanned = True
                        break
                    if review.decision != "step_completed":
                        raise RuntimeError(
                            f"Unsupported review decision: {review.decision}"
                        )
                    accepted.append(
                        {
                            "step_id": step.id,
                            "summary": outcome.summary,
                            "evidence": [
                                item.model_dump() for item in outcome.evidence
                            ],
                            "actions": outcome.actions,
                            "errors": outcome.errors,
                        }
                    )
                    break

                if final_response is not None:
                    break
                if replanned:
                    continue
                step_index += 1

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
                termination_reason=TerminationReason.GOAL_COMPLETED,
            )
        except RunCancelled as error:
            await emit(
                EventKind.CANCELLATION,
                run_id,
                content={"boundary": error.boundary},
            )
            return await self._finish(
                session,
                request,
                run_id,
                events,
                usage,
                final_response,
                ExitStatus.STOPPED,
                emit,
                termination_reason=TerminationReason.CANCELLED,
            )
        except ModelProtocolError as error:
            await emit(
                EventKind.PROTOCOL_ERROR,
                run_id,
                content={"role": error.role, "errors": error.errors},
            )
            return await self._finish(
                session,
                request,
                run_id,
                events,
                usage,
                final_response,
                ExitStatus.FAILED,
                emit,
                terminal_error=str(error),
                termination_reason=TerminationReason.MODEL_PROTOCOL_ERROR,
            )
        except ModelFailure as error:
            await emit(
                EventKind.MODEL_ERROR,
                run_id,
                content={
                    "error_type": error.error_type,
                    "message": error.message,
                },
            )
            return await self._finish(
                session,
                request,
                run_id,
                events,
                usage,
                final_response,
                ExitStatus.FAILED,
                emit,
                terminal_error=str(error),
                termination_reason=TerminationReason.MODEL_ERROR,
            )
        except BudgetExhausted as error:
            await emit(
                EventKind.BUDGET_EXHAUSTED,
                run_id,
                content={"budget": error.budget, "limit": error.limit},
            )
            return await self._finish(
                session,
                request,
                run_id,
                events,
                usage,
                final_response,
                ExitStatus.STOPPED,
                emit,
                termination_reason=TerminationReason.BUDGET_EXHAUSTED,
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
                TerminationReason.RUNTIME_ERROR,
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
        termination_reason=None,
    ):
        content = {"status": status.value}
        if termination_reason is not None:
            content["termination_reason"] = termination_reason.value
        await emit(
            EventKind.COMPLETION,
            run_id,
            content=content,
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
