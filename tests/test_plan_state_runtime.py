import asyncio
import json

from sales_agent.adapter import AutomationBenchAdapter
from sales_agent.contract import (
    CancellationSignal,
    EventKind,
    ExitStatus,
    RuntimeRequest,
    TerminationReason,
)
from sales_agent.model import ModelReply, ProviderFailure, ToolCall
from sales_agent.plan_state_runtime import PlanStateRuntime
from sales_agent.runtime_support import RunBudget


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return next(self.replies)


class FailingAdapter:
    def open(self, task_id):
        raise RuntimeError(f"cannot initialize {task_id}")


class ScoringFailureAdapter:
    def __init__(self):
        self._base = AutomationBenchAdapter()

    def open(self, task_id):
        session = self._base.open(task_id)

        class Session:
            agent_task = session.agent_task

            def evaluate(self):
                raise RuntimeError("official scorer unavailable")

            def world_state(self):
                return session.world_state()

        return Session()


def evidence(requirement_id, requirement, *source_tools):
    return {
        "id": requirement_id,
        "requirement": requirement,
        "source_tools": list(source_tools),
    }


def test_adapter_initialization_failure_returns_classified_terminal_evidence():
    model = ScriptedModel([])

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model, adapter=FailingAdapter()).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.FAILED
    assert outcome.termination_reason is TerminationReason.ADAPTER_INITIALIZATION_FAILED
    assert outcome.score is None
    assert outcome.world_state == {}
    assert [event.kind for event in outcome.events] == [
        EventKind.ADAPTER_ERROR,
        EventKind.COMPLETION,
    ]
    assert "cannot initialize" in outcome.terminal_error
    assert model.requests == []


def test_event_persistence_failure_stops_before_the_next_external_side_effect():
    marker = "MUST NOT BE PERSISTED OR SENT"
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "notify", "objective": "Notify operations."},
                    "steps": [
                        {
                            "id": "notify-operations",
                            "objective": "Send the operations message.",
                            "required_evidence": [
                                evidence(
                                    "notification",
                                    "The sent notification",
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
                        id="notification-call",
                        name="slack_send_channel_message",
                        arguments={
                            "channel_name": "ops-updates",
                            "text": marker,
                        },
                    ),
                )
            ),
        ]
    )
    persisted = []

    def failing_sink(event):
        if event.kind is EventKind.TOOL_CALL:
            raise OSError("session store unavailable")
        persisted.append(event)

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            ),
            event_sink=failing_sink,
        )
    )

    assert outcome.status is ExitStatus.FAILED
    assert outcome.termination_reason is TerminationReason.EVENT_PERSISTENCE_FAILED
    assert marker not in json.dumps(outcome.world_state)
    assert EventKind.TOOL_CALL in [event.kind for event in outcome.events]
    assert [event.kind for event in outcome.events][-2:] == [
        EventKind.EVENT_PERSISTENCE_ERROR,
        EventKind.COMPLETION,
    ]
    assert "session store unavailable" in outcome.terminal_error
    assert persisted[-1].kind is EventKind.MODEL_TURN


def test_scoring_failure_preserves_the_completed_trace_response_and_world():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "inspect", "objective": "Inspect meetings."},
                    "steps": [
                        {
                            "id": "inspect-meetings",
                            "objective": "Inspect the meeting records.",
                            "required_evidence": [
                                evidence(
                                    "meeting-record",
                                    "A meeting record",
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
                        id="meeting-call",
                        name="zoom_list_meetings",
                        arguments={},
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="complete",
                        name="complete_step",
                        arguments={
                            "plan_revision": 3,
                            "step_id": "inspect-meetings",
                            "summary": "Meeting records were inspected.",
                            "evidence": [
                                {
                                    "requirement_id": "meeting-record",
                                    "fact": "Meeting records were returned.",
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
                        id="finish",
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
        PlanStateRuntime(
            model_client=model,
            adapter=ScoringFailureAdapter(),
        ).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert outcome.termination_reason is TerminationReason.GOAL_COMPLETED
    assert outcome.final_response == "Meeting inspection completed."
    assert outcome.score is None
    assert outcome.world_state
    assert "official scorer unavailable" in outcome.evaluation_error
    assert [event.kind for event in outcome.events][-2:] == [
        EventKind.EVALUATION_ERROR,
        EventKind.COMPLETION,
    ]
    assert outcome.events[-1].content["evaluation_available"] is False


def test_malformed_function_arguments_are_recoverable_without_dispatch():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "inspect", "objective": "Inspect meetings."},
                    "steps": [
                        {
                            "id": "inspect-meetings",
                            "objective": "Inspect the meeting records.",
                            "required_evidence": [
                                evidence(
                                    "meeting-record",
                                    "A meeting record",
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
                        id="malformed-call",
                        name="zoom_list_meetings",
                        arguments={},
                        argument_error={
                            "type": "malformed_arguments_json",
                            "message": "JSONDecodeError: invalid JSON",
                            "raw_arguments": "{not-json",
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="meeting-call",
                        name="zoom_list_meetings",
                        arguments={},
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="complete",
                        name="complete_step",
                        arguments={
                            "plan_revision": 3,
                            "step_id": "inspect-meetings",
                            "summary": "Meeting records were inspected.",
                            "evidence": [
                                {
                                    "requirement_id": "meeting-record",
                                    "fact": "Meeting records were returned.",
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
                        id="finish",
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
    malformed = next(
        event
        for event in outcome.events
        if event.kind is EventKind.TOOL_ERROR and event.correlation_id == "malformed-call"
    )
    assert malformed.error["type"] == "malformed_arguments_json"
    next_context = model.requests[2].input[-1]["content"]["tool_observations"]
    assert next_context[-1]["error"]["type"] == "malformed_arguments_json"
    assert [call["call_id"] for call in next_context if call["succeeded"]] == []


def test_tool_reported_failures_exceptions_and_invalid_arguments_recover_without_retries():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "resolve", "objective": "Resolve the meeting."},
                    "steps": [
                        {
                            "id": "reschedule",
                            "objective": "Reschedule the conflicting meeting.",
                            "required_evidence": [
                                evidence(
                                    "updated",
                                    "The updated Zoom record",
                                    "zoom_update_meeting",
                                )
                            ],
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
                    ToolCall(
                        id="invalid-arguments",
                        name="zoom_find_meeting",
                        arguments={},
                    ),
                    ToolCall(
                        id="unknown-tool",
                        name="invented_tool",
                        arguments={},
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
                tool_calls=(
                    ToolCall(
                        id="complete",
                        name="complete_step",
                        arguments={
                            "plan_revision": 3,
                            "step_id": "reschedule",
                            "summary": "The corrected update succeeded.",
                            "evidence": [
                                {
                                    "requirement_id": "updated",
                                    "fact": "Meeting 1234567890 was rescheduled.",
                                    "source_call_id": "corrected-update",
                                }
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="finish",
                        name="finish",
                        arguments={
                            "outcome": "completed",
                            "final_response": "The meeting was rescheduled.",
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
    errors = [
        (event.correlation_id, event.error["type"])
        for event in outcome.events
        if event.kind is EventKind.TOOL_ERROR
    ]
    assert errors == [
        ("failed-write", "tool_reported_error"),
        ("failed-read", "tool_reported_error"),
        ("bad-date", "tool_exception"),
        ("invalid-arguments", "invalid_arguments"),
        ("unknown-tool", "unknown_tool"),
    ]
    recovery = model.requests[2].input[-1]["content"]["tool_observations"]
    assert [item["error"]["type"] for item in recovery] == [
        "tool_reported_error",
        "tool_reported_error",
        "tool_exception",
        "invalid_arguments",
        "unknown_tool",
    ]
    assert [item["side_effect"] for item in recovery] == [
        True,
        False,
        True,
        False,
        False,
    ]
    assert [
        event.correlation_id
        for event in outcome.events
        if event.kind is EventKind.TOOL_CALL and event.name == "zoom_update_meeting"
    ] == ["failed-write", "bad-date", "corrected-update"]


def test_cancellation_waits_for_the_completed_multi_call_batch_boundary():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "inspect", "objective": "Inspect records."},
                    "steps": [
                        {
                            "id": "inspect-records",
                            "objective": "Inspect meeting and policy records.",
                            "required_evidence": [
                                evidence(
                                    "meetings",
                                    "Meeting records",
                                    "zoom_list_meetings",
                                ),
                                evidence(
                                    "policy",
                                    "Priority policy rows",
                                    "google_sheets_get_many_rows",
                                ),
                            ],
                        }
                    ],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="meetings",
                        name="zoom_list_meetings",
                        arguments={},
                    ),
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

    def cancel_after_first_result(event):
        if event.kind is EventKind.TOOL_RESULT and event.correlation_id == "meetings":
            cancellation.cancel()

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            ),
            event_sink=cancel_after_first_result,
            cancellation=cancellation,
        )
    )

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.CANCELLED
    assert len(model.requests) == 2
    assert [
        event.correlation_id for event in outcome.events if event.kind is EventKind.TOOL_RESULT
    ] == ["meetings", "policy"]
    assert [event.kind for event in outcome.events][-2:] == [
        EventKind.CANCELLATION,
        EventKind.COMPLETION,
    ]


def test_provider_retry_exhaustion_is_visible_and_classified():
    class ProviderFailingModel:
        async def respond(self, _request):
            raise ProviderFailure(
                TimeoutError("provider timed out"),
                [
                    {
                        "retry": 1,
                        "max_retries": 2,
                        "error_type": "TimeoutError",
                        "status_code": None,
                    },
                    {
                        "retry": 2,
                        "max_retries": 2,
                        "error_type": "TimeoutError",
                        "status_code": None,
                    },
                ],
                transient=True,
            )

    outcome = asyncio.run(
        PlanStateRuntime(model_client=ProviderFailingModel()).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.FAILED
    assert outcome.termination_reason is TerminationReason.MODEL_ERROR
    assert sum(event.kind is EventKind.PROVIDER_RETRY for event in outcome.events) == 2
    assert [event.kind for event in outcome.events][-2:] == [
        EventKind.MODEL_ERROR,
        EventKind.COMPLETION,
    ]
    assert outcome.events[-2].content["infrastructure_failure"] is True


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


def test_runtime_revises_remaining_work_and_keeps_successful_side_effects_visible():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "adapt", "objective": "Adapt to discovery."},
                    "steps": [
                        {
                            "id": "notify",
                            "objective": "Notify operations before continuing.",
                            "required_evidence": [
                                evidence(
                                    "notification",
                                    "The operations notification",
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
                        id="notification-call",
                        name="slack_send_channel_message",
                        arguments={
                            "channel_name": "ops-updates",
                            "text": "Discovery workflow started.",
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="revise",
                        name="revise_plan",
                        arguments={
                            "plan_revision": 3,
                            "invalidation_reason": "A meeting record must be inspected first.",
                            "active_step_disposition": "superseded",
                            "replacement_steps": [
                                {
                                    "id": "inspect-meetings",
                                    "objective": "Inspect the discovered meeting record.",
                                    "required_evidence": [
                                        evidence(
                                            "meeting-record",
                                            "The discovered meeting record",
                                            "zoom_list_meetings",
                                        )
                                    ],
                                }
                            ],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="meeting-call",
                        name="zoom_list_meetings",
                        arguments={},
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="complete-inspection",
                        name="complete_step",
                        arguments={
                            "plan_revision": 6,
                            "step_id": "inspect-meetings",
                            "summary": "The meeting record was inspected.",
                            "evidence": [
                                {
                                    "requirement_id": "meeting-record",
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
                        id="finish",
                        name="finish",
                        arguments={
                            "outcome": "completed",
                            "final_response": "Discovery handled without repeating the notification.",
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
    assert [
        event.kind
        for event in outcome.events
        if event.kind
        in {
            EventKind.STEP_SUPERSEDED,
            EventKind.PLAN_REVISED,
            EventKind.PLAN_CREATED,
            EventKind.STEP_STARTED,
        }
    ] == [
        EventKind.PLAN_CREATED,
        EventKind.STEP_STARTED,
        EventKind.STEP_SUPERSEDED,
        EventKind.PLAN_REVISED,
        EventKind.PLAN_CREATED,
        EventKind.STEP_STARTED,
    ]
    post_revision_state = model.requests[3].input[-1]["content"]["plan_state"]
    notification = post_revision_state["successful_tool_calls"][0]
    assert notification["call_id"] == "notification-call"
    assert notification["side_effect"] is True
    assert notification["result"] is not None
    assert "Discovery workflow started." in json.dumps(outcome.world_state)
    assert [
        event.correlation_id
        for event in outcome.events
        if event.kind is EventKind.TOOL_CALL and event.name == "slack_send_channel_message"
    ] == ["notification-call"]


def test_multiple_plan_revisions_are_bounded_and_reconstructable_from_events():
    def replacement(step_id, requirement_id):
        return {
            "id": step_id,
            "objective": f"Inspect records through {step_id}.",
            "required_evidence": [
                evidence(
                    requirement_id,
                    "A meeting record",
                    "zoom_list_meetings",
                )
            ],
        }

    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "adapt", "objective": "Adapt twice."},
                    "steps": [replacement("initial-step", "initial-evidence")],
                }
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="revision-one",
                        name="revise_plan",
                        arguments={
                            "plan_revision": 2,
                            "invalidation_reason": "First discovery.",
                            "active_step_disposition": "superseded",
                            "replacement_steps": [replacement("second-step", "second-evidence")],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="revision-two",
                        name="revise_plan",
                        arguments={
                            "plan_revision": 4,
                            "invalidation_reason": "Second discovery.",
                            "active_step_disposition": "failed",
                            "replacement_steps": [replacement("final-step", "final-evidence")],
                        },
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="meeting-call",
                        name="zoom_list_meetings",
                        arguments={},
                    ),
                )
            ),
            ModelReply(
                tool_calls=(
                    ToolCall(
                        id="complete",
                        name="complete_step",
                        arguments={
                            "plan_revision": 7,
                            "step_id": "final-step",
                            "summary": "The final replacement was completed.",
                            "evidence": [
                                {
                                    "requirement_id": "final-evidence",
                                    "fact": "Meeting records were returned.",
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
                        id="finish",
                        name="finish",
                        arguments={
                            "outcome": "completed",
                            "final_response": "Both discoveries were handled.",
                        },
                    ),
                )
            ),
        ]
    )
    budget = RunBudget(
        max_model_turns=10,
        max_tool_calls=4,
        max_plan_revisions=2,
        deadline_seconds=30,
        max_consecutive_no_progress_turns=2,
    )

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model, budget=budget).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    revisions = [event for event in outcome.events if event.kind is EventKind.PLAN_REVISED]
    assert [event.content["invalidation_reason"] for event in revisions] == [
        "First discovery.",
        "Second discovery.",
    ]
    assert sum(event.kind is EventKind.PLAN_CREATED for event in outcome.events) == 3
    assert [
        (event.correlation_id, event.kind.value)
        for event in outcome.events
        if event.kind in {EventKind.STEP_FAILED, EventKind.STEP_SUPERSEDED}
    ] == [
        ("initial-step", "step_superseded"),
        ("second-step", "step_failed"),
    ]


def test_model_turn_exhaustion_uses_the_reserved_tools_disabled_partial_finalizer():
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "inspect", "objective": "Inspect meetings."},
                    "steps": [
                        {
                            "id": "inspect-meetings",
                            "objective": "Inspect the meeting records.",
                            "required_evidence": [
                                evidence(
                                    "meeting-record",
                                    "A meeting record",
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
                        id="meeting-call",
                        name="zoom_list_meetings",
                        arguments={},
                    ),
                )
            ),
            ModelReply(
                content={
                    "outcome": "partial",
                    "final_response": (
                        "Meeting records were retrieved, but the evidence-backed step "
                        "could not be completed within the run budget."
                    ),
                }
            ),
        ]
    )
    budget = RunBudget(
        max_model_turns=2,
        max_tool_calls=4,
        max_plan_revisions=1,
        deadline_seconds=30,
        max_consecutive_no_progress_turns=2,
    )

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model, budget=budget).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.PARTIAL
    assert "retrieved" in outcome.final_response
    assert [event.kind for event in outcome.events][-3:] == [
        EventKind.BUDGET_EXHAUSTED,
        EventKind.RUN_FINALIZING,
        EventKind.COMPLETION,
    ]
    finalizer = model.requests[-1]
    assert finalizer.role == "run_finalizer"
    assert finalizer.tools == ()
    context = finalizer.input[-1]["content"]
    assert context["trigger"]["budget"] == "model_turns"
    assert context["plan_state"]["active_step_id"] == "inspect-meetings"
    assert context["successful_tool_calls"][0]["call_id"] == "meeting-call"
    assert context["unresolved_steps"] == ["inspect-meetings"]


def test_deadline_exhaustion_finalizes_before_dispatching_the_late_model_action():
    now = [0.0]
    replies = iter(
        [
            ModelReply(
                content={
                    "goal": {"id": "inspect", "objective": "Inspect meetings."},
                    "steps": [
                        {
                            "id": "inspect-meetings",
                            "objective": "Inspect meeting records.",
                            "required_evidence": [
                                evidence(
                                    "meeting-record",
                                    "A meeting record",
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
                        id="late-call",
                        name="zoom_list_meetings",
                        arguments={},
                    ),
                )
            ),
            ModelReply(
                content={
                    "outcome": "blocked",
                    "final_response": "The deadline elapsed before the inspection could run.",
                }
            ),
        ]
    )

    class DeadlineModel:
        def __init__(self):
            self.requests = []

        async def respond(self, request):
            self.requests.append(request)
            reply = next(replies)
            if len(self.requests) == 2:
                now[0] = 31.0
            return reply

    model = DeadlineModel()
    budget = RunBudget(
        max_model_turns=10,
        max_tool_calls=4,
        max_plan_revisions=1,
        deadline_seconds=30,
        max_consecutive_no_progress_turns=2,
        clock=lambda: now[0],
    )

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model, budget=budget).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.BLOCKED
    assert not any(
        event.kind is EventKind.TOOL_CALL and event.correlation_id == "late-call"
        for event in outcome.events
    )
    exhausted = next(event for event in outcome.events if event.kind is EventKind.BUDGET_EXHAUSTED)
    assert exhausted.content == {"budget": "deadline", "limit": 30}
    assert model.requests[-1].role == "run_finalizer"


def test_consecutive_no_progress_warns_once_then_finalizes_as_blocked():
    empty_turn = ModelReply(content="No action yet.")
    model = ScriptedModel(
        [
            ModelReply(
                content={
                    "goal": {"id": "inspect", "objective": "Inspect meetings."},
                    "steps": [
                        {
                            "id": "inspect-meetings",
                            "objective": "Inspect the meeting records.",
                            "required_evidence": [
                                evidence(
                                    "meeting-record",
                                    "A meeting record",
                                    "zoom_list_meetings",
                                )
                            ],
                        }
                    ],
                }
            ),
            empty_turn,
            empty_turn,
            empty_turn,
            ModelReply(
                content={
                    "outcome": "blocked",
                    "final_response": "The run was blocked because no executable action was produced.",
                }
            ),
        ]
    )
    budget = RunBudget(
        max_model_turns=10,
        max_tool_calls=4,
        max_plan_revisions=1,
        deadline_seconds=30,
        max_consecutive_no_progress_turns=2,
    )

    outcome = asyncio.run(
        PlanStateRuntime(model_client=model, budget=budget).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="scripted-test",
            )
        )
    )

    assert outcome.status is ExitStatus.STOPPED
    assert outcome.termination_reason is TerminationReason.BLOCKED
    warnings = [event for event in outcome.events if event.kind is EventKind.NO_PROGRESS_WARNING]
    assert len(warnings) == 1
    warning_context = model.requests[3].input[-1]["content"]["control_observations"]
    assert warning_context[-1]["warning"]["code"] == "no_progress_warning"
    exhausted = next(event for event in outcome.events if event.kind is EventKind.BUDGET_EXHAUSTED)
    assert exhausted.content == {"budget": "no_progress_turns", "limit": 2}


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
    corrections = [event for event in outcome.events if event.kind is EventKind.PROTOCOL_CORRECTION]
    assert corrections[0].content["error"]["code"] == "mixed_business_control_batch"
    assert "MIXED BATCH MUST NOT EXECUTE" not in json.dumps(outcome.world_state)
    assert [
        event.correlation_id
        for event in outcome.events
        if event.kind is EventKind.TOOL_CALL and event.name == "slack_send_channel_message"
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
                    ToolCall(id="meeting-call", name="zoom_list_meetings", arguments={}),
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
                        id="premature-finish",
                        name="finish",
                        arguments={
                            "outcome": "completed",
                            "final_response": "Claimed success too early.",
                        },
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
        PlanStateRuntime(
            model_client=model,
            budget=RunBudget(
                max_model_turns=20,
                max_tool_calls=8,
                max_plan_revisions=1,
                deadline_seconds=30,
                max_consecutive_no_progress_turns=10,
            ),
        ).run(
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
        "incomplete_plan",
        "stale_plan_revision",
        "unknown_step",
        "unknown_or_unsuccessful_source_call",
    ]
    assert sum(event.kind is EventKind.STEP_COMPLETED for event in outcome.events) == 1
