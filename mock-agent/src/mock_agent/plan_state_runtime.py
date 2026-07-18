from __future__ import annotations

from dataclasses import replace
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from mock_agent.adapter import AutomationBenchAdapter, ToolSpec
from mock_agent.contract import (
    CancellationSignal,
    EventKind,
    EventSink,
    RuntimeOutcome,
    RuntimeRequest,
)
from mock_agent.model import ModelClient, ModelReply, ModelRequest
from mock_agent.plan_state import (
    CompleteStep,
    Finish,
    PlanDraft,
    PlanState,
    PlanStateError,
    SuccessfulToolCall,
    activate_next_step,
    complete_step,
    create_plan_state,
    finish,
    record_successful_tool_call,
)
from mock_agent.runtime_support import ModelProtocolError, RunCancelled, RuntimeRun


PLAN_STATE_LIMITS = {"plan_steps": 6, "logical_model_calls": 30, "provider_retries": 2}
PLANNER_PROMPT = """plan-state-planner/v1
Create the smallest cohesive linear plan, with at most six steps. Give the goal, every step,
and every evidence requirement a globally unique stable ID. Each step needs a nonempty objective
and explicit observable evidence. Every evidence requirement must name supplied source tools that
can produce it. Business tools are unavailable during planning; use only the supplied schemas.
"""
EXECUTOR_PROMPT = """plan-state-executor/v1
Execute the active plan through one continuous loop. Every turn must contain either a batch of
business-tool calls or exactly one harness control action. Never mix the two. Business calls run
sequentially and their observations arrive on the next turn. Call complete_step only after every
evidence source result has been observed. Use the exact current plan revision and map every active
requirement ID to a factual claim and compatible successful source call ID. Call finish with a
nonempty final response only after all plan steps are completed.
"""
CONTROL_NAMES = frozenset({"complete_step", "finish"})
CONTROL_TOOLS = (
    ToolSpec(
        name="complete_step",
        description="Complete the active plan step with grounded evidence.",
        input_schema=CompleteStep.model_json_schema(),
    ),
    ToolSpec(
        name="finish",
        description="Finish a fully completed plan and provide the final response.",
        input_schema=Finish.model_json_schema(),
    ),
)


def _plan_event_content(state: PlanState) -> dict[str, Any]:
    return {
        "revision": state.revision,
        "goal": state.goal.objective,
        "goal_id": state.goal.id,
        "steps": [step.model_dump(mode="json") for step in state.steps],
    }


def _turn_content(reply: ModelReply) -> dict[str, Any]:
    return {
        "content": reply.content,
        "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in reply.tool_calls
        ],
    }


class PlanStateRuntime:
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
        run = RuntimeRun(
            session=session,
            request=request,
            model=self._model,
            logical_model_call_limit=PLAN_STATE_LIMITS["logical_model_calls"],
            event_sink=event_sink,
            cancellation=cancellation,
        )
        run_id = run.run_id
        emit = run.emit
        ask = run.ask
        final_response = None

        prompt = tuple(
            {"role": item.role, "content": item.content} for item in task.prompt
        )
        declared_tool_names = {tool.name for tool in task.tools}
        planning_context = {
            "available_tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in task.tools
            ]
        }

        async def create_initial_plan() -> tuple[PlanState, ModelReply, float]:
            model_request = ModelRequest(
                role="planner",
                model_name=request.model_name,
                instructions=PLANNER_PROMPT,
                input=prompt + ({"role": "user", "content": planning_context},),
                response_model=PlanDraft,
            )
            current_request = model_request
            errors: list[dict[str, Any]] = []
            for attempt in (1, 2):
                reply, duration = await ask(current_request)
                try:
                    draft = PlanDraft.model_validate(reply.content)
                    state = create_plan_state(draft, declared_tools=declared_tool_names)
                except ValidationError as error:
                    errors = error.errors(include_url=False, include_input=False)
                except PlanStateError as error:
                    errors = [error.observation()]
                else:
                    return state, reply, duration
                if attempt == 2:
                    raise ModelProtocolError("planner", errors)
                correction = {
                    "role": "planner",
                    "attempt": 2,
                    "invalid_output": reply.content,
                    "errors": errors,
                }
                await emit(
                    EventKind.PROTOCOL_CORRECTION,
                    str(uuid4()),
                    parent_id=run_id,
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

        async def correction(
            *,
            turn_id: str,
            action: str | None,
            code: str,
            message: str,
            details: dict[str, Any] | None = None,
            call_id: str | None = None,
        ) -> dict[str, Any]:
            error: dict[str, Any] = {"code": code, "message": message}
            if details:
                error["details"] = details
            observation = {"ok": False, "action": action, "error": error}
            if call_id is not None:
                await emit(
                    EventKind.TOOL_ERROR,
                    call_id,
                    parent_id=turn_id,
                    name=action,
                    error=error,
                )
            await emit(
                EventKind.PROTOCOL_CORRECTION,
                str(uuid4()),
                parent_id=turn_id,
                content=observation,
            )
            return observation

        try:
            await emit(
                EventKind.PLANNING,
                run_id,
                content={"execution_limits": dict(PLAN_STATE_LIMITS)},
            )
            state, planning_reply, planning_duration = await create_initial_plan()
            plan_id = str(uuid4())
            await emit(
                EventKind.PLAN_CREATED,
                plan_id,
                parent_id=run_id,
                content=_plan_event_content(state),
                usage=planning_reply.usage or None,
                duration_ms=planning_duration,
            )
            state = activate_next_step(state)
            active = next(
                step for step in state.steps if step.id == state.active_step_id
            )
            await emit(
                EventKind.STEP_STARTED,
                active.id,
                parent_id=plan_id,
                content={
                    **active.model_dump(mode="json"),
                    "plan_revision": state.revision,
                },
            )

            tool_observations: list[dict[str, Any]] = []
            control_observations: list[dict[str, Any]] = []
            seen_call_ids: set[str] = set()
            execution_tools = task.tools + CONTROL_TOOLS

            while final_response is None:
                execution_context = {
                    "plan_state": state.model_dump(mode="json"),
                    "tool_observations": list(tool_observations),
                    "control_observations": list(control_observations),
                }
                reply, duration = await ask(
                    ModelRequest(
                        role="plan_state_executor",
                        model_name=request.model_name,
                        instructions=EXECUTOR_PROMPT,
                        input=prompt
                        + ({"role": "user", "content": execution_context},),
                        tools=execution_tools,
                    )
                )
                turn_id = str(uuid4())
                await emit(
                    EventKind.MODEL_TURN,
                    turn_id,
                    parent_id=state.active_step_id or plan_id,
                    content=_turn_content(reply),
                    usage=reply.usage or None,
                    duration_ms=duration,
                    metadata=reply.metadata,
                )
                calls = reply.tool_calls
                control_calls = [call for call in calls if call.name in CONTROL_NAMES]
                business_calls = [
                    call for call in calls if call.name not in CONTROL_NAMES
                ]

                if not calls:
                    control_observations.append(
                        await correction(
                            turn_id=turn_id,
                            action=None,
                            code="missing_action",
                            message="A turn must contain business calls or one control action.",
                        )
                    )
                    continue
                if control_calls and business_calls:
                    control_observations.append(
                        await correction(
                            turn_id=turn_id,
                            action=None,
                            code="mixed_business_control_batch",
                            message="Business and control calls cannot share a turn.",
                            details={
                                "business_call_ids": [
                                    call.id for call in business_calls
                                ],
                                "control_call_ids": [call.id for call in control_calls],
                            },
                        )
                    )
                    continue
                if len(control_calls) > 1:
                    control_observations.append(
                        await correction(
                            turn_id=turn_id,
                            action=None,
                            code="multiple_control_actions",
                            message="A turn may contain only one control action.",
                        )
                    )
                    continue

                if business_calls:
                    if state.active_step_id is None:
                        control_observations.append(
                            await correction(
                                turn_id=turn_id,
                                action=None,
                                code="no_active_step",
                                message="Business calls require an active plan step.",
                            )
                        )
                        continue
                    identifiers = [call.id for call in business_calls]
                    duplicates = sorted(
                        {
                            call_id
                            for call_id in identifiers
                            if identifiers.count(call_id) > 1
                            or call_id in seen_call_ids
                        }
                    )
                    if duplicates:
                        control_observations.append(
                            await correction(
                                turn_id=turn_id,
                                action=None,
                                code="duplicate_tool_call_id",
                                message="Business tool call IDs must be globally unique.",
                                details={"call_ids": duplicates},
                            )
                        )
                        continue
                    seen_call_ids.update(identifiers)
                    for call in business_calls:
                        await emit(
                            EventKind.TOOL_CALL,
                            call.id,
                            parent_id=turn_id,
                            name=call.name,
                            arguments=call.arguments,
                        )
                    if cancellation.is_cancelled:
                        raise RunCancelled("tool_batch_boundary")
                    active_step_id = state.active_step_id
                    for call in business_calls:
                        started = monotonic()
                        result = await task.dispatcher.dispatch(
                            call.name, call.arguments
                        )
                        tool_duration = (monotonic() - started) * 1000
                        observation = {
                            "call_id": call.id,
                            "step_id": active_step_id,
                            "name": call.name,
                            "arguments": call.arguments,
                            "result": result.value,
                            "error": result.error,
                            "succeeded": result.error is None,
                        }
                        tool_observations.append(observation)
                        if result.error is None:
                            state = record_successful_tool_call(
                                state,
                                SuccessfulToolCall(
                                    call_id=call.id,
                                    step_id=active_step_id,
                                    tool_name=call.name,
                                ),
                            )
                        await emit(
                            EventKind.TOOL_ERROR
                            if result.error is not None
                            else EventKind.TOOL_RESULT,
                            call.id,
                            parent_id=turn_id,
                            name=call.name,
                            result=result.value,
                            error=result.error,
                            duration_ms=tool_duration,
                        )
                    if cancellation.is_cancelled:
                        raise RunCancelled("tool_batch_boundary")
                    continue

                call = control_calls[0]
                await emit(
                    EventKind.TOOL_CALL,
                    call.id,
                    parent_id=turn_id,
                    name=call.name,
                    arguments=call.arguments,
                )
                try:
                    if call.name == "complete_step":
                        action = CompleteStep.model_validate(call.arguments)
                        state = complete_step(state, action)
                        result = {"ok": True, "plan_revision": state.revision}
                        await emit(
                            EventKind.TOOL_RESULT,
                            call.id,
                            parent_id=turn_id,
                            name=call.name,
                            result=result,
                        )
                        control_observations.append(
                            {"ok": True, "action": call.name, "result": result}
                        )
                        await emit(
                            EventKind.STEP_COMPLETED,
                            action.step_id,
                            parent_id=plan_id,
                            content={
                                **action.model_dump(mode="json"),
                                "plan_revision": state.revision,
                            },
                        )
                        if any(step.state == "pending" for step in state.steps):
                            state = activate_next_step(state)
                            active = next(
                                step
                                for step in state.steps
                                if step.id == state.active_step_id
                            )
                            await emit(
                                EventKind.STEP_STARTED,
                                active.id,
                                parent_id=plan_id,
                                content={
                                    **active.model_dump(mode="json"),
                                    "plan_revision": state.revision,
                                },
                            )
                    else:
                        action = Finish.model_validate(call.arguments)
                        final_response = finish(state, action)
                        result = {"ok": True, "outcome": action.outcome}
                        await emit(
                            EventKind.TOOL_RESULT,
                            call.id,
                            parent_id=turn_id,
                            name=call.name,
                            result=result,
                        )
                        control_observations.append(
                            {"ok": True, "action": call.name, "result": result}
                        )
                except ValidationError as error:
                    control_observations.append(
                        await correction(
                            turn_id=turn_id,
                            action=call.name,
                            call_id=call.id,
                            code="invalid_control_action",
                            message="Control action arguments failed validation.",
                            details={
                                "errors": error.errors(
                                    include_url=False, include_input=False
                                )
                            },
                        )
                    )
                except PlanStateError as error:
                    control_observations.append(
                        await correction(
                            turn_id=turn_id,
                            action=call.name,
                            call_id=call.id,
                            code=error.code,
                            message=error.message,
                            details=error.details,
                        )
                    )

            return await run.finish(final_response)
        except Exception as error:
            return await run.fail(error, final_response)
