import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

from agent_ui.app import create_app
from agent_ui.store import SessionStore
from automationbench.schema.salesforce import Contact
from automationbench.schema.world import WorldState
from mock_agent.contract import EventKind, ExitStatus, RuntimeEvent, RuntimeOutcome
from mock_agent.adapter import score_world
from playwright.sync_api import expect, sync_playwright

from test_api import ControlledRuntime, live_server


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


class LiveTraceRuntime:
    def __init__(self):
        self.started = Event()
        self.release = Event()

    async def run(self, request, *, event_sink=None, cancellation=None):
        events = [
            RuntimeEvent(
                sequence=1,
                kind=EventKind.MODEL_TURN,
                timestamp="2026-07-16T03:00:00+00:00",
                run_id="live-trace",
                correlation_id="turn-live",
                content="I will inspect both sources.",
            ),
            RuntimeEvent(
                sequence=2,
                kind=EventKind.TOOL_CALL,
                timestamp="2026-07-16T03:00:01+00:00",
                run_id="live-trace",
                correlation_id="live-account",
                parent_id="turn-live",
                name="search_accounts",
                arguments={"query": "Northwind"},
            ),
            RuntimeEvent(
                sequence=3,
                kind=EventKind.TOOL_CALL,
                timestamp="2026-07-16T03:00:01+00:00",
                run_id="live-trace",
                correlation_id="live-contact",
                parent_id="turn-live",
                name="read_contacts",
                arguments={"account_id": "account-1"},
            ),
        ]
        for event in events:
            await event_sink(event)
        self.started.set()
        await asyncio.to_thread(self.release.wait)
        events.extend(
            [
                RuntimeEvent(
                    sequence=4,
                    kind=EventKind.TOOL_RESULT,
                    timestamp="2026-07-16T03:00:02+00:00",
                    run_id="live-trace",
                    correlation_id="live-account",
                    name="search_accounts",
                    result={"id": "account-1"},
                    duration_ms=20,
                ),
                RuntimeEvent(
                    sequence=5,
                    kind=EventKind.TOOL_RESULT,
                    timestamp="2026-07-16T03:00:02+00:00",
                    run_id="live-trace",
                    correlation_id="live-contact",
                    name="read_contacts",
                    result={"owner": "Casey"},
                    duration_ms=20,
                ),
                RuntimeEvent(
                    sequence=6,
                    kind=EventKind.MODEL_TURN,
                    timestamp="2026-07-16T03:00:03+00:00",
                    run_id="live-trace",
                    correlation_id="turn-final",
                    content="Northwind is owned by Casey.",
                ),
                RuntimeEvent(
                    sequence=7,
                    kind=EventKind.COMPLETION,
                    timestamp="2026-07-16T03:00:04+00:00",
                    run_id="live-trace",
                    correlation_id="live-trace",
                    content={"status": "completed"},
                ),
            ]
        )
        for event in events[3:]:
            await event_sink(event)
        return RuntimeOutcome(
            status=ExitStatus.COMPLETED,
            task_id=request.task_id,
            run_id="live-trace",
            events=tuple(events),
            final_response="Northwind is owned by Casey.",
            world_state={},
            score={"partial_credit": 1.0, "assertions": []},
            usage={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        )


def session_artifact(session_id, task_id, name, created_at, status, score=None):
    timestamp = created_at.isoformat()
    return {
        "schema_version": 1,
        "session_id": session_id,
        "status": status,
        "lifecycle": {
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": timestamp if status != "Running" else None,
            "terminal_error": None,
        },
        "task": {
            "task_id": task_id,
            "name": name,
            "prompt": [{"role": "user", "content": f"Run {name}."}],
            "tool_definitions": [],
        },
        "agent": {
            "model": "browser-test",
            "max_steps": 12,
            "agent_version": "mock-agent/0.1.0",
        },
        "events": [],
        "final_response": "Finished." if status != "Running" else None,
        "evaluation": None if score is None else {"partial_credit": score},
        "usage": None,
        "initial_world": {},
        "final_world": None,
    }


def causal_trace_artifact(created_at):
    artifact = session_artifact(
        "causal-session",
        "sales.multi_hop_lookup",
        "Multi Hop Lookup",
        created_at,
        "Completed",
        0.75,
    )
    artifact["task"]["prompt"] = [
        {
            "role": "user",
            "content": "Trace a large enterprise account request " + "carefully. " * 45,
        }
    ]
    artifact["task"]["tool_definitions"] = [
        {
            "name": "search_accounts",
            "description": "Find matching CRM accounts.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
        {
            "name": "read_contacts",
            "description": "Read contacts for an account.",
            "input_schema": {"type": "object"},
        },
    ]
    artifact["events"] = [
        {
            "sequence": 1,
            "kind": "model_turn",
            "correlation_id": "turn-1",
            "content": "I will search accounts and contacts together.",
            "duration_ms": 120.4,
        },
        {
            "sequence": 2,
            "kind": "tool_call",
            "correlation_id": "call-accounts",
            "parent_id": "turn-1",
            "name": "search_accounts",
            "arguments": {"query": "A" * 500},
        },
        {
            "sequence": 3,
            "kind": "tool_call",
            "correlation_id": "call-contacts",
            "parent_id": "turn-1",
            "name": "read_contacts",
            "arguments": {"account_id": "account-1"},
        },
        {
            "sequence": 4,
            "kind": "tool_result",
            "correlation_id": "call-accounts",
            "name": "search_accounts",
            "result": {"records": ["Northwind " + "record " * 70]},
            "duration_ms": 42.8,
        },
        {
            "sequence": 5,
            "kind": "tool_error",
            "correlation_id": "call-contacts",
            "name": "read_contacts",
            "error": "CRM permission denied for account-1",
            "duration_ms": 44.1,
        },
        {
            "sequence": 6,
            "kind": "model_turn",
            "correlation_id": "turn-2",
            "content": "I can continue with the account result.",
            "duration_ms": 90,
        },
        {
            "sequence": 7,
            "kind": "tool_call",
            "correlation_id": "call-owner",
            "parent_id": "turn-2",
            "name": "read_contacts",
            "arguments": {"account_id": "account-2"},
        },
        {
            "sequence": 8,
            "kind": "tool_result",
            "correlation_id": "call-owner",
            "name": "read_contacts",
            "result": {"owner": "Casey"},
            "duration_ms": 18,
        },
        {
            "sequence": 9,
            "kind": "completion",
            "correlation_id": "trace-run",
            "content": {"status": "completed"},
        },
    ]
    artifact["final_response"] = "Northwind is owned by Casey."
    return artifact


def evaluated_artifact(created_at):
    initial_world = WorldState()
    initial_world.salesforce.contacts = [
        Contact(
            id="existing-contact",
            email="existing@example.com",
            first_name="Existing",
            last_name="Contact",
        )
    ]
    final_world = initial_world.model_copy(deep=True)
    final_world.salesforce.contacts.append(
        Contact(
            id="new-contact",
            email="new@example.com",
            first_name="New",
            last_name="Contact",
            phone="555-123-4567",
        )
    )
    assertions = [
        {
            "type": "salesforce_record_exists",
            "collection": "contacts",
            "record_id": "existing-contact",
        },
        {
            "type": "salesforce_contact_phone_equals",
            "contact_id": "new-contact",
            "phone": "555-123-4567",
        },
        {
            "type": "salesforce_record_exists",
            "collection": "contacts",
            "record_id": "missing-contact",
        },
    ]
    task = {
        "info": {
            "assertions": assertions,
            "initial_state": initial_world.model_dump(mode="json"),
        }
    }
    score = score_world(task, final_world)
    artifact = session_artifact(
        "evaluated-session",
        "sales.evidence_review",
        "Evidence Review",
        created_at,
        "Completed",
    )
    artifact["lifecycle"]["completed_at"] = (
        created_at + timedelta(seconds=4.25)
    ).isoformat()
    artifact["task"]["assertions"] = assertions
    artifact["events"] = [
        {
            "sequence": 1,
            "kind": "model_turn",
            "correlation_id": "reasoned-turn",
            "content": "I will create the requested contact.",
            "metadata": {
                "reasoning_summary": "Checked the target fields before writing."
            },
        },
        {
            "sequence": 2,
            "kind": "completion",
            "correlation_id": "evaluated-run",
            "content": {"status": "completed"},
        },
    ]
    artifact["final_response"] = "Created the requested contact."
    artifact["evaluation"] = score
    artifact["usage"] = {
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
        "reasoning_tokens": 18,
    }
    artifact["initial_world"] = initial_world.model_dump(mode="json")
    artifact["final_world"] = final_world.model_dump(mode="json")
    return artifact, score


def sparse_normalized_world_artifact(created_at):
    artifact = session_artifact(
        "sparse-normalized-session",
        "sales.zoom_calendar_conflict",
        "Zoom Calendar Conflict",
        created_at,
        "Completed",
        1.0,
    )
    initial_world = {
        "meta": {
            "schema_version": "0.1.0",
            "current_time": "2026-02-20T12:00:00+00:00",
            "allowed_services": ["google_sheets", "zoom"],
        },
        "google_sheets": {
            "rows": [
                {
                    "spreadsheet_id": "meeting-policy",
                    "worksheet_id": "priority-rules",
                    "row_id": 2,
                    "cells": {"Priority": "1", "Rule": "C-level attendee"},
                }
            ]
        },
        "zoom": {
            "meetings": [
                {
                    "id": 1234567890,
                    "topic": "Q1 Product Review - External",
                    "start_time": "2026-02-20T14:00:00+00:00",
                }
            ]
        },
    }
    final_world = WorldState.model_validate(initial_world).model_dump(mode="json")
    final_world["zoom"]["meetings"][0]["topic"] = (
        "[RESCHEDULED] Q1 Product Review - External"
    )
    artifact["initial_world"] = initial_world
    artifact["final_world"] = final_world
    return artifact


def test_evaluator_hides_world_schema_normalization_noise(tmp_path):
    artifact = sparse_normalized_world_artifact(datetime.now(timezone.utc))
    store = SessionStore(tmp_path)
    store.create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='sparse-normalized-session']").click()

        world_changes = page.locator("#world-diff .world-change")
        expect(world_changes).to_have_count(1)
        expect(world_changes.first).to_contain_text("world.zoom.meetings[0].topic")
        expect(world_changes.first).to_contain_text("Q1 Product Review - External")
        expect(world_changes.first).to_contain_text(
            "[RESCHEDULED] Q1 Product Review - External"
        )
        browser.close()


def test_evaluator_matches_reordered_world_records_by_identity(tmp_path):
    artifact = session_artifact(
        "reordered-world-session",
        "sales.zoom_calendar_conflict",
        "Zoom Calendar Conflict",
        datetime.now(timezone.utc),
        "Completed",
        1.0,
    )
    initial_world = {
        "meta": {
            "current_time": "2026-02-20T12:00:00+00:00",
            "allowed_services": ["zoom"],
        },
        "zoom": {
            "meetings": [
                {
                    "id": "meeting-a",
                    "topic": "First unchanged meeting",
                    "start_time": "2026-02-20T14:00:00+00:00",
                },
                {
                    "id": "meeting-b",
                    "topic": "Second unchanged meeting",
                    "start_time": "2026-02-20T16:00:00+00:00",
                },
            ]
        },
    }
    final_world = WorldState.model_validate(initial_world).model_dump(mode="json")
    final_world["zoom"]["meetings"].reverse()
    artifact["initial_world"] = initial_world
    artifact["final_world"] = final_world
    SessionStore(tmp_path).create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='reordered-world-session']").click()

        expect(page.locator("#world-summary")).to_have_text("No changes")
        page.get_by_text("World changes", exact=True).click()
        expect(page.locator("#world-activity")).to_have_text(
            "No world changes recorded."
        )
        browser.close()


def record_activity_artifact(created_at):
    artifact = sparse_normalized_world_artifact(created_at)
    artifact["session_id"] = "record-activity-session"
    artifact["final_world"]["zoom"]["meetings"][0]["start_time"] = (
        "2026-02-20T16:00:00Z"
    )
    artifact["final_world"]["slack"]["messages"].append(
        {
            "ts": "1784196225.974537",
            "channel_id": "C_OPS",
            "user_id": "USLACKBOT",
            "text": "Scheduling conflict resolved.",
            "is_bot": True,
            "bot_name": "Zapier",
        }
    )
    return artifact


def correlated_record_activity_artifact(created_at):
    artifact = record_activity_artifact(created_at)
    artifact["session_id"] = "correlated-record-activity-session"
    meeting = artifact["final_world"]["zoom"]["meetings"][0]
    message = artifact["final_world"]["slack"]["messages"][0]
    artifact["events"] = [
        {
            "sequence": 1,
            "kind": "tool_call",
            "correlation_id": "read-zoom",
            "name": "zoom_find_meeting",
            "arguments": {"meeting_id": 1234567890},
        },
        {
            "sequence": 2,
            "kind": "tool_result",
            "correlation_id": "read-zoom",
            "name": "zoom_find_meeting",
            "result": {"meeting": meeting},
        },
        {
            "sequence": 3,
            "kind": "tool_call",
            "correlation_id": "write-zoom",
            "name": "zoom_update_meeting",
            "arguments": {
                "meeting_id": 1234567890,
                "topic": meeting["topic"],
                "start_time": meeting["start_time"],
            },
        },
        {
            "sequence": 4,
            "kind": "tool_result",
            "correlation_id": "write-zoom",
            "name": "zoom_update_meeting",
            "result": {"success": True, "meeting": meeting},
        },
        {
            "sequence": 5,
            "kind": "tool_call",
            "correlation_id": "write-slack",
            "name": "slack_send_channel_message",
            "arguments": {"channel": "C_OPS", "text": message["text"]},
        },
        {
            "sequence": 6,
            "kind": "tool_result",
            "correlation_id": "write-slack",
            "name": "slack_send_channel_message",
            "result": {"success": True, "message": message},
        },
    ]
    artifact["evaluation"] = {
        "partial_credit": 0.5,
        "assertions": [
            {
                "type": "zoom_meeting_field_equals",
                "passed": True,
                "excluded": False,
                "params": {
                    "meeting_id": 1234567890,
                    "field": "topic",
                    "value": meeting["topic"],
                },
            },
            {
                "type": "zoom_meeting_field_equals",
                "passed": False,
                "excluded": False,
                "params": {
                    "meeting_id": 1234567890,
                    "field": "start_time",
                    "value": "2026-02-20T16:00:00Z",
                },
            },
            {
                "type": "slack_message_exists",
                "passed": True,
                "excluded": False,
                "params": {"text_contains": "Scheduling conflict"},
            },
            {
                "type": "slack_message_exists",
                "passed": True,
                "excluded": True,
                "params": {"text_contains": "resolved"},
            },
        ],
    }
    return artifact


def test_evaluator_collapses_world_activity_behind_a_concise_summary(tmp_path):
    artifact = record_activity_artifact(datetime.now(timezone.utc))
    SessionStore(tmp_path).create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='record-activity-session']").click()

        expect(page.locator("#world-summary")).to_have_text(
            "2 applications · 2 records · 3 changes"
        )
        expect(page.locator("#world-diff .world-change").first).to_be_hidden()
        expect(page.get_by_text("Raw session JSON", exact=True)).to_be_visible()

        page.get_by_text("World changes", exact=True).click()
        expect(page.locator("#world-diff .world-change")).to_have_count(3)
        expect(page.locator("#world-activity .world-application").first).to_be_visible()
        expect(page.locator("#world-diff .world-change").first).to_be_hidden()
        browser.close()


def test_evaluator_groups_world_activity_by_application_and_record(tmp_path):
    artifact = record_activity_artifact(datetime.now(timezone.utc))
    SessionStore(tmp_path).create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='record-activity-session']").click()
        page.get_by_text("World changes", exact=True).click()

        application_groups = page.locator("#world-activity .world-application")
        expect(application_groups).to_have_count(2)

        zoom = page.locator("[data-world-application='zoom']")
        expect(zoom.locator("summary").first).to_contain_text(
            "Zoom1 record · 2 changes"
        )
        expect(zoom.locator(".world-record")).to_be_hidden()
        zoom.locator("summary").first.click()
        expect(zoom.locator(".world-record")).to_have_count(1)
        expect(zoom.locator(".world-record")).to_contain_text(
            "Updated meeting 1234567890"
        )
        expect(zoom.locator(".world-field-change")).to_have_count(2)

        slack = page.locator("[data-world-application='slack']")
        expect(slack.locator("summary").first).to_contain_text(
            "Slack1 record · 1 change"
        )
        slack.locator("summary").first.click()
        expect(slack.locator(".world-record")).to_have_count(1)
        expect(slack.locator(".world-record")).to_contain_text(
            "Created message 1784196225.974537"
        )
        expect(slack.locator(".world-record")).to_contain_text(
            "Scheduling conflict resolved."
        )

        technical_diff = page.locator("#technical-world-diff")
        expect(technical_diff.locator("#world-diff .world-change").first).to_be_hidden()
        technical_diff.get_by_text("Technical state diff", exact=True).click()
        expect(technical_diff.locator("#world-diff .world-change")).to_have_count(3)
        browser.close()


def test_world_activity_connects_writes_and_assertions_to_source_evidence(tmp_path):
    artifact = correlated_record_activity_artifact(datetime.now(timezone.utc))
    SessionStore(tmp_path).create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator(
            "[data-session-id='correlated-record-activity-session']"
        ).click()
        page.get_by_text("World changes", exact=True).click()

        zoom = page.locator("[data-world-application='zoom']")
        zoom.locator("summary").first.click()
        expect(zoom.locator(".world-tool-reference")).to_have_text(
            "Write · zoom_update_meeting"
        )
        expect(zoom.locator(".world-assertion-passed")).to_contain_text(
            "Passed · zoom_meeting_field_equals"
        )
        expect(zoom.locator(".world-assertion-failed")).to_contain_text(
            "Failed · zoom_meeting_field_equals"
        )

        zoom.locator(".world-tool-reference").click()
        write = page.locator(
            "[data-correlation-id='write-zoom'][data-trace-kind='tool_call']"
        )
        expect(write).to_have_attribute("open", "")
        expect(write.locator("summary")).to_be_focused()
        expect(page.locator("[data-correlation-id='read-zoom']")).to_have_count(1)

        page.locator("#world-section").scroll_into_view_if_needed()
        slack = page.locator("[data-world-application='slack']")
        slack.locator("summary").first.click()
        expect(slack.locator(".world-assertion-passed")).to_contain_text(
            "Passed · slack_message_exists"
        )
        expect(slack.locator(".world-assertion-excluded")).to_contain_text(
            "Pre-satisfied · excluded · slack_message_exists"
        )
        browser.close()


def test_world_activity_explains_when_correlation_and_evaluation_are_unavailable(
    tmp_path,
):
    artifact = record_activity_artifact(datetime.now(timezone.utc))
    SessionStore(tmp_path).create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='record-activity-session']").click()
        page.get_by_text("World changes", exact=True).click()
        zoom = page.locator("[data-world-application='zoom']")
        zoom.locator("summary").first.click()

        expect(zoom).to_contain_text("Originating write unavailable · uncorrelated")
        expect(zoom).to_contain_text("Assertion evidence unavailable")
        expect(zoom.locator(".world-tool-reference")).to_have_count(0)
        browser.close()


def test_world_activity_disclosures_remain_keyboard_operable_on_narrow_screens(
    tmp_path,
):
    artifact = record_activity_artifact(datetime.now(timezone.utc))
    SessionStore(tmp_path).create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 390, "height": 760})
        page.goto(base_url)

        page.get_by_role("button", name="Open session history").click()
        page.locator("[data-session-id='record-activity-session']").click()
        page.get_by_role("button", name="Open evaluator inspector").click()

        world_summary = page.locator("#world-section > summary")
        world_summary.focus()
        world_summary.dispatch_event(
            "keydown", {"key": "Enter", "bubbles": True}
        )
        expect(page.locator("#world-section")).to_have_attribute("open", "")

        zoom_summary = page.locator(
            "[data-world-application='zoom'] > summary"
        )
        zoom_summary.focus()
        zoom_summary.dispatch_event(
            "keydown", {"key": "Enter", "bubbles": True}
        )
        expect(page.locator("[data-world-application='zoom']")).to_have_attribute(
            "open", ""
        )
        expect(page.locator("#technical-world-diff")).not_to_have_attribute(
            "open", ""
        )

        raw_session = page.get_by_text("Raw session JSON", exact=True)
        raw_session.scroll_into_view_if_needed()
        expect(raw_session).to_be_visible()
        assert page.locator("#inspector").evaluate(
            "node => node.scrollWidth <= node.clientWidth"
        )
        browser.close()


def test_evaluator_exposes_complete_deterministic_evidence(tmp_path):
    artifact, official_score = evaluated_artifact(datetime.now(timezone.utc))
    store = SessionStore(tmp_path)
    store.create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='evaluated-session']").click()

        evidence = page.locator("#evaluation-evidence")
        expect(evidence.get_by_text("Completed", exact=True)).to_be_visible()
        expect(evidence.get_by_text("Partial credit", exact=True)).to_be_visible()
        expect(evidence.get_by_text("50%", exact=True)).to_be_visible()
        expect(evidence.get_by_text("Strict completion", exact=True)).to_be_visible()
        expect(
            evidence.locator("[data-metric-state='failed']", has_text="Failed")
        ).to_be_visible()
        expect(evidence.get_by_text("1 of 2 scored assertions passed")).to_be_visible()
        expect(evidence.locator("[data-assertion-status='passed']")).to_have_count(1)
        expect(evidence.locator("[data-assertion-status='failed']")).to_have_count(1)
        expect(evidence.locator("[data-assertion-status='excluded']")).to_have_count(1)
        expect(evidence).to_contain_text(
            official_score["assertions"][1]["params"]["phone"]
        )
        expect(evidence).to_contain_text("4.25 s")
        expect(evidence).to_contain_text("165 total")
        expect(evidence).to_contain_text("18 reasoning")
        expect(evidence).to_contain_text("Checked the target fields before writing.")

        expect(page.locator("#final-response")).to_have_text(
            "Created the requested contact."
        )
        world_diff = evidence.locator("#world-diff")
        expect(world_diff).to_contain_text("new-contact")
        expect(world_diff).to_contain_text("Added")
        evidence.get_by_text("World changes", exact=True).click()
        evidence.get_by_text("Initial world snapshot", exact=True).click()
        expect(evidence.locator("#initial-world-snapshot")).to_contain_text(
            "existing-contact"
        )
        evidence.get_by_text("Final world snapshot", exact=True).click()
        expect(evidence.locator("#final-world-snapshot")).to_contain_text("new-contact")
        evidence.get_by_text("Raw session JSON", exact=True).click()
        expect(evidence.locator("#raw-session-json")).to_contain_text(
            '"session_id": "evaluated-session"'
        )
        browser.close()


def test_evaluator_marks_missing_evidence_without_inferring_reasoning(tmp_path):
    artifact = session_artifact(
        "missing-evidence-session",
        "sales.incomplete_run",
        "Incomplete Run",
        datetime.now(timezone.utc),
        "Interrupted",
    )
    artifact["final_response"] = None
    artifact["evaluation"] = None
    artifact["usage"] = None
    artifact["initial_world"] = None
    artifact["final_world"] = None
    store = SessionStore(tmp_path)
    store.create(artifact)
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='missing-evidence-session']").click()

        evidence = page.locator("#evaluation-evidence")
        expect(page.locator("#final-response")).to_have_text(
            "Final response unavailable"
        )
        for label in ("Partial credit", "Strict completion", "Token usage"):
            row = evidence.locator(".evidence-metrics > div", has_text=label)
            expect(row.locator("dd")).to_have_text("Unavailable")
        expect(evidence.get_by_text("Assertion results unavailable")).to_be_visible()
        expect(evidence.locator("#world-summary")).to_have_text("Unavailable")
        evidence.get_by_text("World changes", exact=True).click()
        expect(
            evidence.get_by_text("World changes unavailable", exact=True)
        ).to_be_visible()
        expect(evidence.locator("#reasoning-evidence")).to_be_hidden()
        evidence.get_by_text("Raw session JSON", exact=True).click()
        expect(evidence.locator("#raw-session-json")).to_contain_text('"usage": null')
        browser.close()


def test_evaluator_explains_a_completed_causal_trace(tmp_path):
    store = SessionStore(tmp_path)
    store.create(causal_trace_artifact(datetime.now(timezone.utc)))
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        page.locator("[data-session-id='causal-session']").click()

        inspector = page.locator("#inspector")
        expect(inspector.get_by_role("heading", name="Causal trace")).to_be_visible()
        expect(inspector.locator("#inspector-prompt")).to_contain_text(
            "Trace a large enterprise"
        )
        inspector.get_by_text("2 available tools", exact=True).click()
        expect(inspector.locator("#tool-definitions")).to_contain_text(
            "Find matching CRM accounts."
        )

        turns = inspector.locator("[data-trace-kind='model_turn']")
        expect(turns).to_have_count(2)
        first_batch = inspector.locator("[data-parent-id='turn-1']")
        expect(first_batch).to_have_class("parallel-tool-batch")
        expect(first_batch.locator("[data-trace-kind='tool_call']")).to_have_count(2)
        expect(
            first_batch.locator("[data-correlation-id='call-contacts']")
        ).to_contain_text("CRM permission denied for account-1")

        account_call = first_batch.locator("[data-correlation-id='call-accounts']")
        account_call.locator("summary").click()
        expect(account_call).to_contain_text('"query"')
        expect(account_call).to_contain_text("42.8 ms")
        expect(account_call).to_contain_text("call-accounts")
        expect(account_call).to_contain_text("Northwind")
        expect(inspector.locator("[data-trace-kind='completion']")).to_contain_text(
            "Northwind is owned by Casey."
        )
        browser.close()


def test_running_causal_trace_recovers_after_refresh_and_continues(tmp_path):
    runtime = LiveTraceRuntime()
    app = create_app(runtime=runtime, sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        response = page.request.post(
            f"{base_url}/api/sessions",
            data={"task_id": "sales.multi_hop_lookup"},
        )
        session_id = response.json()["session_id"]
        assert runtime.started.wait(timeout=2)

        page.goto(base_url)
        expect(page.locator("#session-status")).to_have_text("Running")
        expect(page.locator("[data-correlation-id='turn-live']")).to_have_count(1)
        expect(
            page.locator("[data-parent-id='turn-live'] [data-trace-kind='tool_call']")
        ).to_have_count(2)
        page.reload()
        expect(page.locator("[data-correlation-id='turn-live']")).to_have_count(1)
        expect(page.locator("[data-correlation-id='live-account']")).to_have_count(1)

        runtime.release.set()
        expect(page.locator("#session-status")).to_have_text("Completed")
        expect(page.locator("[data-trace-kind='model_turn']")).to_have_count(2)
        expect(page.locator("[data-correlation-id='live-account']")).to_have_count(1)
        expect(page.locator("[data-trace-kind='completion']")).to_contain_text(
            "Northwind is owned by Casey."
        )
        expect(
            page.locator(f"[data-session-id='{session_id}'] .history-status")
        ).to_have_text("Completed")
        browser.close()


def test_evaluator_can_browse_history_and_return_to_the_active_run(tmp_path):
    app = create_app(sessions_dir=tmp_path)
    store = SessionStore(tmp_path)
    now = datetime.now(timezone.utc)
    sessions = (
        session_artifact(
            "active-session",
            "sales.zoom_calendar_conflict",
            "Zoom Calendar Conflict",
            now,
            "Running",
        ),
        session_artifact(
            "previous-session",
            "sales.multi_hop_lookup",
            "Multi Hop Lookup",
            now - timedelta(days=3),
            "Completed",
            0.75,
        ),
        session_artifact(
            "older-session",
            "sales.qualify_lead",
            "Qualify Lead",
            now - timedelta(days=12),
            "Failed",
            0.25,
        ),
    )

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)
        expect(page.get_by_text("No runs yet", exact=True)).to_be_visible()

        for session in sessions:
            store.create(session)
        page.reload()

        for heading in ("Today", "Previous 7 days", "Older"):
            expect(
                page.get_by_role("heading", name=heading, exact=True)
            ).to_be_visible()

        history_search = page.get_by_label("Search execution history")
        history_search.fill("multi hop")
        expect(page.locator("[data-session-id='previous-session']")).to_be_visible()
        expect(page.locator(".history-item")).to_have_count(1)
        history_search.fill("sales.qualify_lead")
        page.locator("[data-session-id='older-session']").click()

        expect(page.locator("#session-workspace")).to_have_attribute(
            "data-session-id", "older-session"
        )
        expect(page.locator("#inspector")).to_have_attribute(
            "data-session-id", "older-session"
        )
        expect(page.get_by_role("button", name="Return to active run")).to_be_visible()
        page.get_by_role("button", name="Return to active run").click()
        expect(page.locator("#session-workspace")).to_have_attribute(
            "data-session-id", "active-session"
        )

        collapse = page.locator("#history-toggle")
        collapse.click()
        expect(collapse).to_have_attribute("aria-expanded", "false")
        page.get_by_role("button", name="Expand history").click()
        expect(page.get_by_label("Search execution history")).to_be_visible()
        browser.close()


def test_evaluator_sees_startup_interruption_and_stops_only_the_active_run(tmp_path):
    store = SessionStore(tmp_path)
    now = datetime.now(timezone.utc)
    store.create(
        session_artifact(
            "orphaned-session",
            "sales.multi_hop_lookup",
            "Multi Hop Lookup",
            now - timedelta(minutes=2),
            "Running",
        )
    )
    failed = session_artifact(
        "failed-session",
        "sales.qualify_lead",
        "Qualify Lead",
        now - timedelta(minutes=4),
        "Failed",
    )
    failed["lifecycle"]["terminal_error"] = "RuntimeError: scripted failure"
    store.create(failed)
    runtime = ControlledRuntime("model")
    app = create_app(runtime=runtime, sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)

        orphaned = page.locator("[data-session-id='orphaned-session']")
        expect(orphaned.locator(".history-status")).to_have_text("Interrupted")
        orphaned.click()
        expect(page.locator("#session-status")).to_have_text("Interrupted")
        expect(page.locator("#session-score")).to_have_text("Unavailable")
        expect(page.get_by_role("button", name="Stop run")).to_have_count(0)

        response = page.request.post(
            f"{base_url}/api/sessions",
            data={"task_id": "sales.zoom_calendar_conflict"},
        )
        active_session_id = response.json()["session_id"]
        assert runtime.started.wait(timeout=2)
        page.reload()

        stop = page.get_by_role("button", name="Stop run")
        expect(stop).to_be_visible()
        stop.click()
        runtime.release.set()
        expect(page.locator("#session-status")).to_have_text("Stopped")
        expect(stop).to_be_hidden()
        expect(
            page.locator(f"[data-session-id='{active_session_id}'] .history-status")
        ).to_have_text("Stopped")
        expect(
            page.locator("[data-session-id='failed-session'] .history-status")
        ).to_have_text("Failed")
        browser.close()


def test_responsive_workspace_keeps_navigation_keyboard_operable(tmp_path):
    store = SessionStore(tmp_path)
    store.create(causal_trace_artifact(datetime.now(timezone.utc)))
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(base_url)

        history = page.locator("#history-panel")
        workspace = page.locator(".workspace")
        inspector = page.locator("#inspector")
        wide_boxes = [item.bounding_box() for item in (history, workspace, inspector)]
        assert all(box is not None for box in wide_boxes)
        assert wide_boxes[0]["x"] < wide_boxes[1]["x"] < wide_boxes[2]["x"]

        page.set_viewport_size({"width": 960, "height": 800})
        page.wait_for_function(
            "document.querySelector('#history-panel').getBoundingClientRect().width <= 64"
        )
        medium_boxes = [item.bounding_box() for item in (history, workspace, inspector)]
        assert all(box is not None for box in medium_boxes)
        assert medium_boxes[0]["width"] <= 64
        assert medium_boxes[0]["x"] < medium_boxes[1]["x"] < medium_boxes[2]["x"]
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        assert workspace.evaluate("node => node.scrollWidth <= node.clientWidth")

        page.set_viewport_size({"width": 390, "height": 760})
        open_history = page.get_by_role("button", name="Open session history")
        open_inspector = page.get_by_role("button", name="Open evaluator inspector")
        expect(open_history).to_be_visible()
        expect(open_inspector).to_be_visible()
        expect(history).to_be_hidden()
        expect(inspector).to_be_hidden()

        open_history.press("Enter")
        expect(history).to_be_visible()
        expect(page.get_by_role("button", name="Close session history")).to_be_focused()
        page.keyboard.press("Escape")
        expect(history).to_be_hidden()
        expect(open_history).to_be_focused()

        open_inspector.press("Enter")
        expect(inspector).to_be_visible()
        expect(
            page.get_by_role("button", name="Close evaluator inspector")
        ).to_be_focused()
        page.keyboard.press("Escape")
        expect(inspector).to_be_hidden()
        expect(open_inspector).to_be_focused()
        browser.close()


def test_long_completed_session_remains_accessible_on_a_narrow_screen(tmp_path):
    store = SessionStore(tmp_path)
    store.create(causal_trace_artifact(datetime.now(timezone.utc)))
    app = create_app(sessions_dir=tmp_path)

    with live_server(app) as base_url, sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME.exists():
            launch_options["executable_path"] = str(CHROME)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 390, "height": 760})
        page.goto(base_url)

        page.get_by_role("button", name="Open session history").click()
        session = page.locator("[data-session-id='causal-session']")
        session.click()
        expect(page.locator("#history-panel")).to_be_hidden()
        expect(page.locator("#session-status")).to_have_text("Completed")

        page.get_by_role("button", name="Open evaluator inspector").click()
        inspector = page.locator("#inspector")
        tools = inspector.get_by_text("2 available tools", exact=True)
        tools.dispatch_event("keydown", {"key": "Enter", "bubbles": True})
        expect(inspector.locator("#tool-definitions")).to_be_visible()
        expect(inspector.locator("#tool-definitions")).to_contain_text(
            "Find matching CRM accounts."
        )
        account_call = inspector.locator(
            "[data-correlation-id='call-accounts'][data-trace-kind='tool_call']"
        )
        account_call.locator("summary").dispatch_event(
            "keydown", {"key": "Enter", "bubbles": True}
        )
        expect(account_call).to_have_attribute("open", "")

        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        assert inspector.evaluate("node => node.scrollWidth <= node.clientWidth")
        browser.close()
