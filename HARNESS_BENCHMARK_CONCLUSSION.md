# Harness Benchmark Conclusion

## Resume

The `plan-state/1.0.0` harness beates its previous measured version, `planner-executor/0.3.0`.

Across the same five tasks, using the same `gpt-5.6-sol` model and 10 scorable repetitions per task:

- Strict success increased from **4/50 to 18/50** (**8% to 36%**).
- Mean partial credit increased from **0.295 to 0.681**.
- Median duration decreased slightly from **251 seconds to 234 seconds**.
- Median token consumption increased from approximately **124,000 to 397,000 tokens**, or about **3.2 times**.
- Runs terminating as `goal_completed` increased from **15 to 38**.
- The previous harness had 33 budget-exhausted runs; the current harness had none, although 12 runs terminated as partial.

The refactor made the agent more capable of carrying workflows through to useful completion. The clearest example is demo scheduling, which went from never succeeding to succeeding in eight of ten runs.

The improvement has a significant computational cost. The current agent generally uses more model turns, tool calls, and especially tokens. This version is considerably more effective, but less token-efficient.

## Per-task results

| Task | Previous strict | Current strict | Previous partial | Current partial | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| Demo scheduling | 0% | **80%** | 0.000 | **0.917** | Largest improvement; transformed from nonfunctional to reliable |
| Event pipeline | 10% | **60%** | 0.850 | **0.860** | Major strict improvement; partial performance was already strong |
| Full sales cycle | 30% | **40%** | 0.388 | **0.775** | Moderate strict gain and large improvement in completeness |
| Contract renewal | 0% | 0% | 0.087 | **0.692** | Much more useful work, but still never completely correct |
| Account health | 0% | 0% | 0.150 | 0.160 | Essentially unchanged and still the weakest task |
| **Overall** | **8%** | **36%** | **0.295** | **0.681** | Substantial capability improvement with higher token cost |

No task's mean score regressed:

- Demo scheduling accounts for much of the strict-success increase.
- Event pipeline and full sales cycle improved convincingly.
- Contract renewal improved greatly in partial completion but remained at zero strict successes.
- Account health showed almost no material movement.

## Remaining weaknesses

The weakest current benchmark result is `sales.cross_platform_account_health_score`:

- **0/10 strict successes**
- **0.160 mean partial credit**
- Eight of ten runs terminated as partial
- A median of 65.5 tool calls, close to the execution limit

This pattern indicates that the agent struggles to coordinate the task's cross-platform data gathering and complete every required assertion within the available execution capacity.

Contract renewal is the other important weakness. Its mean partial score rose from 0.087 to 0.692, but it remained at 0/10 strict success. The agent often completed most of the workflow while missing at least one required state change or making invalid Salesforce or evidence calls.

The two non-strict demo runs were also attributable to agent behavior:

- One created a meeting without the exact required title format and waiting-room setting.
- One declined to create the meeting because scheduling details were absent, even though the task permitted reasonable assumptions.

These outcomes were not caused by hidden harness contracts or malformed inputs or outputs.

## Harness diagnosis

The experiment uncovered one genuine harness defect. Benchmark tools could return nested exception objects that the artifact writer could not serialize, causing persistence to crash after an otherwise valid run. The writer now serializes nested exceptions as structured `{type, message}` JSON, and a regression test covers this contract. The completed panel exercised that fix extensively, persisting 66 nested `ValueError` occurrences successfully.

After that fix, the traces showed no evidence that malformed inputs, unexpected output formatting, hidden contracts, or incorrect scoring caused the remaining task failures. Tool and plan rejections generally corresponded to explicitly documented constraints, including invalid SOQL, duplicate evidence identifiers, incompatible evidence tools, and cross-step evidence references.

Nine Azure provider-rate-limit attempts were retained as unscorable infrastructure diagnostics. They were excluded from statistics, and every expected task repetition ultimately received a valid scorable observation. They therefore did not lower the benchmark result.

No additional harness changes are recommended on the basis of the remaining task failures.

## Final benchmark verdict

**The current harness improved substantially.**

Its strict completion rate increased by 28 percentage points, and the number of strict successes increased 4.5 times. Mean partial credit increased by 0.386. No individual task regressed in either strict success rate or mean partial credit.

The strongest improvement was demo scheduling, which increased from 0% to 80% strict success. The weakest current task remains cross-platform account health, at 0% strict success and 0.160 mean partial credit.

The principal regression is efficiency rather than capability: median token consumption increased approximately 3.2 times, tool usage increased, and more runs contained recoverable tool errors. Despite that cost, median wall-clock duration improved slightly.

On capability grounds, `plan-state/1.0.0` should replace `planner-executor/0.3.0` as the benchmarked harness. Account health and contract renewal remain unresolved benchmark weaknesses, while token efficiency is the primary trade-off to track in future versions.

This comparison is based on 10 repetitions for each of five tasks and provides strong directional evidence, but it is not a high-powered statistical study. It compares the current harness specifically against the retained `planner-executor/0.3.0` benchmark; there is not enough retained evidence to rank it rigorously against other unreported historical versions.

## Artifacts

- Current report: [`results/evaluation/plan-state-v1-five-task/report.md`](results/evaluation/plan-state-v1-five-task/report.md)
- Current machine-readable report: [`results/evaluation/plan-state-v1-five-task/report.json`](results/evaluation/plan-state-v1-five-task/report.json)
- Historical five-task manifest: [`evaluation/manifest.historical-five-task.json`](evaluation/manifest.historical-five-task.json)
- Previous measured report: [`results/evaluation/report.md`](results/evaluation/report.md)
