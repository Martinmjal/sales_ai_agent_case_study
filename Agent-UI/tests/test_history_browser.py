import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

from agent_ui.app import create_app
from agent_ui.store import SessionStore
from mock_agent.contract import EventKind, ExitStatus, RuntimeEvent, RuntimeOutcome
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
        expect(
            inspector.get_by_text("Trace a large enterprise", exact=False)
        ).to_be_visible()
        inspector.get_by_text("2 available tools", exact=True).click()
        expect(inspector.get_by_text("Find matching CRM accounts.")).to_be_visible()

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
