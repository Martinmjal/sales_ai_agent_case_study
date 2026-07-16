from agent_ui.world_diff import world_change_evidence


def evidence_session():
    initial = {
        "zoom": {
            "meetings": [
                {
                    "id": 123,
                    "topic": "Planning",
                    "start_time": "2026-07-16T14:00:00+00:00",
                }
            ]
        },
        "slack": {
            "channels": [
                {"id": "C_OPS", "name": "ops-updates", "is_private": False}
            ],
            "messages": [],
        },
    }
    final = {
        "zoom": {
            "meetings": [
                {
                    "id": 123,
                    "topic": "[RESCHEDULED] Planning",
                    "start_time": "2026-07-16T16:00:00+00:00",
                }
            ]
        },
        "slack": {
            "channels": [
                {"id": "C_OPS", "name": "ops-updates", "is_private": False}
            ],
            "messages": [
                {
                    "ts": "1784196225.974537",
                    "channel_id": "C_OPS",
                    "user_id": "USLACKBOT",
                    "text": "Alpha resolved; beta notified.",
                    "is_bot": True,
                }
            ],
        },
    }
    return {
        "initial_world": initial,
        "final_world": final,
        "events": [
            {
                "sequence": 1,
                "kind": "tool_call",
                "correlation_id": "read-zoom",
                "name": "zoom_find_meeting",
                "arguments": {"meeting_id": 123},
            },
            {
                "sequence": 2,
                "kind": "tool_result",
                "correlation_id": "read-zoom",
                "name": "zoom_find_meeting",
                "result": {"meeting": final["zoom"]["meetings"][0]},
            },
            {
                "sequence": 3,
                "kind": "tool_call",
                "correlation_id": "write-zoom",
                "name": "zoom_update_meeting",
                "arguments": {
                    "meeting_id": 123,
                    "topic": "[RESCHEDULED] Planning",
                    "start_time": "2026-07-16T16:00:00+00:00",
                },
            },
            {
                "sequence": 4,
                "kind": "tool_result",
                "correlation_id": "write-zoom",
                "name": "zoom_update_meeting",
                "result": {"success": True, "meeting": final["zoom"]["meetings"][0]},
            },
            {
                "sequence": 5,
                "kind": "tool_call",
                "correlation_id": "write-slack",
                "name": "slack_send_channel_message",
                "arguments": {
                    "channel": "C_OPS",
                    "text": "Alpha resolved; beta notified.",
                },
            },
            {
                "sequence": 6,
                "kind": "tool_result",
                "correlation_id": "write-slack",
                "name": "slack_send_channel_message",
                "result": {"success": True, "message": final["slack"]["messages"][0]},
            },
        ],
        "evaluation": {
            "assertions": [
                {
                    "type": "zoom_meeting_field_equals",
                    "passed": True,
                    "excluded": False,
                    "params": {
                        "meeting_id": 123,
                        "field": "topic",
                        "value": "[RESCHEDULED] Planning",
                    },
                },
                {
                    "type": "slack_message_exists",
                    "passed": True,
                    "excluded": False,
                    "params": {"text_contains": "Alpha resolved"},
                },
                {
                    "type": "slack_message_exists",
                    "passed": True,
                    "excluded": True,
                    "params": {"text_contains": "beta notified"},
                },
            ]
        },
    }


def test_correlates_one_write_to_multiple_changes_and_ignores_read_calls():
    changes = world_change_evidence(evidence_session())

    zoom_changes = [change for change in changes if change["application"] == "zoom"]
    assert len(zoom_changes) == 2
    assert {change["origin"]["correlation_id"] for change in zoom_changes} == {
        "write-zoom"
    }
    assert all(change["origin"]["tool_name"] == "zoom_update_meeting" for change in zoom_changes)


def test_marks_unmatched_mutations_uncorrelated_instead_of_guessing():
    session = evidence_session()
    session["events"] = [
        event for event in session["events"] if event["correlation_id"] != "write-zoom"
    ]

    changes = world_change_evidence(session)

    zoom_changes = [change for change in changes if change["application"] == "zoom"]
    assert all(change["origin"] is None for change in zoom_changes)


def test_matches_multiple_assertions_to_the_fields_and_records_they_support():
    changes = world_change_evidence(evidence_session())

    topic = next(change for change in changes if change["path"].endswith(".topic"))
    assert [(item["type"], item["status"]) for item in topic["assertions"]] == [
        ("zoom_meeting_field_equals", "passed")
    ]
    start_time = next(
        change for change in changes if change["path"].endswith(".start_time")
    )
    assert start_time["assertions"] == []
    message = next(change for change in changes if change["application"] == "slack")
    assert [(item["type"], item["status_label"]) for item in message["assertions"]] == [
        ("slack_message_exists", "Passed"),
        ("slack_message_exists", "Pre-satisfied · excluded"),
    ]
