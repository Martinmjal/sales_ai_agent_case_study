# Mock Agent

A framework-free planner-executor for the AutomationBench Sales dataset.

The runtime exposes the `AgentRuntime` contract, keeps benchmark identity, assertions, expected
values, raw world state, and scoring behind a blind adapter, and sends only prompt messages,
public tool schemas, observed tool results, accepted evidence, and execution budgets to the model.
It uses the OpenAI Responses API directly.

## Set up

```bash
uv sync
cp .env.example .env
```

Set `LIBRA_BASE_URL` plus `LIBRA_INTERVIEW_API_KEY` (or `OPENAI_API_KEY`) in either
`mock-agent/.env` or the repository-root `.env`.

## Run

```bash
uv run mock-agent
```

Optional flags are `--task-id`, `--model`, and `--output`. The default task is
`sales.zoom_calendar_conflict`; the result contains the full runtime trace, official score,
usage, final response, termination reason, and final simulated world.

## Runtime behavior

Plans contain at most six steps. Each step attempt receives four executor turns, one rejected
step may be retried, one plan may be replaced, and a run receives at most 24 logical model calls.
Accepted transcripts become structured evidence; failed attempts retain structured side-effect
records. Provider retries, protocol correction, tool errors, cancellation, budget exhaustion,
and completion are emitted as correlated events and return scorable outcomes.

## Verify

```bash
uv run pytest
```

The scripted suite drives the public runtime seam with real AutomationBench tools and official
scoring. It requires no model API key.
