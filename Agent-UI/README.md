# Agent UI

Local evaluator workspace for selecting and running any of the 100 registered AutomationBench
sales tasks. FastAPI owns each execution as a background task and writes one self-contained JSON
`RunArtifact` to `mock-agent/results/runs/`. It also reads evaluation observations directly from
`mock-agent/results/evaluation/`; no copied session database exists.

Running sessions expose a reconnectable SSE stream at `/api/sessions/{session_id}/events`.
The JSON artifact is the durable source of truth: clients load it first, then resume the stream
after its latest sequence with `Last-Event-ID` or the `after` query parameter.

The top-right agent picker exposes the sole submission **Custom agent**, backed by the plan-state
runtime. The no-plan baseline remains evaluation-only. The server freezes the runtime ID, label,
and version into the artifact before execution. The picker is disabled while a session is active.

Architecture-neutral `plan_created`, `step_started`, `step_completed`, `step_failed`,
`step_superseded`, `plan_revised`, and completion events reduce into one structured plan in the
center workspace. Historical review, retry, and replan events remain supported, and replaced work
stays visible as completed, failed, or superseded history. The
same reducer rebuilds the final plan solely from a historical artifact; runtimes without plan
events display `No structured plan`.

The history drawer searches durable sessions by task name or canonical task ID, groups them in
the browser's local timezone, and keeps the active run available while terminal history is viewed.
Terminal artifacts are immutable once their final status is persisted; malformed and unsupported
artifacts are ignored when history is materialized. A direct URL of the form
`http://127.0.0.1:8000/?run_id=<stable-run-id>` opens canonical single-run or evaluation history.

The active Running session exposes one Stop control. A stop request sets the runtime cancellation
signal and remains in progress until the runtime reaches its next safe model or completed
tool-batch boundary. Stopped and failed runs retain their available trace, world, evaluation, and
error evidence. On server startup, any persisted Running artifact without a live owner is marked
Interrupted and is never resumed or replayed automatically. Stopped, Failed, and Interrupted
artifacts are terminal and immutable, and missing evaluation data is displayed as unavailable.

The right inspector is the primary explanation of an execution. It preserves the session's full
problem prompt and tool definitions, then renders assistant turns as a vertical causal spine.
Calls sharing an assistant-turn parent are presented as parallel siblings, with each result or
error reconnected by correlation ID. Compact disclosures retain arguments, results, errors,
durations, and long structured values without duplicating tool evidence in the center workspace.
The final response or terminal execution outcome closes the trace with an accessible state.

The same inspector exposes deterministic evaluation evidence separately from the final response.
Its sticky summary distinguishes partial credit from strict benchmark completion and includes
lifecycle, duration, and available token usage. Assertion disclosures follow the official scorer's
passed, failed, explicitly excluded, and pre-satisfied exclusion semantics. Human-readable world
changes sit alongside collapsed initial and final snapshots and the complete read-only session
JSON. Missing evidence is labeled unavailable; provider-visible reasoning summaries and reasoning
token counts appear only when the durable artifact contains them.

The shell keeps all three columns visible on wide screens, reduces history to an expandable rail
on medium screens, and exposes history and evaluation as focus-managed drawers on narrow screens.
On desktop, the session history and evaluator inspector have draggable separators with keyboard
arrow controls. Pane widths stay within workspace-safe bounds and are remembered in the browser.
The frontend is served as local HTML, CSS, and JavaScript with no CDN or build-time dependency.

## Set up

The application uses the mock agent's Libra-compatible model endpoint. Put these required values
in either the repository-root `.env` or `mock-agent/.env`:

```dotenv
LIBRA_INTERVIEW_API_KEY=replace-with-your-libra-api-key
LIBRA_BASE_URL=https://replace-with-your-libra-endpoint.example/api/projects/replace-with-project/openai/v1
```

Use the dedicated Libra variable; `OPENAI_API_KEY` is reserved for tools that intentionally call
the public OpenAI API. Then, from this directory:

```bash
uv sync
uv run playwright install chromium
```

The browser install is optional when Google Chrome is already installed in its standard macOS
location.

## Run

```bash
uv run agent-ui
```

Open `http://127.0.0.1:8000`. The configured model, maximum steps, selected runtime, and runtime
version are frozen into each session and displayed in the interface. Model and budget remain
server-side settings; optional overrides are `AGENT_MODEL`, `AGENT_MAX_MODEL_TURNS`, and
`AGENT_VERSION` (the custom runtime version).

The registered runtime is framework-free and executes through the `AgentRuntime` boundary.
Recovery, provider retries, protocol correction, cancellation, budget exhaustion, and completion
are retained as ordered durable events in each canonical run artifact.

## Verify

```bash
uv run pytest
```

The API tests use scripted runtimes and temporary artifact directories. They require no model API
key and do not modify committed run artifacts.
