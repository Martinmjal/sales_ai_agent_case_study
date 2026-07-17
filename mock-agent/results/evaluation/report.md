# Offline Evaluation Report

## Configuration

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

- Model: `gpt-5.6-sol`
- Harness: `planner-executor/0.3.0`
- Prompts: `planner-executor-prompts/v2`
- Protocol: `sales-panel/v1`
- Execution limits: `{"executor_tool_turns_per_attempt":4,"logical_model_calls":30,"plan_steps":6,"provider_retries":2,"replans":1,"reserved_outcome_calls_per_saturated_attempt":1,"step_retries":1}`

## Coverage

| Configuration | Task | Scorable | Repetitions |
| --- | --- | ---: | --- |
| `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` | `sales.contract_renewal_coordinator` | 10 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` | `sales.cross_platform_account_health_score` | 10 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` | `sales.demo_scheduling` | 10 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` | `sales.event_to_opportunity_pipeline` | 10 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` | `sales.full_sales_cycle_orchestrator` | 10 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |

## Panel Summary

| Configuration | Tasks | Scorable | Strict | Partial mean | Token median | Duration median (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` | 5 | 50 | 4/50 (8.000%) | 0.295 | 124028.5 | 251361.595 |

## Per-task Results

### `sales.contract_renewal_coordinator` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

- Strict completion: 0/10 (0.000%).
- Partial credit: mean 0.087, sample SD 0.236, range 0.0–0.75.
- Tokens: median 146748.0, range 123609–184732.
- Duration (ms): median 293766.82200000004, range 145932.256–380652.741.
- Model turns: median 17.0, maximum 27.
- Tool calls: median 61.0, maximum 84.
- Runs containing tool errors: 10.

### `sales.cross_platform_account_health_score` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

- Strict completion: 0/10 (0.000%).
- Partial credit: mean 0.150, sample SD 0.324, range 0.0–0.9.
- Tokens: median 104342.5, range 59637–217058.
- Duration (ms): median 198262.782, range 117918.766–517770.334.
- Model turns: median 13.0, maximum 29.
- Tool calls: median 44.5, maximum 92.
- Runs containing tool errors: 10.

### `sales.demo_scheduling` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

- Strict completion: 0/10 (0.000%).
- Partial credit: mean 0.000, sample SD 0.000, range 0.0–0.0.
- Tokens: median 61572.0, range 6988–173776.
- Duration (ms): median 162968.6845, range 23286.454–376629.447.
- Model turns: median 13.0, maximum 20.
- Tool calls: median 23.0, maximum 50.
- Runs containing tool errors: 8.

### `sales.event_to_opportunity_pipeline` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

- Strict completion: 1/10 (10.000%).
- Partial credit: mean 0.850, sample SD 0.143, range 0.5–1.0.
- Tokens: median 112585.5, range 85647–152034.
- Duration (ms): median 226984.39, range 124396.431–518289.606.
- Model turns: median 23.0, maximum 29.
- Tool calls: median 20.0, maximum 28.
- Runs containing tool errors: 0.

### `sales.full_sales_cycle_orchestrator` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

- Strict completion: 3/10 (30.000%).
- Partial credit: mean 0.388, sample SD 0.502, range 0.0–1.0.
- Tokens: median 156335.0, range 94486–209884.
- Duration (ms): median 263483.1945, range 122744.545–376414.777.
- Model turns: median 19.0, maximum 30.
- Tool calls: median 24.0, maximum 49.
- Runs containing tool errors: 9.

## Termination Evidence

- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.contract_renewal_coordinator` — `budget_exhausted`: 9, `goal_completed`: 1.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.cross_platform_account_health_score` — `budget_exhausted`: 8, `goal_completed`: 2.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.demo_scheduling` — `budget_exhausted`: 8, `model_protocol_error`: 2.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.event_to_opportunity_pipeline` — `budget_exhausted`: 1, `goal_completed`: 9.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.full_sales_cycle_orchestrator` — `budget_exhausted`: 7, `goal_completed`: 3.

## Run Artifacts

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.contract_renewal_coordinator`

- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r001.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r002.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r003.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r004.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r005.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r006.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r007.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r008.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r009.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.cross_platform_account_health_score`

- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r001.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r002.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r003.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r004.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r005.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r006.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r007.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r008.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r009.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.demo_scheduling`

- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r001.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r002.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r003.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r004.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r005.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r006.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r007.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r008.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r009.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.event_to_opportunity_pipeline`

- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r001.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r002.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r003.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r004.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r005.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r006.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r007.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r008.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r009.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.full_sales_cycle_orchestrator`

- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r001.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r002.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r003.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r004.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r005.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r006.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r007.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r008.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r009.json)
- [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r010.json)
