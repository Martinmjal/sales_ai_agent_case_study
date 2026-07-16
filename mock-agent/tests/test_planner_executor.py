import asyncio
import json
from types import SimpleNamespace

from mock_agent.contract import EventKind, ExitStatus, RuntimeRequest
from mock_agent.model import ModelReply, OpenAIModelClient, ToolCall
from mock_agent.planner_executor import PlannerExecutorRuntime


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return next(self.replies)


class Parsed:
    def __init__(self, value):
        self.value = value

    def model_dump(self, mode="python"):
        return self.value


class FakeResponses:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=f"response-{len(self.calls)}",
            status="completed",
            output=[],
            output_parsed=Parsed(next(self.values)),
            output_text="",
            usage=SimpleNamespace(input_tokens=2, output_tokens=1, total_tokens=3),
        )


def test_runtime_completes_a_blind_planned_task_with_real_tools_and_scoring():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Resolve the meeting conflict and notify operations.",
                    "steps": [
                        {
                            "id": "inspect",
                            "objective": "Inspect the policy and conflicting meetings.",
                            "required_evidence": ["Policy, Zoom, and calendar records"],
                        },
                        {
                            "id": "resolve",
                            "objective": "Reschedule the lower-priority meeting and notify operations.",
                            "required_evidence": [
                                "Updated Zoom record and Slack message"
                            ],
                        },
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="policy",
                        name="google_sheets_get_many_rows",
                        arguments={
                            "spreadsheet_id": "ss_meeting_policy",
                            "worksheet_id": "ws_priority_rules",
                            "row_count": 50,
                        },
                    ),
                    ToolCall(id="zoom", name="zoom_list_meetings", arguments={}),
                    ToolCall(
                        id="calendar",
                        name="google_calendar_find_event",
                        arguments={
                            "calendarid": "primary",
                            "start_time": "2026-02-20T14:00:00+00:00",
                            "end_time": "2026-02-20T15:00:00+00:00",
                        },
                    ),
                )
            ),
            ModelReply(
                content={
                    "summary": "The executive session has priority over the product review.",
                    "evidence": [
                        {
                            "fact": "The product review must be rescheduled.",
                            "source_call_id": "policy",
                        },
                        {
                            "fact": "Zoom meeting 1234567890 conflicts.",
                            "source_call_id": "zoom",
                        },
                        {
                            "fact": "The calendar conflict is evt_conflict_001.",
                            "source_call_id": "calendar",
                        },
                    ],
                    "actions": [],
                    "errors": [],
                }
            ),
            ModelReply(content={"decision": "step_completed"}),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="update",
                        name="zoom_update_meeting",
                        arguments={
                            "meeting_id": 1234567890,
                            "topic": "[RESCHEDULED] Q1 Product Review - External",
                        },
                    ),
                    ToolCall(
                        id="slack",
                        name="slack_send_channel_message",
                        arguments={
                            "channel_name": "ops-updates",
                            "text": (
                                "Executive Strategy Session won; Zoom meeting 1234567890 "
                                "was rescheduled. Calendar event ID: evt_conflict_001."
                            ),
                        },
                    ),
                )
            ),
            ModelReply(
                content={
                    "summary": "The Zoom meeting was rescheduled and operations was notified.",
                    "evidence": [
                        {
                            "fact": "Zoom meeting 1234567890 was updated.",
                            "source_call_id": "update",
                        },
                        {
                            "fact": "The operations message was sent.",
                            "source_call_id": "slack",
                        },
                    ],
                    "actions": ["Updated Zoom meeting", "Sent Slack message"],
                    "errors": [],
                }
            ),
            ModelReply(
                content={
                    "decision": "goal_completed",
                    "final_response": "Conflict resolved and operations notified.",
                }
            ),
        ]
    )
    observed = []

    outcome = asyncio.run(
        PlannerExecutorRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            ),
            event_sink=observed.append,
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert outcome.final_response == "Conflict resolved and operations notified."
    assert outcome.score["partial_credit"] == 1.0
    assert outcome.score["task_completed_correctly"] == 1.0
    assert observed == list(outcome.events)
    assert [event.sequence for event in outcome.events] == list(
        range(1, len(outcome.events) + 1)
    )
    assert [event.kind for event in outcome.events] == [
        EventKind.PLANNING,
        EventKind.PLAN_CREATED,
        EventKind.STEP_STARTED,
        EventKind.EXECUTOR_TURN,
        EventKind.TOOL_CALL,
        EventKind.TOOL_CALL,
        EventKind.TOOL_CALL,
        EventKind.TOOL_RESULT,
        EventKind.TOOL_RESULT,
        EventKind.TOOL_RESULT,
        EventKind.EXECUTOR_TURN,
        EventKind.REVIEW,
        EventKind.STEP_STARTED,
        EventKind.EXECUTOR_TURN,
        EventKind.TOOL_CALL,
        EventKind.TOOL_CALL,
        EventKind.TOOL_RESULT,
        EventKind.TOOL_RESULT,
        EventKind.EXECUTOR_TURN,
        EventKind.REVIEW,
        EventKind.COMPLETION,
    ]
    calls = {
        event.correlation_id: event
        for event in outcome.events
        if event.kind is EventKind.TOOL_CALL
    }
    results = [event for event in outcome.events if event.kind is EventKind.TOOL_RESULT]
    assert all(result.correlation_id in calls for result in results)
    assert all(
        request.tools for request in model.requests if request.role == "executor"
    )
    model_input = json.dumps([request.input for request in model.requests], default=str)
    assert "sales.zoom_calendar_conflict" not in model_input
    assert "assertions" not in model_input
    assert "task_completed_correctly" not in model_input


def test_runtime_returns_structured_argument_errors_to_the_executor():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Inspect the conflicting meeting.",
                    "steps": [
                        {
                            "id": "inspect",
                            "objective": "Find the meeting.",
                            "required_evidence": ["A meeting lookup result"],
                        }
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(id="invalid", name="zoom_find_meeting", arguments={}),
                )
            ),
            ModelReply(
                content={
                    "summary": "The lookup could not run with incomplete arguments.",
                    "evidence": [],
                    "actions": [],
                    "errors": ["The meeting type is required."],
                }
            ),
            ModelReply(
                content={
                    "decision": "goal_completed",
                    "final_response": "The invalid lookup was reported.",
                }
            ),
        ]
    )

    outcome = asyncio.run(
        PlannerExecutorRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    error_event = next(
        event for event in outcome.events if event.kind is EventKind.TOOL_ERROR
    )
    retry_context = model.requests[2].input[-1]["content"]["local_transcript"]
    assert error_event.error["type"] == "invalid_arguments"
    assert error_event.correlation_id == "invalid"
    assert retry_context[0]["error"]["type"] == "invalid_arguments"
    assert retry_context[0]["error"]["details"][0]["location"] == ["type"]


def test_runtime_uses_the_direct_responses_api_without_exposing_private_fields():
    responses = FakeResponses(
        [
            {
                "goal": "Inspect the task.",
                "steps": [
                    {
                        "id": "inspect",
                        "objective": "Inspect the available evidence.",
                        "required_evidence": ["A grounded result"],
                    }
                ],
            },
            {
                "summary": "No mutation was needed for this protocol check.",
                "evidence": [],
                "actions": [],
                "errors": [],
            },
            {
                "decision": "goal_completed",
                "final_response": "The direct Responses API path completed.",
            },
        ]
    )
    client = SimpleNamespace(responses=responses)

    outcome = asyncio.run(
        PlannerExecutorRuntime(model_client=OpenAIModelClient(client=client)).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="gpt-5.6-sol",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert outcome.final_response == "The direct Responses API path completed."
    assert outcome.usage["total_tokens"] == 9
    assert len(responses.calls) == 3
    assert all(call["store"] is False for call in responses.calls)
    executor_call = responses.calls[1]
    assert executor_call["model"] == "gpt-5.6-sol"
    assert executor_call["tools"]
    assert all(item["type"] == "message" for item in executor_call["input"])
    assert "world" not in json.dumps(executor_call["tools"])
    assert "assertions" not in json.dumps(responses.calls, default=str)
