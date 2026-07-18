# Mock Agent

A framework-free plan-state agent and evaluation-only comparison baseline for the AutomationBench
Sales dataset.

The runtime exposes the `AgentRuntime` contract, keeps benchmark identity, assertions, expected
values, raw world state, and scoring behind a blind adapter, and sends only prompt messages,
public tool schemas, observed tool results, accepted evidence, and execution budgets to the model.
It uses the OpenAI Responses API directly.

`PlanStateRuntime` is the sole submission runtime. It uses one continuous execution loop and local
evidence-backed control actions. The smaller `BaselineRuntime` is a direct model/tool loop kept for
evaluation comparisons only. Both implement the same `AgentRuntime` request, event, cancellation,
and outcome contract without LangChain or LangGraph.

## Set up

```bash
uv sync
cp .env.example .env
```

Set `LIBRA_BASE_URL` plus `LIBRA_INTERVIEW_API_KEY` in either `mock-agent/.env` or
the repository-root `.env`. The dedicated key keeps Libra authentication separate from
AutomationBench tools that may interpret `OPENAI_API_KEY` as a public OpenAI credential.

## Run

```bash
uv run mock-agent
```

Optional flags are `--task-id`, `--model`, and `--output`. The default task is
`sales.zoom_calendar_conflict`; the result contains the full runtime trace, official score,
usage, final response, termination reason, and final simulated world.

## Runtime behavior

The planner receives only the task prompt and declared public tools. It creates the smallest
cohesive plan (at most six steps), and every evidence requirement must name declared source tools.
The executor then uses one continuous loop. Each turn contains either a sequential batch of
business calls or one harness control: `complete_step`, `revise_plan`, or `finish`.

Typed transitions preserve completed steps, accepted evidence, and the successful call ledger.
Plan revision explicitly fails or supersedes the active step and replaces only remaining work.
One run-level budget owns model turns, tool calls, plan revisions, the deadline, no-progress
detection, and a single tools-disabled partial/blocked finalizer. Provider retries are separately
limited to two and remain visible in the trace.

The frozen limits are recorded in the first trace event and in evaluation configuration. Tool
payloads that report `success: false` or a non-null top-level `error` become correlated
`TOOL_ERROR` events while retaining the raw payload. Accepted transcripts become structured
evidence; failed writes and reads remain distinguishable from successful side effects. Provider
retries, protocol correction, cancellation, budget exhaustion, and completion are also emitted as
correlated events and return scorable outcomes.

## Plan-state controls

`PlanStateRuntime` makes one tool-disabled structured planning call, activates the first step, and
then exposes business tools plus three harness controls to one model loop.
`complete_step` must cite the current plan revision and map every requirement ID to a factual claim
and a compatible successful call made for that step. `finish(outcome="completed")` is accepted only
after all required steps are complete and carries the final response.

Business calls execute through the same validating dispatcher and in the same emitted order as the
default runtime. A turn that mixes business and control calls executes nothing and returns a
structured correction observation. Stale revisions, unknown steps, failed or invented calls, and
incompatible evidence remain recoverable observations. The runtime emits `plan_created`,
`step_started`, `step_completed`, `step_failed`, `step_superseded`, `plan_revised`, and `completion`
without reviewer calls, retry loops, or per-step finalization. The Agent UI registers it as the
single **Custom agent** submission runtime.

## Verify

```bash
uv run pytest
```

The scripted suite drives the public runtime seam with real AutomationBench tools and official
scoring. It requires no model API key.

## Offline evaluation

The final owner-preregistered panel and frozen configuration are checked in as
`evaluation/manifest.json` and `evaluation/config.json`. Evaluator metadata stays outside the
runtime request and model context.

```bash
uv run mock-agent-eval run \
  --manifest evaluation/manifest.json \
  --config evaluation/config.json \
  --repetitions 10 \
  --artifacts-dir results/evaluation \
  --sessions-dir ../sessions
```

The evaluator runs sequentially with a fresh runtime/world for every attempt. Each agent
observation is written immediately, agent failures remain scorable, exhausted transient endpoint
attempts are replaced, and rerunning the same command skips completed configuration/task/repetition
pairs. Each scorable execution also becomes a complete Agent-UI history artifact; a missing UI
copy is reconstructed from its evaluation artifact during resumption without another model call.

Generate byte-stable Markdown and JSON reports offline:

```bash
uv run mock-agent-eval report \
  --artifacts-dir results/evaluation \
  --markdown results/evaluation/report.md \
  --json results/evaluation/report.json \
  --task-id sales.contract_renewal_coordinator \
  --task-id sales.event_to_opportunity_pipeline \
  --task-id sales.full_sales_cycle_orchestrator \
  --task-id sales.cross_platform_account_health_score \
  --task-id sales.demo_scheduling
```

Reports include configuration-wide panel statistics and per-task sample sizes, strict completion,
partial-credit variation, efficiency, termination evidence, and links to every persisted run.
Repeated `--task-id` options select a reproducible subset without deleting observations. The
checked-in final report covers the owner-selected first five tasks (50 runs); all 61 completed
traces remain available, including the later observations excluded from that aggregate. The
`.example.json` inputs remain available as a one-task development template.
