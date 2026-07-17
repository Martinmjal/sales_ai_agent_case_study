# Mock Agent

A framework-free planner-executor and minimal comparison baseline for the AutomationBench Sales
dataset.

The runtime exposes the `AgentRuntime` contract, keeps benchmark identity, assertions, expected
values, raw world state, and scoring behind a blind adapter, and sends only prompt messages,
public tool schemas, observed tool results, accepted evidence, and execution budgets to the model.
It uses the OpenAI Responses API directly.

`PlannerExecutorRuntime` provides structured planning, review, retry, and replanning. The smaller
`BaselineRuntime` is a direct model/tool loop with no plan events; both implement the same
`AgentRuntime` request, event, cancellation, and outcome contract without LangChain or LangGraph.

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

## Offline evaluation

Copy and freeze the example inputs before a panel run. The manifest contains only canonical task
IDs; evaluator metadata stays outside the runtime request and model context.

```bash
cp evaluation/config.example.json evaluation/config.json
cp evaluation/manifest.example.json evaluation/manifest.json
uv run mock-agent-eval run \
  --manifest evaluation/manifest.json \
  --config evaluation/config.json \
  --repetitions 10 \
  --artifacts-dir results/evaluation
```

The evaluator runs sequentially with a fresh runtime/world for every attempt. Each agent
observation is written immediately, agent failures remain scorable, exhausted transient endpoint
attempts are replaced, and rerunning the same command skips completed configuration/task/repetition
pairs.

Generate byte-stable Markdown and JSON reports offline:

```bash
uv run mock-agent-eval report \
  --artifacts-dir results/evaluation \
  --markdown results/evaluation/report.md \
  --json results/evaluation/report.json
```

The checked-in manifest is a development example, not a claim that its task is held out. Replace
it with the owner-preregistered Sales panel before the final evaluation.
