from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_ui.app import create_app
from agent_ui.store import SessionStore
from playwright.sync_api import expect, sync_playwright

from test_api import live_server


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


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
