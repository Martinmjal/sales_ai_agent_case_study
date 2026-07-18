# Sales agent runtime

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

Set `LIBRA_BASE_URL` plus `LIBRA_INTERVIEW_API_KEY` in the repository-root `.env`. The dedicated
key keeps Libra authentication separate from
AutomationBench tools that may interpret `OPENAI_API_KEY` as a public OpenAI credential.

## Run

```bash
uv run sales-agent run
```

Optional flags are `--task-id`, `--model`, `--output`, `--artifacts-dir`, and
`--viewer-base-url`. The default task is `sales.zoom_calendar_conflict`; new runs use the shared
typed `RunArtifact` serializer, default to `results/runs/<run-id>.json`, and print both their
artifact path and stable viewer URL.

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
without reviewer calls, retry loops, or per-step finalization. The browser viewer is deliberately
read-only; this CLI and the evaluator are the execution surfaces.

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
uv run sales-agent evaluate \
  --manifest evaluation/manifest.json \
  --config evaluation/config.json \
  --repetitions 10 \
  --artifacts-dir results/evaluation/plan-state-v1
```

The evaluator runs sequentially with a fresh runtime/world for every attempt. Agent-caused
failures remain scorable. An infrastructure-invalid attempt can be replaced at most twice for a
configuration/task/repetition, so the third consecutive infrastructure failure exhausts the
policy. Recovery writes exactly one scorable observation and records the actual replacement count.
Exhaustion writes the final failed attempt as an unscorable canonical diagnostic and exits
non-zero; a later command still retries that missing scorable triple. Rerunning skips only
completed scorable pairs. Every persisted execution is already a complete viewer artifact; the
viewer reads it from `results/evaluation` without a copied session file.

Final reports require the expected manifest, frozen configuration, and repetition count. With no
filters, this command succeeds only when every expected triple is present exactly once:

```bash
uv run sales-agent report \
  --manifest evaluation/manifest.json \
  --config evaluation/config.json \
  --repetitions 10 \
  --artifacts-dir results/evaluation/plan-state-v1 \
  --markdown results/evaluation/plan-state-v1/report.md \
  --json results/evaluation/plan-state-v1/report.json
```

The current corpus does not contain the full ten-task preregistered panel. Regenerate its
checked-in, owner-selected five-task analysis only in explicit exploratory mode:

```bash
uv run sales-agent report \
  --manifest evaluation/manifest.json \
  --config evaluation/config.planner-executor-v2.json \
  --repetitions 10 \
  --artifacts-dir results/evaluation \
  --markdown results/evaluation/report.md \
  --json results/evaluation/report.json \
  --exploratory \
  --task-id sales.contract_renewal_coordinator \
  --task-id sales.event_to_opportunity_pipeline \
  --task-id sales.full_sales_cycle_orchestrator \
  --task-id sales.cross_platform_account_health_score \
  --task-id sales.demo_scheduling
```

Reports include configuration-wide panel statistics and per-task sample sizes, strict completion,
partial-credit variation, efficiency, termination evidence, and links to every persisted run.
`--task-id` is accepted only with `--exploratory`; exploratory Markdown and JSON are labeled
incomplete and disclose the manifest, filters, exclusions, and missing observations. Final mode
rejects missing, duplicate, out-of-range, unexpected-task, and mixed-configuration observations.
The checked-in exploratory report covers the owner-selected first five tasks (50 runs); all 61
completed traces remain available, including later observations excluded from that aggregate.

The evaluator is split by responsibility under `sales_agent/evaluation/`: `cli.py` parses and
dispatches commands, `runner.py` performs sequential fresh-state execution, `records.py` owns the
typed manifest/configuration and canonical-artifact index, and `report.py` validates coverage and
renders byte-stable outputs. No module defines another persisted run format or UI projection.
The historical report uses `config.planner-executor-v2.json`, the exact configuration snapshot
whose canonical hash matches those artifacts. The current plan-state `config.json` derives a
different identity, preventing incompatible observations from being combined. The `.example.json`
inputs remain a one-task development template.

The canonical contract, authoritative locations, unsupported input behavior, and atomic write-once
guarantees are documented in [`../docs/run-artifacts.md`](../docs/run-artifacts.md).
