# Agent UI

Local evaluator workspace for selecting and running any of the 100 registered AutomationBench
sales tasks. FastAPI owns each execution as a background task and writes one self-contained JSON
artifact to the repository-root `sessions/` directory.

Running sessions expose a reconnectable SSE stream at `/api/sessions/{session_id}/events`.
The JSON artifact is the durable source of truth: clients load it first, then resume the stream
after its latest sequence with `Last-Event-ID` or the `after` query parameter.

## Set up

The mock agent uses the same `LIBRA_BASE_URL` and `LIBRA_INTERVIEW_API_KEY` configuration described
in `../mock-agent/README.md`. From this directory:

```bash
uv sync
```

## Run

```bash
uv run agent-ui
```

Open `http://127.0.0.1:8000`. The configured model, maximum steps, and agent version are frozen into
each session and displayed in the interface. They remain server-side settings; optional overrides
are `AGENT_MODEL`, `AGENT_MAX_STEPS`, and `AGENT_VERSION`.

## Verify

```bash
uv run pytest
```

The API tests use scripted runtimes and temporary session directories. They require no model API
key and do not modify committed session artifacts.
