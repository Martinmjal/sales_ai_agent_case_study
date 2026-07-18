from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from sales_agent import __version__
from sales_agent.artifacts import RunArtifact
from sales_agent.config import REPOSITORY_ROOT
from sales_agent.viewer.store import (
    ArtifactReference,
    ArtifactRepository,
    RunNotFoundError,
    UnsupportedRunError,
)

STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


def create_app(
    *,
    artifacts_dir: Path | None = None,
    read_directories: Iterable[Path] | None = None,
) -> FastAPI:
    if artifacts_dir is not None and read_directories is not None:
        raise ValueError("Pass artifacts_dir or read_directories, not both")
    if read_directories is None:
        results = REPOSITORY_ROOT / "results"
        read_directories = (artifacts_dir,) if artifacts_dir else (results,)
    repository = ArtifactRepository(read_directories)
    app = FastAPI(title="Run Artifact Trace Viewer", version=__version__)
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")

    @app.get("/", include_in_schema=False)
    async def recent_runs(run_id: str | None = None):
        if run_id:
            return RedirectResponse(f"/runs/{quote(run_id, safe='')}", status_code=307)
        return _html(_recent_page(repository.recent()))

    @app.get("/runs/{run_id}/artifact.json", include_in_schema=False)
    async def raw_artifact(run_id: str):
        try:
            reference = repository.get(run_id)
        except RunNotFoundError as error:
            return _error_page(404, "Run not found", str(error))
        except UnsupportedRunError as error:
            return _error_page(422, "Run unavailable", str(error))
        return FileResponse(reference.path, media_type="application/json")

    @app.get("/runs/{run_id}", include_in_schema=False)
    async def run_view(run_id: str):
        try:
            reference = repository.get(run_id)
        except RunNotFoundError as error:
            return _error_page(404, "Run not found", str(error))
        except UnsupportedRunError as error:
            return _error_page(422, "Run unavailable", str(error))
        return _html(_run_page(reference))

    return app


def _html(body: str, *, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        body,
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; style-src 'self'; object-src 'none'",
        },
    )


def _shell(content: str, *, title: str, refresh: bool = False) -> str:
    refresh_tag = '<meta http-equiv="refresh" content="2">' if refresh else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh_tag}
  <title>{escape(title)} · Run trace viewer</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="/">Run trace viewer</a>
    <span>Canonical artifacts · read only</span>
  </header>
  <main id="main-content">{content}</main>
</body>
</html>"""


def _recent_page(references: list[ArtifactReference]) -> str:
    rows = []
    for reference in references:
        artifact = reference.artifact
        score = artifact.evaluation.official_score if artifact.evaluation.available else {}
        partial = _score(score.get("partial_credit"))
        strict = _strict_score(score.get("task_completed_correctly"))
        task_name = artifact.task.get("name") or artifact.task["task_id"]
        rows.append(
            f"""<li class="run-row">
  <a href="/runs/{quote(artifact.run_id, safe="")}">
    <span class="run-task">{escape(str(task_name))}</span>
    <code>{escape(artifact.task["task_id"])}</code>
    <span class="run-meta"><time datetime="{escape(reference.timestamp)}">{escape(reference.timestamp)}</time>
      · <strong>{escape(artifact.status)}</strong> · partial {partial} · strict {strict}</span>
  </a>
</li>"""
        )
    items = "".join(rows) or '<li class="empty">No supported run artifacts found.</li>'
    return _shell(
        f"""<section aria-labelledby="recent-title">
  <p class="eyebrow">Artifact store</p>
  <h1 id="recent-title">Recent runs</h1>
  <p>Newest first. Open a run to inspect its immutable trace and evaluation evidence.</p>
  <nav aria-label="Recent runs"><ol class="run-list">{items}</ol></nav>
</section>""",
        title="Recent runs",
    )


def _run_page(reference: ArtifactReference) -> str:
    artifact = reference.artifact
    plan = _plan_from_trace(artifact.trace)
    prompt = _prompt_html(artifact.task.get("prompt"))
    score = _score_html(artifact)
    assertions = _assertions_html(artifact)
    trace = "".join(_event_html(event) for event in artifact.trace)
    trace = trace or '<p class="empty">No trace events were recorded.</p>'
    final = _final_html(artifact)
    config = artifact.configuration
    runtime = config.get("runtime") or {}
    active = artifact.status == "running"
    source_kind = (
        "Canonical RunArtifact" if reference.canonical else "Supported historical artifact"
    )
    content = f"""
<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Recent runs</a><span>/</span><span>{escape(artifact.run_id)}</span></nav>
<article>
  <header class="run-header">
    <div><p class="eyebrow">{escape(artifact.task["task_id"])}</p><h1>{escape(str(artifact.task.get("name") or artifact.task["task_id"]))}</h1></div>
    <span class="status status-{escape(artifact.status)}">{escape(artifact.status)}</span>
  </header>
  <section class="card" aria-labelledby="identity-title"><h2 id="identity-title">Task and run</h2>
    <dl class="facts">
      {_fact("Run ID", artifact.run_id)}{_fact("Started", artifact.timing.started_at)}
      {_fact("Termination", artifact.termination_reason or "Not terminal")}
      {_fact("Model", config.get("model"))}{_fact("Runtime", runtime.get("label") or runtime.get("id"))}
      {_fact("Harness", config.get("harness_version"))}{_fact("Prompt version", config.get("prompt_version"))}
    </dl>{prompt}
  </section>
  {_plan_html(plan)}
  <section class="card" aria-labelledby="trace-title"><h2 id="trace-title">Chronological trace</h2>
    <p>Tool calls, results, and errors expose their shared correlation ID. No world-change provenance is inferred.</p>
    <ol class="trace">{trace}</ol>
  </section>
  {final}
  <section class="card" aria-labelledby="score-title"><h2 id="score-title">Official score</h2>{score}{assertions}</section>
  <section class="card" aria-labelledby="world-title"><h2 id="world-title">Initial and final worlds</h2>
    <p>Raw snapshots are disclosed side by side without tool-to-change attribution.</p>
    <div class="worlds"><div><h3>Initial</h3>{_structured(artifact.worlds.initial)}</div><div><h3>Final</h3>{_structured(artifact.worlds.final, unavailable="Unavailable")}</div></div>
  </section>
  <section class="card raw-link" aria-labelledby="raw-title"><h2 id="raw-title">Source artifact</h2>
    <a href="/runs/{quote(artifact.run_id, safe="")}/artifact.json">Open raw artifact</a>
    <span>{escape(source_kind)} · {escape(str(reference.path))}</span>
  </section>
</article>"""
    return _shell(content, title=str(artifact.task.get("name") or artifact.run_id), refresh=active)


def _plan_from_trace(trace: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    plan: dict[str, Any] | None = None
    states: dict[str, str] = {}
    transitions = {
        "step_started": "active",
        "step_completed": "completed",
        "step_failed": "failed",
        "step_superseded": "superseded",
    }
    for event in trace:
        event_content = event.get("content")
        content: dict[str, Any] = event_content if isinstance(event_content, dict) else {}
        if event.get("kind") in {"plan_created", "plan_revised", "replan"}:
            plan_state = content.get("plan_state")
            candidate: dict[str, Any] = plan_state if isinstance(plan_state, dict) else content
            if isinstance(candidate.get("steps"), list):
                plan = candidate
                states = {
                    str(step.get("id")): str(step.get("status") or "pending")
                    for step in candidate["steps"]
                    if isinstance(step, dict) and step.get("id")
                }
        state = transitions.get(str(event.get("kind")))
        if state:
            step_id = content.get("id") or content.get("step_id") or event.get("correlation_id")
            if step_id:
                states[str(step_id)] = state
    if plan is not None:
        plan = {**plan, "step_states": states}
    return plan


def _plan_html(plan: dict[str, Any] | None) -> str:
    if plan is None:
        return '<section class="card" aria-labelledby="plan-title"><h2 id="plan-title">Plan</h2><p class="empty">No structured plan was recorded.</p></section>'
    states = plan.get("step_states") or {}
    steps = []
    for step in plan.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or "step")
        state = str(states.get(step_id) or step.get("status") or "pending")
        steps.append(
            f'<li><span class="step-state state-{escape(state)}">{escape(state)}</span><strong>{escape(step_id)}</strong><p>{escape(str(step.get("objective") or "No objective disclosed"))}</p></li>'
        )
    goal = plan.get("goal")
    if isinstance(goal, dict):
        goal = goal.get("objective") or goal.get("description") or goal.get("id")
    return f'<section class="card" aria-labelledby="plan-title"><h2 id="plan-title">Current or final plan</h2><p>{escape(str(goal or "No goal disclosed"))}</p><ol class="plan">{"".join(steps)}</ol></section>'


def _event_html(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "event")
    correlation = event.get("correlation_id")
    details = []
    for label, key in (
        ("Content", "content"),
        ("Arguments", "arguments"),
        ("Result", "result"),
        ("Error", "error"),
        ("Usage", "usage"),
        ("Metadata", "metadata"),
    ):
        value = event.get(key)
        if value not in (None, {}, []):
            details.append(f"<dt>{label}</dt><dd>{_structured(value)}</dd>")
    if event.get("duration_ms") is not None:
        details.append(f"<dt>Duration</dt><dd>{escape(str(event['duration_ms']))} ms</dd>")
    relation = []
    if correlation:
        relation.append(f"correlation <code>{escape(str(correlation))}</code>")
    if event.get("parent_id"):
        relation.append(f"parent <code>{escape(str(event['parent_id']))}</code>")
    if event.get("name"):
        relation.append(f"name <code>{escape(str(event['name']))}</code>")
    return f"""<li class="event kind-{escape(kind)}" data-correlation="{escape(str(correlation or ""))}">
  <header><span class="sequence">#{escape(str(event.get("sequence", "?")))}</span><strong>{escape(kind.replace("_", " "))}</strong><time datetime="{escape(str(event.get("timestamp") or ""))}">{escape(str(event.get("timestamp") or ""))}</time></header>
  <p class="relations">{" · ".join(relation) or "No correlation metadata"}</p><dl>{"".join(details)}</dl>
</li>"""


def _prompt_html(value: Any) -> str:
    messages = value if isinstance(value, list) else [value]
    rows = []
    for message in messages:
        if isinstance(message, dict):
            role, content = message.get("role", "message"), message.get("content")
        else:
            role, content = "message", message
        rows.append(
            f'<div class="prompt"><strong>{escape(str(role))}</strong>{_structured(content)}</div>'
        )
    return '<div class="prompts"><h3>Prompt</h3>' + "".join(rows) + "</div>"


def _final_html(artifact: RunArtifact) -> str:
    if artifact.final_response is not None:
        body = _structured(artifact.final_response)
    else:
        outcome = {
            "status": artifact.status,
            "termination_reason": artifact.termination_reason,
            "terminal_error": artifact.terminal_error,
        }
        body = _structured(outcome)
    return f'<section class="card" aria-labelledby="outcome-title"><h2 id="outcome-title">Final response or terminal outcome</h2>{body}</section>'


def _score_html(artifact: RunArtifact) -> str:
    evaluation = artifact.evaluation
    if not evaluation.available:
        reason = artifact.evaluation_error or "The scorer did not provide evidence."
        return f'<p class="unavailable"><strong>Unavailable.</strong> {escape(reason)}</p>'
    score = evaluation.official_score
    return f'<dl class="facts">{_fact("Partial credit", _score(score.get("partial_credit")))}{_fact("Strict completion", _strict_score(score.get("task_completed_correctly")))}</dl>'


def _assertions_html(artifact: RunArtifact) -> str:
    evaluation = artifact.evaluation
    if not evaluation.assertion_evidence_available:
        return '<h3>Assertions</h3><p class="unavailable">Assertion evidence unavailable.</p>'
    if not evaluation.assertion_evidence:
        return '<h3>Assertions</h3><p class="empty">No assertion evidence recorded.</p>'
    rows = []
    for assertion in evaluation.assertion_evidence:
        passed = assertion.get("passed") if isinstance(assertion, dict) else None
        label = "passed" if passed is True else "failed" if passed is False else "not disclosed"
        rows.append(f"<li><strong>{escape(label)}</strong>{_structured(assertion)}</li>")
    return '<h3>Assertions</h3><ol class="assertions">' + "".join(rows) + "</ol>"


def _structured(value: Any, *, unavailable: str = "None") -> str:
    if value is None:
        return f'<p class="unavailable">{escape(unavailable)}</p>'
    if isinstance(value, str):
        return f"<pre>{escape(value)}</pre>"
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, default=str)
    return f"<pre>{escape(payload)}</pre>"


def _fact(label: str, value: Any) -> str:
    shown = "Unavailable" if value is None else str(value)
    return f"<div><dt>{escape(label)}</dt><dd>{escape(shown)}</dd></div>"


def _score(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else "unavailable"


def _strict_score(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "unavailable"
    return "yes" if value == 1.0 else "no"


def _error_page(status_code: int, title: str, detail: str) -> HTMLResponse:
    content = f'<section class="error"><p class="eyebrow">{status_code}</p><h1>{escape(title)}</h1><p>{escape(detail)}</p><a href="/">Return to recent runs</a></section>'
    return _html(_shell(content, title=title), status_code=status_code)
