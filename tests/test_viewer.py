from __future__ import annotations

import json
import socket
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

import pytest
import uvicorn
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from sales_agent.artifacts import (
    ArtifactEvaluation,
    ArtifactSummary,
    ArtifactTiming,
    ArtifactWorlds,
    RunArtifact,
    RunArtifactStore,
)
from sales_agent.contract import ExitStatus, RuntimeOutcome, TerminationReason
from sales_agent.main import main as single_run_main
from sales_agent.viewer.app import create_app
from sales_agent.viewer.store import ArtifactRepository

TASK_ID = "sales.zoom_calendar_conflict"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _event(run_id, sequence, kind, correlation_id, **values):
    return {
        "sequence": sequence,
        "kind": kind,
        "timestamp": f"2026-07-17T12:00:{sequence:02}+00:00",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "parent_id": values.get("parent_id"),
        "name": values.get("name"),
        "content": values.get("content"),
        "arguments": values.get("arguments"),
        "result": values.get("result"),
        "error": values.get("error"),
        "usage": values.get("usage"),
        "duration_ms": values.get("duration_ms"),
        "metadata": values.get("metadata", {}),
    }


def _artifact(
    run_id,
    *,
    started_at="2026-07-17T12:00:00+00:00",
    status="completed",
    termination_reason="goal_completed",
    final_response="Finished safely.",
    available=True,
    evaluation_error=None,
    assertion_evidence_available=True,
    score=None,
    trace=(),
):
    official_score = (
        score
        if score is not None
        else {"partial_credit": 1.0, "task_completed_correctly": 1.0}
        if available
        else {}
    )
    assertions = (
        ({"type": "example_assertion", "passed": True, "params": {"long": "x" * 500}},)
        if assertion_evidence_available and available
        else ()
    )
    return RunArtifact(
        run_id=run_id,
        task={
            "task_id": TASK_ID,
            "name": 'Unsafe <script id="injected">alert(1)</script> task',
            "prompt": [
                {
                    "role": "user",
                    "content": "Inspect <img src=x onerror=alert(1)> safely.",
                }
            ],
            "tools": ["zoom_list_meetings"],
            "assertions": [],
            "tool_definitions": [],
        },
        configuration={
            "identity": "configuration-a",
            "model": "scripted-model",
            "harness_version": "plan-state/1.0.0",
            "prompt_version": "plan-state-prompts/v1",
            "evaluation_protocol_version": "test/v1",
            "execution_limits": {"max_model_turns": 30},
            "runtime": {"id": "custom", "label": "Custom agent", "version": "1"},
        },
        timing=ArtifactTiming(
            started_at=started_at,
            updated_at=started_at,
            finished_at=started_at if status != "running" else None,
            duration_ms=25 if status != "running" else None,
        ),
        status=status,
        termination_reason=termination_reason if status != "running" else None,
        trace=tuple(trace),
        summary=ArtifactSummary(0, 2, 1, False),
        usage={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
        final_response=final_response,
        terminal_error="runtime exploded" if status == "failed" else None,
        evaluation_error=evaluation_error,
        worlds=ArtifactWorlds(
            {"records": [{"id": 1, "value": "before"}]},
            {"records": [{"id": 1, "value": "after"}]},
        ),
        evaluation=ArtifactEvaluation(
            available=available,
            official_score=official_score,
            assertion_evidence=assertions,
            assertion_evidence_available=assertion_evidence_available,
            context=None,
        ),
    )


def _write(directory: Path, artifact: RunArtifact, filename: str | None = None) -> Path:
    return RunArtifactStore(directory).write(
        artifact, filename=filename or f"{artifact.run_id}.json"
    )


def _trace(run_id):
    steps = [
        {"id": "inspect", "objective": "Inspect the account."},
        {"id": "notify", "objective": "Notify the owner."},
    ]
    return (
        _event(
            run_id,
            1,
            "plan_created",
            "plan-1",
            content={"goal": "Resolve the request.", "steps": steps},
        ),
        _event(run_id, 2, "step_started", "inspect", content=steps[0]),
        _event(
            run_id,
            3,
            "tool_call",
            "call-1",
            parent_id="turn-1",
            name="zoom_list_meetings",
            arguments={"query": "x" * 800},
        ),
        _event(
            run_id,
            4,
            "tool_result",
            "call-1",
            name="zoom_list_meetings",
            result={"success": True, "meetings": [1]},
            duration_ms=12,
        ),
        _event(run_id, 5, "step_completed", "inspect", content={"id": "inspect"}),
        _event(
            run_id,
            6,
            "tool_error",
            "call-2",
            name="notify_owner",
            error={"message": "delivery blocked"},
        ),
        _event(
            run_id,
            7,
            "completion",
            run_id,
            content={"status": "completed", "termination_reason": "goal_completed"},
        ),
    )


def test_recent_runs_are_flat_newest_first_and_requests_are_read_only(tmp_path):
    older = _write(
        tmp_path,
        _artifact("older", started_at="2026-07-17T12:00:00+00:00"),
    )
    newer = _write(
        tmp_path,
        _artifact(
            "newer",
            started_at="2026-07-17T13:00:00+00:00",
            score={"partial_credit": 0.5, "task_completed_correctly": 0.0},
        ),
    )
    (tmp_path / "unsupported.json").write_text(
        '{"artifact_type":"run_artifact","schema_version":999,"run_id":"unsupported"}',
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in (older, newer, tmp_path / "unsupported.json")}

    repository = ArtifactRepository((tmp_path,))
    assert [reference.artifact.run_id for reference in repository.recent()] == [
        "newer",
        "older",
    ]
    client = TestClient(create_app(artifacts_dir=tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert response.text.index("/runs/newer") < response.text.index("/runs/older")
    assert "partial 0.500" in response.text
    assert "unsupported" not in response.text
    assert '<nav aria-label="Recent runs">' in response.text
    redirect = client.get("/?run_id=newer", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/runs/newer"
    assert all(path.read_bytes() == payload for path, payload in before.items())


def test_run_route_renders_plan_correlated_trace_score_worlds_and_raw_artifact(
    tmp_path,
):
    run_id = "complete-run"
    path = _write(tmp_path, _artifact(run_id, trace=_trace(run_id)))
    original = path.read_bytes()
    client = TestClient(create_app(artifacts_dir=tmp_path))

    response = client.get(f"/runs/{run_id}")
    assert response.status_code == 200
    page = response.text
    assert "Current or final plan" in page
    assert "Resolve the request" in page
    assert "completed" in page
    assert page.count("correlation <code>call-1</code>") == 2
    assert "tool error" in page
    assert "Finished safely" in page
    assert "Partial credit" in page and "1.000" in page
    assert "example_assertion" in page
    assert "before" in page and "after" in page
    assert "No world-change provenance is inferred" in page
    assert f'href="/runs/{run_id}/artifact.json"' in page
    assert "&lt;script id=&quot;injected&quot;&gt;" in page
    assert '<script id="injected">' not in page
    assert "x" * 500 in page

    raw = client.get(f"/runs/{run_id}/artifact.json")
    assert raw.status_code == 200
    assert raw.content == original
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("run_id", "status", "reason", "available", "expected"),
    [
        ("partial", "stopped", "partial", True, "partial"),
        ("blocked", "stopped", "blocked", True, "blocked"),
        ("failed", "failed", "runtime_error", True, "runtime exploded"),
        ("cancelled", "stopped", "cancelled", True, "cancelled"),
        ("unscored", "completed", "goal_completed", False, "scorer offline"),
    ],
)
def test_terminal_and_scorer_unavailable_states_render(
    tmp_path, run_id, status, reason, available, expected
):
    _write(
        tmp_path,
        _artifact(
            run_id,
            status=status,
            termination_reason=reason,
            final_response=None,
            available=available,
            evaluation_error="scorer offline" if not available else None,
            assertion_evidence_available=available,
            score={"partial_credit": 0.25, "task_completed_correctly": 0.0} if available else None,
        ),
    )
    response = TestClient(create_app(artifacts_dir=tmp_path)).get(f"/runs/{run_id}")
    assert response.status_code == 200
    assert expected in response.text
    if not available:
        assert "Unavailable" in response.text


def test_missing_score_fields_are_not_invented(tmp_path):
    _write(tmp_path, _artifact("missing-score", score={}))
    page = TestClient(create_app(artifacts_dir=tmp_path)).get("/runs/missing-score").text
    assert "Partial credit" in page
    assert "Strict completion" in page
    assert page.count("unavailable") >= 2


def test_historical_and_malformed_artifacts_are_unavailable_without_rewrite(tmp_path):
    legacy = tmp_path / "legacy-evaluation.json"
    legacy.write_text(
        json.dumps(
            {
                "artifact_type": "agent_evaluation_run",
                "schema_version": 1,
                "run_id": "legacy-run",
                "task_id": TASK_ID,
                "configuration": {
                    "identity": "legacy-config",
                    "model": "legacy-model",
                    "harness_version": "legacy/v1",
                    "prompt_version": "legacy-prompts/v1",
                    "evaluation_protocol_version": "legacy-panel/v1",
                    "execution_limits": {"calls": 1},
                },
                "repetition": 1,
                "timing": {
                    "started_at": "2026-07-16T12:00:00+00:00",
                    "finished_at": "2026-07-16T12:01:00+00:00",
                    "duration_ms": 60000,
                },
                "status": "completed",
                "termination_reason": "goal_completed",
                "trace": [],
                "usage": {"total_tokens": 10},
                "worlds": {"initial": {}, "final": {}},
                "official_score": {
                    "partial_credit": 1.0,
                    "task_completed_correctly": 1.0,
                },
                "assertion_evidence": [],
                "evaluation_available": True,
            }
        ),
        encoding="utf-8",
    )
    malformed = tmp_path / "malformed-run.json"
    malformed.write_text("{not-json", encoding="utf-8")
    original = {path: path.read_bytes() for path in (legacy, malformed)}
    client = TestClient(create_app(artifacts_dir=tmp_path))

    historical = client.get("/runs/legacy-run")
    assert historical.status_code == 422
    assert "malformed or unsupported" in historical.text
    unavailable = client.get("/runs/malformed-run")
    assert unavailable.status_code == 422
    assert "malformed or unsupported" in unavailable.text
    assert client.get("/runs/unknown-run").status_code == 404
    assert client.post("/api/sessions", json={"task_id": TASK_ID}).status_code == 404
    assert client.get("/api/runtimes").status_code == 404
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "legacy-evaluation.json",
        "malformed-run.json",
    ]
    assert all(path.read_bytes() == payload for path, payload in original.items())


def test_cli_artifact_printed_route_opens_in_viewer(tmp_path, capsys):
    class CliRuntime:
        async def run(self, request, **_):
            return RuntimeOutcome(
                status=ExitStatus.COMPLETED,
                task_id=request.task_id,
                run_id="cli-viewer-run",
                events=(),
                final_response="Created by the CLI.",
                world_state={"source": "cli"},
                score={
                    "partial_credit": 1.0,
                    "task_completed_correctly": 1.0,
                    "assertions": [],
                },
                usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                termination_reason=TerminationReason.GOAL_COMPLETED,
            )

    single_run_main(
        [
            "--task-id",
            TASK_ID,
            "--artifacts-dir",
            str(tmp_path),
            "--viewer-base-url",
            "http://testserver",
        ],
        runtime_factory=CliRuntime,
    )
    output = capsys.readouterr().out
    assert "viewer: http://testserver/runs/cli-viewer-run" in output
    response = TestClient(create_app(artifacts_dir=tmp_path)).get("/runs/cli-viewer-run")
    assert response.status_code == 200
    assert "Created by the CLI" in response.text


@contextmanager
def _live_server(app):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        thread.join(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_keyboard_accessible_bookmarkable_route_and_html_escaping(tmp_path):
    run_id = "browser-run"
    _write(tmp_path, _artifact(run_id, trace=_trace(run_id)))
    with _live_server(create_app(artifacts_dir=tmp_path)) as base_url:
        with sync_playwright() as playwright:
            launch = {"headless": True}
            if CHROME.exists():
                launch["executable_path"] = str(CHROME)
            browser = playwright.chromium.launch(**launch)
            page = browser.new_page()
            page.goto(base_url)
            expect(page.get_by_role("heading", name="Recent runs")).to_be_visible()
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.tagName") == "A"
            page.get_by_role("link", name="Unsafe", exact=False).click()
            expect(page).to_have_url(f"{base_url}/runs/{run_id}")
            expect(page.get_by_role("heading", name="Chronological trace")).to_be_visible()
            assert page.locator("script#injected").count() == 0
            assert page.locator("main").count() == 1
            browser.close()
