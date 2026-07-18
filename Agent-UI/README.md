# Run trace viewer

This application is a small, read-only viewer over the repository's canonical `RunArtifact`
files. It does not run agents, select runtimes, cancel work, stream events, recover execution
owners, or maintain a session database. The CLI and evaluator own execution; the artifact store is
the viewer's only source of truth.

The landing page derives a newest-first list directly from `mock-agent/results/`. Each row shows
the task, artifact timestamp, terminal status, partial score, and strict score, and links to the
bookmarkable `/runs/{run-id}` route. A run page shows:

- the task prompt, run ID, and runtime/configuration summary;
- the current or final plan reconstructed from architecture-neutral trace events;
- the chronological trace with tool call/result/error correlation IDs;
- the final response or explicit terminal outcome;
- official partial/strict scores and assertion evidence when available;
- raw initial and final worlds without inferred tool provenance; and
- a link to the exact source artifact.

Supported historical files are normalized in memory through the mock agent's versioned reader and
are never copied or rewritten. Malformed files are omitted from recent runs; a direct request for a
malformed or unsupported run returns a clear unavailable page. Running canonical snapshots use a
simple two-second page refresh. There is no SSE or reconnect state.

## Set up and run

```bash
uv sync
uv run agent-ui
```

Open <http://127.0.0.1:8000>. No model credentials are needed because the viewer cannot execute an
agent. Create a new artifact with the mock-agent CLI and follow the printed `/runs/{run-id}` URL.

Playwright is used only by the keyboard/accessibility browser smoke test. Install Chromium if a
local Google Chrome installation is unavailable:

```bash
uv run playwright install chromium
```

## Verify

```bash
uv run pytest
```

The focused tests cover recent ordering, stable routes, terminal and scorer-unavailable states,
plan/trace correlation, historical compatibility, malformed inputs, HTML escaping, long values,
keyboard access, and the invariant that viewer requests never mutate artifact files.
