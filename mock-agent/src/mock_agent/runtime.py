from __future__ import annotations

import copy
from datetime import datetime, timezone
import inspect
import os
from time import monotonic
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage, convert_to_messages
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from automationbench.schema.world import WorldState

from mock_agent.catalog import TaskCatalog, TaskDefinition
from mock_agent.contract import (
    CancellationSignal,
    EventKind,
    EventSink,
    ExitStatus,
    RuntimeEvent,
    RuntimeOutcome,
    RuntimeRequest,
)
from mock_agent.main import build_graph, make_task_tools, score_world


class MockAgentRuntime:
    def __init__(
        self,
        *,
        catalog: TaskCatalog | None = None,
        agent_model: Runnable[Any, BaseMessage] | None = None,
    ) -> None:
        self._catalog = catalog or TaskCatalog.from_sales_dataset()
        self._agent_model = agent_model

    async def run(
        self,
        request: RuntimeRequest,
        *,
        event_sink: EventSink | None = None,
        cancellation: CancellationSignal | None = None,
    ) -> RuntimeOutcome:
        task = self._catalog.get_task(request.task_id)
        return await self.run_task(
            task,
            request,
            event_sink=event_sink,
            cancellation=cancellation,
        )

    async def run_task(
        self,
        task: TaskDefinition,
        request: RuntimeRequest,
        *,
        event_sink: EventSink | None = None,
        cancellation: CancellationSignal | None = None,
    ) -> RuntimeOutcome:
        cancellation = cancellation or CancellationSignal()
        benchmark_task = task.to_benchmark_task()
        world = WorldState(**copy.deepcopy(task.info["initial_state"]))
        tools = make_task_tools(benchmark_task, world)
        run_id = str(uuid4())
        events: list[RuntimeEvent] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        final_response = None
        boundary_started = monotonic()
        stopped = cancellation.is_cancelled

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

        try:
            if not stopped:
                model = self._agent_model or self._make_model(request.model_name, tools)
                graph = build_graph(model, tools)
                prompt = convert_to_messages(benchmark_task["prompt"])
                async for update in graph.astream(
                    {"messages": prompt},
                    config={"recursion_limit": request.max_steps * 2 + 1},
                    stream_mode="updates",
                ):
                    elapsed_ms = (monotonic() - boundary_started) * 1000
                    boundary_started = monotonic()
                    if "agent" in update:
                        message = update["agent"]["messages"][-1]
                        turn_id = message.id or str(uuid4())
                        message_usage = self._message_usage(message)
                        for key in usage:
                            usage[key] += message_usage.get(key, 0)
                        await emit(
                            EventKind.MODEL_TURN,
                            turn_id,
                            content=self._json_value(message.content),
                            usage=message_usage or None,
                            duration_ms=elapsed_ms,
                            metadata=self._message_metadata(message),
                        )
                        for call in message.tool_calls:
                            await emit(
                                EventKind.TOOL_CALL,
                                call["id"],
                                parent_id=turn_id,
                                name=call["name"],
                                arguments=self._json_value(call.get("args", {})),
                            )
                        if not message.tool_calls:
                            final_response = self._json_value(message.content)
                        elif cancellation.is_cancelled:
                            stopped = True
                            break
                    if "tools" in update:
                        messages = update["tools"]["messages"]
                        per_tool_ms = elapsed_ms / max(len(messages), 1)
                        for message in messages:
                            is_error = getattr(message, "status", None) == "error"
                            await emit(
                                EventKind.TOOL_ERROR if is_error else EventKind.TOOL_RESULT,
                                message.tool_call_id,
                                name=message.name,
                                result=None if is_error else self._json_value(message.content),
                                error=str(message.content) if is_error else None,
                                duration_ms=per_tool_ms,
                                metadata=self._message_metadata(message),
                            )
                        if cancellation.is_cancelled:
                            stopped = True
                            break

            status = ExitStatus.STOPPED if stopped else ExitStatus.COMPLETED
            await emit(
                EventKind.COMPLETION,
                run_id,
                content={"status": status.value},
            )
            return self._outcome(
                status=status,
                task=task,
                run_id=run_id,
                events=events,
                final_response=final_response,
                world=world,
                usage=usage,
            )
        except Exception as error:
            await emit(
                EventKind.COMPLETION,
                run_id,
                content={"status": ExitStatus.FAILED.value},
                error=f"{type(error).__name__}: {error}",
            )
            return self._outcome(
                status=ExitStatus.FAILED,
                task=task,
                run_id=run_id,
                events=events,
                final_response=final_response,
                world=world,
                usage=usage,
                terminal_error=f"{type(error).__name__}: {error}",
            )

    @staticmethod
    def _make_model(model_name: str, tools: list[Any]) -> Runnable[Any, BaseMessage]:
        base_url = os.environ.get("LIBRA_BASE_URL")
        if not base_url:
            raise RuntimeError("Set LIBRA_BASE_URL in mock-agent/.env before running the benchmark")
        return ChatOpenAI(
            model=model_name,
            api_key=os.environ.get("LIBRA_INTERVIEW_API_KEY")
            or os.environ["OPENAI_API_KEY"],
            base_url=base_url,
            use_responses_api=True,
        ).bind_tools(tools)

    @staticmethod
    def _message_usage(message: BaseMessage) -> dict[str, int]:
        metadata = getattr(message, "usage_metadata", None) or {}
        return {
            key: int(metadata.get(key, 0))
            for key in ("input_tokens", "output_tokens", "total_tokens")
            if key in metadata
        }

    @staticmethod
    def _message_metadata(message: BaseMessage) -> dict[str, Any]:
        metadata = getattr(message, "response_metadata", None) or {}
        return MockAgentRuntime._json_value(metadata)

    @staticmethod
    def _json_value(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {str(key): MockAgentRuntime._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [MockAgentRuntime._json_value(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _outcome(
        *,
        status: ExitStatus,
        task: TaskDefinition,
        run_id: str,
        events: list[RuntimeEvent],
        final_response: Any,
        world: WorldState,
        usage: dict[str, int],
        terminal_error: str | None = None,
    ) -> RuntimeOutcome:
        score = score_world(task.to_benchmark_task(), world)
        return RuntimeOutcome(
            status=status,
            task_id=task.summary.task_id,
            run_id=run_id,
            events=tuple(events),
            final_response=final_response,
            world_state=world.model_dump(mode="json"),
            score=score,
            usage=usage,
            terminal_error=terminal_error,
        )
