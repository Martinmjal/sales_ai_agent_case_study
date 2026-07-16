import asyncio

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
import pytest

from mock_agent.catalog import TaskCatalog, UnknownTaskError
from mock_agent.contract import (
    CancellationSignal,
    EventKind,
    ExitStatus,
    RuntimeRequest,
)
from mock_agent.runtime import MockAgentRuntime


def trace_agent(messages):
    if not any(isinstance(message, ToolMessage) for message in messages):
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "zoom_list_meetings", "args": {}, "id": "meetings"},
                {"name": "zoom_find_meeting", "args": {}, "id": "missing"},
            ],
            usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )
    return AIMessage(content="Meeting inventory checked.")


def test_catalog_exposes_registered_sales_tasks_by_canonical_id():
    catalog = TaskCatalog.from_sales_dataset()

    summaries = catalog.list_tasks()
    task = catalog.get_task("sales.zoom_calendar_conflict")

    assert len(summaries) == 100
    assert len({summary.task_id for summary in summaries}) == 100
    assert task.summary in summaries
    assert task.summary.prompt[-1].role == "user"
    assert task.summary.tools == tuple(task.info["zapier_tools"])
    assert task.summary.assertion_count == len(task.info["assertions"])
    with pytest.raises(UnknownTaskError, match="sales.not_registered"):
        catalog.get_task("sales.not_registered")


def test_runtime_emits_a_correlated_framework_neutral_completed_trace():
    observed = []
    runtime = MockAgentRuntime(agent_model=RunnableLambda(trace_agent))

    outcome = asyncio.run(
        runtime.run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            ),
            event_sink=observed.append,
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert observed == list(outcome.events)
    assert [event.kind for event in outcome.events] == [
        EventKind.MODEL_TURN,
        EventKind.TOOL_CALL,
        EventKind.TOOL_CALL,
        EventKind.TOOL_RESULT,
        EventKind.TOOL_ERROR,
        EventKind.MODEL_TURN,
        EventKind.COMPLETION,
    ]
    assert [event.sequence for event in outcome.events] == list(range(1, 8))
    assert outcome.events[1].parent_id == outcome.events[2].parent_id
    assert outcome.events[1].correlation_id == outcome.events[3].correlation_id == "meetings"
    assert outcome.events[2].correlation_id == outcome.events[4].correlation_id == "missing"
    assert outcome.final_response == "Meeting inventory checked."
    assert outcome.usage["total_tokens"] == 12
    assert outcome.score is not None
    assert outcome.world_state["zoom"]["meetings"]


def test_runtime_returns_structured_stopped_and_failed_outcomes():
    request = RuntimeRequest(
        task_id="sales.zoom_calendar_conflict",
        model_name="scripted-test",
    )
    cancellation = CancellationSignal()

    def stop_after_model_boundary(event):
        if event.kind is EventKind.MODEL_TURN:
            cancellation.cancel()

    stopped = asyncio.run(
        MockAgentRuntime(agent_model=RunnableLambda(trace_agent)).run(
            request,
            event_sink=stop_after_model_boundary,
            cancellation=cancellation,
        )
    )

    def fail_agent(_messages):
        raise RuntimeError("scripted model failure")

    failed = asyncio.run(
        MockAgentRuntime(agent_model=RunnableLambda(fail_agent)).run(request)
    )

    assert stopped.status is ExitStatus.STOPPED
    assert EventKind.TOOL_RESULT not in [event.kind for event in stopped.events]
    assert stopped.score is not None
    assert stopped.terminal_error is None
    assert failed.status is ExitStatus.FAILED
    assert failed.terminal_error == "RuntimeError: scripted model failure"
    assert failed.events[-1].kind is EventKind.COMPLETION
