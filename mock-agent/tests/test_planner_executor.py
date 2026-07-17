import asyncio
import json
from types import SimpleNamespace

from pydantic import BaseModel, ValidationError

from mock_agent.contract import (
    CancellationSignal,
    EventKind,
    ExitStatus,
    RuntimeRequest,
    TerminationReason,
)
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
        value = next(self.values)
        if isinstance(value, BaseException):
            raise value
        return SimpleNamespace(
            id=f"response-{len(self.calls)}",
            status="completed",
            output=[],
            output_parsed=Parsed(value),
            output_text="",
            usage=SimpleNamespace(input_tokens=2, output_tokens=1, total_tokens=3),
        )


class TransientProviderError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


class RequiredValue(BaseModel):
    value: int


def plan_evidence(requirement, *source_tools):
    return [{"requirement": requirement, "source_tools": list(source_tools)}]


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
                            "required_evidence": plan_evidence(
                                "Policy, Zoom, and calendar records",
                                "google_sheets_get_many_rows",
                                "zoom_list_meetings",
                                "google_calendar_find_event",
                            ),
                        },
                        {
                            "id": "resolve",
                            "objective": "Reschedule the lower-priority meeting and notify operations.",
                            "required_evidence": plan_evidence(
                                "Updated Zoom record and Slack message",
                                "zoom_update_meeting",
                                "slack_send_channel_message",
                            ),
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
    assert outcome.events[0].content == {
        "execution_limits": {
            "plan_steps": 6,
            "executor_tool_turns_per_attempt": 4,
            "reserved_outcome_calls_per_saturated_attempt": 1,
            "step_retries": 1,
            "replans": 1,
            "logical_model_calls": 30,
            "provider_retries": 2,
        }
    }
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
                            "required_evidence": plan_evidence(
                                "A meeting lookup result", "zoom_list_meetings"
                            ),
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


def test_runtime_normalizes_tool_failures_for_model_driven_recovery():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Reschedule the meeting.",
                    "steps": [
                        {
                            "id": "reschedule",
                            "objective": "Reschedule the conflicting meeting.",
                            "required_evidence": plan_evidence(
                                "Updated Zoom record", "zoom_update_meeting"
                            ),
                        }
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="failed-write",
                        name="zoom_update_meeting",
                        arguments={
                            "meeting_id": 9999999999,
                            "topic": "Must not be created",
                        },
                    ),
                    ToolCall(
                        id="failed-read",
                        name="google_sheets_get_spreadsheet_by_id",
                        arguments={"spreadsheet_id": "missing"},
                    ),
                    ToolCall(
                        id="bad-date",
                        name="zoom_update_meeting",
                        arguments={
                            "meeting_id": 1234567890,
                            "start_time": "not-an-iso-date",
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="corrected-update",
                        name="zoom_update_meeting",
                        arguments={
                            "meeting_id": 1234567890,
                            "topic": "[RESCHEDULED] Q1 Product Review - External",
                        },
                    ),
                )
            ),
            ModelReply(
                content={
                    "summary": "The corrected update succeeded.",
                    "evidence": [
                        {
                            "fact": "Meeting 1234567890 was rescheduled.",
                            "source_call_id": "corrected-update",
                        }
                    ],
                    "actions": ["Updated the Zoom meeting once"],
                    "errors": [],
                }
            ),
            ModelReply(
                content={
                    "decision": "goal_completed",
                    "final_response": "The meeting was rescheduled.",
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

    assert outcome.status is ExitStatus.COMPLETED
    error_events = [
        event for event in outcome.events if event.kind is EventKind.TOOL_ERROR
    ]
    assert [(event.correlation_id, event.error["type"]) for event in error_events] == [
        ("failed-write", "tool_reported_error"),
        ("failed-read", "tool_reported_error"),
        ("bad-date", "tool_exception"),
    ]
    assert error_events[0].result["success"] is False
    assert error_events[1].result == {
        "error": "Spreadsheet with id 'missing' not found"
    }
    recovery_context = model.requests[2].input[-1]["content"]["local_transcript"]
    assert [item["error"]["type"] for item in recovery_context] == [
        "tool_reported_error",
        "tool_reported_error",
        "tool_exception",
    ]
    assert [item["side_effect"] for item in recovery_context] == [True, False, True]
    assert [
        event.correlation_id
        for event in outcome.events
        if event.kind is EventKind.TOOL_CALL
    ] == ["failed-write", "failed-read", "bad-date", "corrected-update"]


def test_runtime_uses_the_direct_responses_api_without_exposing_private_fields():
    responses = FakeResponses(
        [
            {
                "goal": "Inspect the task.",
                "steps": [
                    {
                        "id": "inspect",
                        "objective": "Inspect the available evidence.",
                        "required_evidence": plan_evidence(
                            "A grounded result", "zoom_list_meetings"
                        ),
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
    planner_call = responses.calls[0]
    assert planner_call["tools"]
    executor_call = responses.calls[1]
    assert executor_call["model"] == "gpt-5.6-sol"
    assert executor_call["tools"]
    assert all(item["type"] == "message" for item in executor_call["input"])
    assert "world" not in json.dumps(executor_call["tools"])
    assert "assertions" not in json.dumps(responses.calls, default=str)


def test_runtime_corrects_a_direct_responses_schema_parse_failure():
    try:
        RequiredValue.model_validate({})
    except ValidationError as error:
        schema_error = error
    responses = FakeResponses(
        [
            schema_error,
            {
                "goal": "Inspect the task.",
                "steps": [
                    {
                        "id": "inspect",
                        "objective": "Inspect the task.",
                        "required_evidence": plan_evidence(
                            "A grounded result", "zoom_list_meetings"
                        ),
                    }
                ],
            },
            {
                "summary": "The corrected response was valid.",
                "evidence": [],
                "actions": [],
                "errors": [],
            },
            {
                "decision": "goal_completed",
                "final_response": "The corrected protocol completed.",
            },
        ]
    )

    outcome = asyncio.run(
        PlannerExecutorRuntime(
            model_client=OpenAIModelClient(
                client=SimpleNamespace(responses=responses),
                retry_delays=(0, 0),
            )
        ).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="gpt-5.6-sol",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert len(responses.calls) == 4
    assert (
        sum(event.kind is EventKind.PROTOCOL_CORRECTION for event in outcome.events)
        == 1
    )


def test_runtime_retries_a_rejected_step_with_prior_context_without_replaying_actions():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Reschedule the conflicting meeting.",
                    "steps": [
                        {
                            "id": "resolve",
                            "objective": "Reschedule the lower-priority Zoom meeting.",
                            "required_evidence": plan_evidence(
                                "The updated meeting record", "zoom_update_meeting"
                            ),
                        }
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="update-once",
                        name="zoom_update_meeting",
                        arguments={
                            "meeting_id": 1234567890,
                            "topic": "[RESCHEDULED] Q1 Product Review - External",
                        },
                    ),
                )
            ),
            ModelReply(
                content={
                    "summary": "The meeting was updated, but the evidence was vague.",
                    "evidence": [],
                    "actions": ["Updated Zoom meeting 1234567890"],
                    "errors": [],
                }
            ),
            ModelReply(
                content={
                    "decision": "retry_step",
                    "feedback": "Cite the existing update-once tool result as evidence.",
                }
            ),
            ModelReply(
                content={
                    "summary": "The existing tool result proves the meeting was updated.",
                    "evidence": [
                        {
                            "fact": "Zoom meeting 1234567890 was rescheduled.",
                            "source_call_id": "update-once",
                        }
                    ],
                    "actions": [],
                    "errors": [],
                }
            ),
            ModelReply(
                content={
                    "decision": "goal_completed",
                    "final_response": "The conflicting meeting was rescheduled.",
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

    assert outcome.status is ExitStatus.COMPLETED
    retry_request = [
        request for request in model.requests if request.role == "executor"
    ][-1]
    retry_context = retry_request.input[-1]["content"]
    assert retry_context["review_feedback"] == (
        "Cite the existing update-once tool result as evidence."
    )
    assert retry_context["previous_outcome"]["summary"] == (
        "The meeting was updated, but the evidence was vague."
    )
    assert retry_context["local_transcript"][0]["tool_call_id"] == "update-once"
    assert [
        event.name for event in outcome.events if event.kind is EventKind.TOOL_CALL
    ] == ["zoom_update_meeting"]
    assert sum(event.kind is EventKind.STEP_RETRY for event in outcome.events) == 1


def test_runtime_replans_once_with_completed_evidence_and_the_failed_step_record():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Resolve the conflict and notify operations.",
                    "steps": [
                        {
                            "id": "reschedule",
                            "objective": "Reschedule the lower-priority meeting.",
                            "required_evidence": plan_evidence(
                                "Updated Zoom record", "zoom_update_meeting"
                            ),
                        },
                        {
                            "id": "notify-v1",
                            "objective": "Notify operations.",
                            "required_evidence": plan_evidence(
                                "Slack confirmation", "slack_send_channel_message"
                            ),
                        },
                    ],
                }
            ),
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
                )
            ),
            ModelReply(
                content={
                    "summary": "The Zoom meeting was rescheduled.",
                    "evidence": [
                        {
                            "fact": "Meeting 1234567890 has the rescheduled topic.",
                            "source_call_id": "update",
                        }
                    ],
                    "actions": ["Updated Zoom meeting"],
                    "errors": [],
                }
            ),
            ModelReply(content={"decision": "step_completed"}),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="premature-slack",
                        name="slack_send_channel_message",
                        arguments={
                            "channel_name": "ops-updates",
                            "text": "Conflict update pending.",
                        },
                    ),
                )
            ),
            ModelReply(
                content={
                    "summary": "An incomplete notification was sent.",
                    "evidence": [
                        {
                            "fact": "Operations received only a pending update.",
                            "source_call_id": "premature-slack",
                        }
                    ],
                    "actions": ["Sent an incomplete Slack notification"],
                    "errors": ["The notification omitted the resolution."],
                }
            ),
            ModelReply(
                content={
                    "decision": "replan",
                    "feedback": "Replace the notification step with a direct Slack action.",
                }
            ),
            ModelReply(
                content={
                    "goal": "Resolve the conflict and notify operations.",
                    "steps": [
                        {
                            "id": "notify-v2",
                            "objective": "Send the grounded operations notification.",
                            "required_evidence": plan_evidence(
                                "Slack confirmation", "slack_send_channel_message"
                            ),
                        },
                        {
                            "id": "finish",
                            "objective": "Confirm the preserved resolution evidence.",
                            "required_evidence": plan_evidence(
                                "Accepted resolution evidence", "zoom_list_meetings"
                            ),
                        },
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
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
                    "summary": "Operations received the conflict resolution.",
                    "evidence": [
                        {
                            "fact": "A message was sent to ops-updates.",
                            "source_call_id": "slack",
                        }
                    ],
                    "actions": ["Sent Slack message"],
                    "errors": [],
                }
            ),
            ModelReply(content={"decision": "step_completed"}),
            ModelReply(
                content={
                    "summary": "The accepted evidence covers the completed resolution.",
                    "evidence": [],
                    "actions": [],
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

    outcome = asyncio.run(
        PlannerExecutorRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    planner_requests = [
        request for request in model.requests if request.role == "planner"
    ]
    assert all(request.tools for request in planner_requests)
    replan_review = next(
        request
        for request in model.requests
        if request.role == "reviewer"
        and request.input[-1]["content"]["step"]["id"] == "notify-v1"
    )
    assert [
        step["id"]
        for step in replan_review.input[-1]["content"]["current_plan"]["steps"]
    ] == ["reschedule", "notify-v1"]
    replan_context = planner_requests[1].input[-1]["content"]
    completed_step = replan_context["completed_steps"][0]
    assert completed_step["step_id"] == "reschedule"
    assert completed_step["evidence"][0]["source_call_id"] == "update"
    completed_side_effect = completed_step["side_effects"][0]
    assert completed_side_effect["tool_call_id"] == "update"
    assert completed_side_effect["name"] == "zoom_update_meeting"
    assert completed_side_effect["result"]["success"] is True
    failed_step = replan_context["failed_step"]
    assert failed_step["step"]["id"] == "notify-v1"
    assert failed_step["useful_facts"] == [
        {
            "fact": "Operations received only a pending update.",
            "source_call_id": "premature-slack",
        }
    ]
    assert failed_step["performed_actions"] == ["Sent an incomplete Slack notification"]
    assert len(failed_step["side_effects_must_not_repeat"]) == 1
    side_effect = failed_step["side_effects_must_not_repeat"][0]
    assert side_effect["tool_call_id"] == "premature-slack"
    assert side_effect["name"] == "slack_send_channel_message"
    assert side_effect["arguments"] == {
        "channel_name": "ops-updates",
        "text": "Conflict update pending.",
    }
    assert side_effect["result"]["success"] is True
    assert failed_step["errors"] == ["The notification omitted the resolution."]
    assert failed_step["invalidation_reason"] == (
        "Replace the notification step with a direct Slack action."
    )
    assert "local_transcript" not in json.dumps(replan_context)
    assert [
        event.name for event in outcome.events if event.kind is EventKind.TOOL_CALL
    ] == [
        "zoom_update_meeting",
        "slack_send_channel_message",
        "slack_send_channel_message",
    ]
    replan_event = next(
        event for event in outcome.events if event.kind is EventKind.REPLAN
    )
    plan_events = [
        event for event in outcome.events if event.kind is EventKind.PLAN_CREATED
    ]
    assert replan_event.sequence < plan_events[1].sequence


def test_runtime_finalizes_a_saturated_step_without_tools_then_reaches_review():
    replies = [
        ModelReply(
            content={
                "goal": "Inspect the meeting.",
                "steps": [
                    {
                        "id": "inspect",
                        "objective": "Inspect the meeting.",
                        "required_evidence": plan_evidence(
                            "A grounded record", "zoom_list_meetings"
                        ),
                    }
                ],
            }
        )
    ]
    replies.extend(
        ModelReply(
            tool_calls=(
                ToolCall(
                    id=f"meeting-{turn}",
                    name="zoom_list_meetings",
                    arguments={},
                ),
            )
        )
        for turn in range(4)
    )
    replies.extend(
        [
            ModelReply(
                content={
                    "summary": "The meeting was inspected.",
                    "evidence": [
                        {
                            "fact": "The meeting record was returned.",
                            "source_call_id": "meeting-3",
                        }
                    ],
                    "actions": [],
                    "unresolved_requirements": [],
                    "errors": [],
                }
            ),
            ModelReply(
                content={
                    "decision": "goal_completed",
                    "final_response": "Inspection completed.",
                }
            ),
        ]
    )
    model = ScriptedModel(replies)

    outcome = asyncio.run(
        PlannerExecutorRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert outcome.final_response == "Inspection completed."
    executor_requests = [request for request in model.requests if request.role == "executor"]
    assert [request.input[-1]["content"]["tool_turns_used"] for request in executor_requests] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert [request.input[-1]["content"]["tool_turns_remaining"] for request in executor_requests] == [4, 3, 2, 1, 0]
    assert all(request.input[-1]["content"]["reserved_outcome_policy"] for request in executor_requests)
    assert executor_requests[-1].tools == ()
    assert any(event.kind is EventKind.REVIEW for event in outcome.events)


def test_runtime_corrects_an_invalid_plan_once_then_reports_model_protocol_error():
    seven_steps = [
        {
            "id": f"step-{index}",
            "objective": f"Objective {index}",
            "required_evidence": plan_evidence(
                f"Evidence {index}", "zoom_list_meetings"
            ),
        }
        for index in range(7)
    ]
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Use an undeclared source.",
                    "steps": [
                        {
                            "id": "inspect",
                            "objective": "Inspect the task.",
                            "required_evidence": plan_evidence(
                                "Grounded evidence", "not_a_declared_tool"
                            ),
                        }
                    ],
                }
            ),
            ModelReply(content={"goal": "Too many steps", "steps": seven_steps}),
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

    assert outcome.status is ExitStatus.FAILED
    assert outcome.termination_reason is TerminationReason.MODEL_PROTOCOL_ERROR
    assert outcome.score is not None
    assert len(model.requests) == 2
    correction = model.requests[1].input[-1]["content"]["protocol_correction"]
    assert correction["role"] == "planner"
    assert correction["attempt"] == 2
    assert correction["errors"][0]["type"] == "undeclared_evidence_source"
    assert [event.kind for event in outcome.events] == [
        EventKind.PLANNING,
        EventKind.PROTOCOL_CORRECTION,
        EventKind.PROTOCOL_ERROR,
        EventKind.COMPLETION,
    ]


def test_runtime_corrects_an_invalid_review_once_then_reports_model_protocol_error():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Inspect the task.",
                    "steps": [
                        {
                            "id": "inspect",
                            "objective": "Inspect the task.",
                            "required_evidence": plan_evidence(
                                "A grounded result", "zoom_list_meetings"
                            ),
                        }
                    ],
                }
            ),
            ModelReply(
                content={
                    "summary": "The task was inspected.",
                    "evidence": [],
                    "actions": [],
                    "errors": [],
                }
            ),
            ModelReply(content={"decision": "goal_completed"}),
            ModelReply(content={"decision": "not_a_review_decision"}),
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

    assert outcome.status is ExitStatus.FAILED
    assert outcome.termination_reason is TerminationReason.MODEL_PROTOCOL_ERROR
    assert [request.role for request in model.requests] == [
        "planner",
        "executor",
        "reviewer",
        "reviewer",
    ]
    correction = model.requests[-1].input[-1]["content"]["protocol_correction"]
    assert correction["role"] == "reviewer"
    assert (
        sum(event.kind is EventKind.PROTOCOL_CORRECTION for event in outcome.events)
        == 1
    )


def test_runtime_surfaces_two_provider_retries_then_continues():
    responses = FakeResponses(
        [
            TransientProviderError(429),
            TransientProviderError(503),
            {
                "goal": "Inspect the task.",
                "steps": [
                    {
                        "id": "inspect",
                        "objective": "Inspect the available evidence.",
                        "required_evidence": plan_evidence(
                            "A grounded result", "zoom_list_meetings"
                        ),
                    }
                ],
            },
            {
                "summary": "No action was required.",
                "evidence": [],
                "actions": [],
                "errors": [],
            },
            {
                "decision": "goal_completed",
                "final_response": "The task was inspected.",
            },
        ]
    )
    runtime = PlannerExecutorRuntime(
        model_client=OpenAIModelClient(
            client=SimpleNamespace(responses=responses),
            retry_delays=(0, 0),
        )
    )

    outcome = asyncio.run(
        runtime.run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="gpt-5.6-sol",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert len(responses.calls) == 5
    assert [
        event.content
        for event in outcome.events
        if event.kind is EventKind.PROVIDER_RETRY
    ] == [
        {
            "retry": 1,
            "max_retries": 2,
            "error_type": "TransientProviderError",
            "status_code": 429,
        },
        {
            "retry": 2,
            "max_retries": 2,
            "error_type": "TransientProviderError",
            "status_code": 503,
        },
    ]


def test_runtime_stops_after_two_provider_retries_with_a_model_error_outcome():
    responses = FakeResponses(
        [
            TransientProviderError(429),
            TransientProviderError(500),
            TransientProviderError(503),
        ]
    )

    outcome = asyncio.run(
        PlannerExecutorRuntime(
            model_client=OpenAIModelClient(
                client=SimpleNamespace(responses=responses),
                retry_delays=(0, 0),
            )
        ).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="gpt-5.6-sol",
            )
        )
    )

    assert outcome.status is ExitStatus.FAILED
    assert outcome.termination_reason is TerminationReason.MODEL_ERROR
    assert outcome.score is not None
    assert len(responses.calls) == 3
    assert sum(event.kind is EventKind.PROVIDER_RETRY for event in outcome.events) == 2
    assert [event.kind for event in outcome.events[-2:]] == [
        EventKind.MODEL_ERROR,
        EventKind.COMPLETION,
    ]
    assert outcome.events[-2].content["infrastructure_failure"] is True
    assert "HTTP 503" in outcome.terminal_error


def test_runtime_cancels_after_completing_the_active_tool_batch():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Inspect task evidence.",
                    "steps": [
                        {
                            "id": "inspect",
                            "objective": "Inspect policy and meetings.",
                            "required_evidence": plan_evidence(
                                "Policy and meeting records", "zoom_list_meetings"
                            ),
                        }
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(id="meetings", name="zoom_list_meetings", arguments={}),
                    ToolCall(
                        id="policy",
                        name="google_sheets_get_many_rows",
                        arguments={
                            "spreadsheet_id": "ss_meeting_policy",
                            "worksheet_id": "ws_priority_rules",
                            "row_count": 50,
                        },
                    ),
                )
            ),
        ]
    )
    cancellation = CancellationSignal()

    def cancel_during_batch(event):
        if event.kind is EventKind.TOOL_RESULT and event.correlation_id == "meetings":
            cancellation.cancel()

    outcome = asyncio.run(
        PlannerExecutorRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            ),
            event_sink=cancel_during_batch,
            cancellation=cancellation,
        )
    )

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.CANCELLED
    assert len(model.requests) == 2
    assert [
        event.correlation_id
        for event in outcome.events
        if event.kind is EventKind.TOOL_RESULT
    ] == ["meetings", "policy"]
    assert [event.kind for event in outcome.events[-2:]] == [
        EventKind.CANCELLATION,
        EventKind.COMPLETION,
    ]


def test_runtime_exhausts_the_single_step_retry_budget():
    step_outcome = {
        "summary": "The evidence is still incomplete.",
        "evidence": [],
        "actions": [],
        "errors": ["Missing evidence"],
    }
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": "Inspect the conflict.",
                    "steps": [
                        {
                            "id": "inspect-first",
                            "objective": "Inspect the first source.",
                            "required_evidence": plan_evidence(
                                "Grounded evidence", "zoom_list_meetings"
                            ),
                        },
                        {
                            "id": "inspect-second",
                            "objective": "Inspect the second source.",
                            "required_evidence": plan_evidence(
                                "Grounded evidence", "zoom_list_meetings"
                            ),
                        },
                    ],
                }
            ),
            ModelReply(content=step_outcome),
            ModelReply(content={"decision": "retry_step", "feedback": "Retry."}),
            ModelReply(content=step_outcome),
            ModelReply(content={"decision": "step_completed"}),
            ModelReply(content=step_outcome),
            ModelReply(content={"decision": "retry_step", "feedback": "Retry again."}),
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

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.BUDGET_EXHAUSTED
    assert len(model.requests) == 7
    budget_event = next(
        event for event in outcome.events if event.kind is EventKind.BUDGET_EXHAUSTED
    )
    assert budget_event.content == {"budget": "step_retries", "limit": 1}


def test_runtime_exhausts_the_single_replan_budget():
    def plan(step_id):
        return {
            "goal": "Resolve the conflict.",
            "steps": [
                {
                    "id": step_id,
                    "objective": "Resolve the conflict.",
                    "required_evidence": plan_evidence(
                        "Grounded evidence", "zoom_list_meetings"
                    ),
                }
            ],
        }

    failed_outcome = {
        "summary": "The plan remains invalid.",
        "evidence": [],
        "actions": [],
        "errors": ["Invalid plan"],
    }
    model = ScriptedModel(
        [
            ModelReply(content=plan("attempt-v1")),
            ModelReply(content=failed_outcome),
            ModelReply(content={"decision": "replan", "feedback": "Replace it."}),
            ModelReply(content=plan("attempt-v2")),
            ModelReply(content=failed_outcome),
            ModelReply(content={"decision": "replan", "feedback": "Replace it again."}),
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

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.BUDGET_EXHAUSTED
    assert len(model.requests) == 6
    budget_event = next(
        event for event in outcome.events if event.kind is EventKind.BUDGET_EXHAUSTED
    )
    assert budget_event.content == {"budget": "replans", "limit": 1}


def test_runtime_stops_before_the_thirty_first_logical_model_call():
    def six_step_plan(prefix):
        return {
            "goal": "Inspect all required evidence.",
            "steps": [
                {
                    "id": f"{prefix}-{index}",
                    "objective": f"Inspect item {index}.",
                    "required_evidence": plan_evidence(
                        f"Evidence {index}", "zoom_list_meetings"
                    ),
                }
                for index in range(6)
            ],
        }

    outcome_record = {
        "summary": "The step produced accepted evidence.",
        "evidence": [],
        "actions": [],
        "errors": [],
    }
    replies = [ModelReply(content=six_step_plan("initial"))]
    for index in range(6):
        replies.append(ModelReply(content=outcome_record))
        decision = (
            {"decision": "replan", "feedback": "Replace pending work."}
            if index == 5
            else {"decision": "step_completed"}
        )
        replies.append(ModelReply(content=decision))
    replies.append(ModelReply(content=six_step_plan("replacement")))
    for _ in range(5):
        replies.extend(
            [
                ModelReply(content=outcome_record),
                ModelReply(content={"decision": "step_completed"}),
            ]
        )
    replies.extend(
        ModelReply(
            tool_calls=(
                ToolCall(
                    id=f"saturated-{turn}",
                    name="zoom_list_meetings",
                    arguments={},
                ),
            )
        )
        for turn in range(4)
    )
    replies.extend(
        [
            ModelReply(content={**outcome_record, "unresolved_requirements": []}),
            ModelReply(content={"decision": "retry_step", "feedback": "Retry."}),
        ]
    )
    model = ScriptedModel(replies)

    outcome = asyncio.run(
        PlannerExecutorRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.BUDGET_EXHAUSTED
    assert len(model.requests) == 30
    budget_event = next(
        event for event in outcome.events if event.kind is EventKind.BUDGET_EXHAUSTED
    )
    assert budget_event.content == {"budget": "logical_model_calls", "limit": 30}
