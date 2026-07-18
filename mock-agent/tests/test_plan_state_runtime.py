import asyncio
import json

from mock_agent.contract import EventKind, ExitStatus, RuntimeRequest
from mock_agent.model import ModelReply, ToolCall
from mock_agent.plan_state_runtime import PlanStateRuntime


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return next(self.replies)


def evidence(requirement_id, requirement, *source_tools):
    return {
        "id": requirement_id,
        "requirement": requirement,
        "source_tools": list(source_tools),
    }


def test_plan_state_runtime_completes_a_blind_task_with_real_tools_and_scoring():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {
                        "id": "resolve-conflict",
                        "objective": "Resolve the meeting conflict and notify operations.",
                    },
                    "steps": [
                        {
                            "id": "inspect",
                            "objective": "Inspect the policy and conflicting meetings.",
                            "required_evidence": [
                                evidence(
                                    "policy",
                                    "The applicable priority policy",
                                    "google_sheets_get_many_rows",
                                ),
                                evidence(
                                    "zoom-record",
                                    "The conflicting Zoom meeting",
                                    "zoom_list_meetings",
                                ),
                                evidence(
                                    "calendar-record",
                                    "The conflicting calendar event",
                                    "google_calendar_find_event",
                                ),
                            ],
                        },
                        {
                            "id": "resolve",
                            "objective": "Reschedule the lower-priority meeting and notify operations.",
                            "required_evidence": [
                                evidence(
                                    "updated",
                                    "The updated Zoom record",
                                    "zoom_update_meeting",
                                ),
                                evidence(
                                    "notified",
                                    "The operations notification",
                                    "slack_send_channel_message",
                                ),
                            ],
                        },
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="policy-call",
                        name="google_sheets_get_many_rows",
                        arguments={
                            "spreadsheet_id": "ss_meeting_policy",
                            "worksheet_id": "ws_priority_rules",
                            "row_count": 50,
                        },
                    ),
                    ToolCall(id="zoom-call", name="zoom_list_meetings", arguments={}),
                    ToolCall(
                        id="calendar-call",
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
                tool_calls=(
                    ToolCall(
                        id="complete-inspect",
                        name="complete_step",
                        arguments={
                            "plan_revision": 5,
                            "step_id": "inspect",
                            "summary": "The product review is the lower-priority meeting.",
                            "evidence": [
                                {
                                    "requirement_id": "policy",
                                    "fact": "Executive sessions outrank product reviews.",
                                    "source_call_id": "policy-call",
                                },
                                {
                                    "requirement_id": "zoom-record",
                                    "fact": "Zoom meeting 1234567890 conflicts.",
                                    "source_call_id": "zoom-call",
                                },
                                {
                                    "requirement_id": "calendar-record",
                                    "fact": "Calendar event evt_conflict_001 conflicts.",
                                    "source_call_id": "calendar-call",
                                },
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="update-call",
                        name="zoom_update_meeting",
                        arguments={
                            "meeting_id": 1234567890,
                            "topic": "[RESCHEDULED] Q1 Product Review - External",
                        },
                    ),
                    ToolCall(
                        id="slack-call",
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
                tool_calls=(
                    ToolCall(
                        id="complete-resolve",
                        name="complete_step",
                        arguments={
                            "plan_revision": 9,
                            "step_id": "resolve",
                            "summary": "The meeting was rescheduled and operations was notified.",
                            "evidence": [
                                {
                                    "requirement_id": "updated",
                                    "fact": "Zoom meeting 1234567890 was updated.",
                                    "source_call_id": "update-call",
                                },
                                {
                                    "requirement_id": "notified",
                                    "fact": "The operations message was sent.",
                                    "source_call_id": "slack-call",
                                },
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="finish-run",
                        name="finish",
                        arguments={
                            "outcome": "completed",
                            "final_response": "Conflict resolved and operations notified.",
                        },
                    ),
                )
            ),
        ]
    )
    observed = []

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model).run(
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
    assert sum(event.kind is EventKind.STEP_COMPLETED for event in outcome.events) == 2
    assert not any(event.kind is EventKind.REVIEW for event in outcome.events)
    assert [request.role for request in model.requests] == [
        "planner",
        "plan_state_executor",
        "plan_state_executor",
        "plan_state_executor",
        "plan_state_executor",
        "plan_state_executor",
    ]
    assert model.requests[0].tools == ()
    assert {tool.name for tool in model.requests[1].tools} >= {
        "complete_step",
        "finish",
        "zoom_list_meetings",
    }
    control_request = model.requests[2].input[-1]["content"]
    assert [item["call_id"] for item in control_request["tool_observations"]] == [
        "policy-call",
        "zoom-call",
        "calendar-call",
    ]
    visible = json.dumps([request.input for request in model.requests], default=str)
    assert "sales.zoom_calendar_conflict" not in visible
    assert "assertions" not in visible
    assert "task_completed_correctly" not in visible
    assert "initial_state" not in visible


def test_mixed_business_and_control_calls_execute_no_side_effects_and_recover():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "notify-goal", "objective": "Notify operations."},
                    "steps": [
                        {
                            "id": "notify",
                            "objective": "Send the operations notification.",
                            "required_evidence": [
                                evidence(
                                    "notification",
                                    "The operations message",
                                    "slack_send_channel_message",
                                )
                            ],
                        }
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="mixed-side-effect",
                        name="slack_send_channel_message",
                        arguments={
                            "channel_name": "ops-updates",
                            "text": "MIXED BATCH MUST NOT EXECUTE",
                        },
                    ),
                    ToolCall(
                        id="mixed-control",
                        name="complete_step",
                        arguments={
                            "plan_revision": 2,
                            "step_id": "notify",
                            "summary": "Incorrect mixed completion.",
                            "evidence": [],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="notification-call",
                        name="slack_send_channel_message",
                        arguments={
                            "channel_name": "ops-updates",
                            "text": "The conflict was resolved safely.",
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="complete-notify",
                        name="complete_step",
                        arguments={
                            "plan_revision": 3,
                            "step_id": "notify",
                            "summary": "Operations was notified.",
                            "evidence": [
                                {
                                    "requirement_id": "notification",
                                    "fact": "The safe notification was sent.",
                                    "source_call_id": "notification-call",
                                }
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="finish-run",
                        name="finish",
                        arguments={
                            "outcome": "completed",
                            "final_response": "Operations notified.",
                        },
                    ),
                )
            ),
        ]
    )

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    corrections = [
        event for event in outcome.events if event.kind is EventKind.PROTOCOL_CORRECTION
    ]
    assert corrections[0].content["error"]["code"] == "mixed_business_control_batch"
    assert "MIXED BATCH MUST NOT EXECUTE" not in json.dumps(outcome.world_state)
    assert [
        event.correlation_id
        for event in outcome.events
        if event.kind is EventKind.TOOL_CALL
        and event.name == "slack_send_channel_message"
    ] == ["notification-call"]
    correction_context = model.requests[2].input[-1]["content"]["control_observations"]
    assert correction_context[-1]["error"]["code"] == "mixed_business_control_batch"


def test_invalid_evidence_controls_are_recoverable_observations():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "inspect-goal", "objective": "Inspect meetings."},
                    "steps": [
                        {
                            "id": "inspect",
                            "objective": "Inspect meetings.",
                            "required_evidence": [
                                evidence(
                                    "meeting",
                                    "A returned meeting record",
                                    "zoom_list_meetings",
                                )
                            ],
                        }
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="meeting-call", name="zoom_list_meetings", arguments={}
                    ),
                    ToolCall(
                        id="failed-call",
                        name="zoom_find_meeting",
                        arguments={},
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="stale-control",
                        name="complete_step",
                        arguments={
                            "plan_revision": 2,
                            "step_id": "inspect",
                            "summary": "Used a stale revision.",
                            "evidence": [
                                {
                                    "requirement_id": "meeting",
                                    "fact": "A meeting was returned.",
                                    "source_call_id": "meeting-call",
                                }
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="failed-evidence-control",
                        name="complete_step",
                        arguments={
                            "plan_revision": 3,
                            "step_id": "unknown-step",
                            "summary": "Used an unknown step.",
                            "evidence": [
                                {
                                    "requirement_id": "meeting",
                                    "fact": "A meeting was returned.",
                                    "source_call_id": "meeting-call",
                                }
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="failed-source-control",
                        name="complete_step",
                        arguments={
                            "plan_revision": 3,
                            "step_id": "inspect",
                            "summary": "Used a failed call.",
                            "evidence": [
                                {
                                    "requirement_id": "meeting",
                                    "fact": "An invented meeting was returned.",
                                    "source_call_id": "failed-call",
                                }
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="valid-control",
                        name="complete_step",
                        arguments={
                            "plan_revision": 3,
                            "step_id": "inspect",
                            "summary": "The meeting list was inspected.",
                            "evidence": [
                                {
                                    "requirement_id": "meeting",
                                    "fact": "The conflicting meeting was returned.",
                                    "source_call_id": "meeting-call",
                                }
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="finish-run",
                        name="finish",
                        arguments={
                            "outcome": "completed",
                            "final_response": "Meeting inspection completed.",
                        },
                    ),
                )
            ),
        ]
    )

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    correction_codes = [
        event.content["error"]["code"]
        for event in outcome.events
        if event.kind is EventKind.PROTOCOL_CORRECTION
    ]
    assert correction_codes == [
        "stale_plan_revision",
        "unknown_step",
        "unknown_or_unsuccessful_source_call",
    ]
    assert sum(event.kind is EventKind.STEP_COMPLETED for event in outcome.events) == 1
