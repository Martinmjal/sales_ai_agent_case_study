# Offline Evaluation Report — INCOMPLETE EXPLORATORY ANALYSIS

## Report Status

> This output is exploratory and is not a complete final panel.

- Mode: `exploratory`
- Complete: `no`
- Configuration: `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`
- Expected repetitions per selected task: 10
- Applied task filters: `sales.contract_renewal_coordinator`, `sales.event_to_opportunity_pipeline`, `sales.full_sales_cycle_orchestrator`, `sales.cross_platform_account_health_score`, `sales.demo_scheduling`
- Coverage complete: `yes`

## Configuration

```json
{
  "evaluation_protocol_version": "sales-panel/v1",
  "execution_limits": {
    "executor_tool_turns_per_attempt": 4,
    "logical_model_calls": 30,
    "plan_steps": 6,
    "provider_retries": 2,
    "replans": 1,
    "reserved_outcome_calls_per_saturated_attempt": 1,
    "step_retries": 1
  },
  "harness_version": "planner-executor/0.3.0",
  "identity": "a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c",
  "model": "gpt-5.6-sol",
  "prompt_version": "planner-executor-prompts/v2",
  "runtime": {
    "id": "custom",
    "label": "Custom agent",
    "version": "planner-executor/0.3.0"
  }
}
```

## Coverage

```json
{
  "coverage": {
    "coverage_complete": true,
    "excluded_configuration_identities": [],
    "expected_observation_count": 50,
    "missing": [],
    "scorable_observation_count": 50,
    "unexpected_tasks": [],
    "unscorable": []
  },
  "selection": {
    "configuration_identity": "a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c",
    "manifest": {
      "panel_id": "sales-heldout-2026-07-17",
      "preregistered_by": "repository-owner",
      "tasks": [
        "sales.contract_renewal_coordinator",
        "sales.event_to_opportunity_pipeline",
        "sales.full_sales_cycle_orchestrator",
        "sales.cross_platform_account_health_score",
        "sales.demo_scheduling",
        "sales.chatgpt_proposal_customization",
        "sales.docusign_contract_send",
        "sales.sheets_multi_channel_campaign_router",
        "sales.email_zoom_fuzzy",
        "sales.overdue_followup_flag"
      ]
    },
    "repetitions": 10,
    "selected_tasks": [
      "sales.contract_renewal_coordinator",
      "sales.event_to_opportunity_pipeline",
      "sales.full_sales_cycle_orchestrator",
      "sales.cross_platform_account_health_score",
      "sales.demo_scheduling"
    ],
    "task_filters": [
      "sales.contract_renewal_coordinator",
      "sales.event_to_opportunity_pipeline",
      "sales.full_sales_cycle_orchestrator",
      "sales.cross_platform_account_health_score",
      "sales.demo_scheduling"
    ]
  }
}
```

## Panel Summary

```json
[
  {
    "configuration": {
      "evaluation_protocol_version": "sales-panel/v1",
      "execution_limits": {
        "executor_tool_turns_per_attempt": 4,
        "logical_model_calls": 30,
        "plan_steps": 6,
        "provider_retries": 2,
        "replans": 1,
        "reserved_outcome_calls_per_saturated_attempt": 1,
        "step_retries": 1
      },
      "harness_version": "planner-executor/0.3.0",
      "identity": "a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c",
      "model": "gpt-5.6-sol",
      "prompt_version": "planner-executor-prompts/v2",
      "runtime": {
        "id": "custom",
        "label": "Custom agent",
        "version": "planner-executor/0.3.0"
      }
    },
    "coverage": {
      "scorable_count": 50,
      "task_count": 5
    },
    "duration_ms": {
      "maximum": 518289.606,
      "median": 251361.595,
      "minimum": 23286.454
    },
    "model_turns": {
      "maximum": 30,
      "median": 17.0
    },
    "partial_credit": {
      "maximum": 1.0,
      "mean": 0.295,
      "minimum": 0.0,
      "sample_standard_deviation": 0.418
    },
    "runs_containing_tool_errors": 37,
    "strict_completion": {
      "count": 4,
      "percentage": 8.0
    },
    "termination_reasons": {
      "budget_exhausted": 33,
      "goal_completed": 15,
      "model_protocol_error": 2
    },
    "tokens": {
      "maximum": 217058,
      "median": 124028.5,
      "minimum": 6988
    },
    "tool_calls": {
      "maximum": 92,
      "median": 27.5
    }
  }
]
```

## Per-task Results

### `sales.contract_renewal_coordinator` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

```json
{
  "coverage": {
    "repetitions": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10
    ],
    "scorable_count": 10
  },
  "duration_ms": {
    "maximum": 380652.741,
    "median": 293766.82200000004,
    "minimum": 145932.256
  },
  "model_turns": {
    "maximum": 27,
    "median": 17.0
  },
  "partial_credit": {
    "maximum": 0.75,
    "mean": 0.087,
    "minimum": 0.0,
    "sample_standard_deviation": 0.236
  },
  "runs_containing_tool_errors": 10,
  "strict_completion": {
    "count": 0,
    "percentage": 0.0
  },
  "task_id": "sales.contract_renewal_coordinator",
  "termination_reasons": {
    "budget_exhausted": 9,
    "goal_completed": 1
  },
  "tokens": {
    "maximum": 184732,
    "median": 146748.0,
    "minimum": 123609
  },
  "tool_calls": {
    "maximum": 84,
    "median": 61.0
  }
}
```

### `sales.cross_platform_account_health_score` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

```json
{
  "coverage": {
    "repetitions": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10
    ],
    "scorable_count": 10
  },
  "duration_ms": {
    "maximum": 517770.334,
    "median": 198262.782,
    "minimum": 117918.766
  },
  "model_turns": {
    "maximum": 29,
    "median": 13.0
  },
  "partial_credit": {
    "maximum": 0.9,
    "mean": 0.15,
    "minimum": 0.0,
    "sample_standard_deviation": 0.324
  },
  "runs_containing_tool_errors": 10,
  "strict_completion": {
    "count": 0,
    "percentage": 0.0
  },
  "task_id": "sales.cross_platform_account_health_score",
  "termination_reasons": {
    "budget_exhausted": 8,
    "goal_completed": 2
  },
  "tokens": {
    "maximum": 217058,
    "median": 104342.5,
    "minimum": 59637
  },
  "tool_calls": {
    "maximum": 92,
    "median": 44.5
  }
}
```

### `sales.demo_scheduling` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

```json
{
  "coverage": {
    "repetitions": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10
    ],
    "scorable_count": 10
  },
  "duration_ms": {
    "maximum": 376629.447,
    "median": 162968.6845,
    "minimum": 23286.454
  },
  "model_turns": {
    "maximum": 20,
    "median": 13.0
  },
  "partial_credit": {
    "maximum": 0.0,
    "mean": 0.0,
    "minimum": 0.0,
    "sample_standard_deviation": 0.0
  },
  "runs_containing_tool_errors": 8,
  "strict_completion": {
    "count": 0,
    "percentage": 0.0
  },
  "task_id": "sales.demo_scheduling",
  "termination_reasons": {
    "budget_exhausted": 8,
    "model_protocol_error": 2
  },
  "tokens": {
    "maximum": 173776,
    "median": 61572.0,
    "minimum": 6988
  },
  "tool_calls": {
    "maximum": 50,
    "median": 23.0
  }
}
```

### `sales.event_to_opportunity_pipeline` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

```json
{
  "coverage": {
    "repetitions": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10
    ],
    "scorable_count": 10
  },
  "duration_ms": {
    "maximum": 518289.606,
    "median": 226984.39,
    "minimum": 124396.431
  },
  "model_turns": {
    "maximum": 29,
    "median": 23.0
  },
  "partial_credit": {
    "maximum": 1.0,
    "mean": 0.85,
    "minimum": 0.5,
    "sample_standard_deviation": 0.143
  },
  "runs_containing_tool_errors": 0,
  "strict_completion": {
    "count": 1,
    "percentage": 10.0
  },
  "task_id": "sales.event_to_opportunity_pipeline",
  "termination_reasons": {
    "budget_exhausted": 1,
    "goal_completed": 9
  },
  "tokens": {
    "maximum": 152034,
    "median": 112585.5,
    "minimum": 85647
  },
  "tool_calls": {
    "maximum": 28,
    "median": 20.0
  }
}
```

### `sales.full_sales_cycle_orchestrator` — `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c`

```json
{
  "coverage": {
    "repetitions": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10
    ],
    "scorable_count": 10
  },
  "duration_ms": {
    "maximum": 376414.777,
    "median": 263483.1945,
    "minimum": 122744.545
  },
  "model_turns": {
    "maximum": 30,
    "median": 19.0
  },
  "partial_credit": {
    "maximum": 1.0,
    "mean": 0.388,
    "minimum": 0.0,
    "sample_standard_deviation": 0.502
  },
  "runs_containing_tool_errors": 9,
  "strict_completion": {
    "count": 3,
    "percentage": 30.0
  },
  "task_id": "sales.full_sales_cycle_orchestrator",
  "termination_reasons": {
    "budget_exhausted": 7,
    "goal_completed": 3
  },
  "tokens": {
    "maximum": 209884,
    "median": 156335.0,
    "minimum": 94486
  },
  "tool_calls": {
    "maximum": 49,
    "median": 24.0
  }
}
```

## Termination Evidence

- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.contract_renewal_coordinator` — `budget_exhausted`: 9, `goal_completed`: 1.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.cross_platform_account_health_score` — `budget_exhausted`: 8, `goal_completed`: 2.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.demo_scheduling` — `budget_exhausted`: 8, `model_protocol_error`: 2.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.event_to_opportunity_pipeline` — `budget_exhausted`: 1, `goal_completed`: 9.
- `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.full_sales_cycle_orchestrator` — `budget_exhausted`: 7, `goal_completed`: 3.

## Run Artifacts

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.contract_renewal_coordinator`

- [View run](http://127.0.0.1:8000/runs/068c07c0-6bd4-4ebd-962b-bdbfca76d8a6) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r001.json)
- [View run](http://127.0.0.1:8000/runs/be9587cf-a28e-42ec-b79b-65d8017bb9b2) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r002.json)
- [View run](http://127.0.0.1:8000/runs/93b56269-efd0-461c-a5c2-3e6105bc0329) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r003.json)
- [View run](http://127.0.0.1:8000/runs/209d2a5a-aab3-4f1d-ae00-44f72371c20d) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r004.json)
- [View run](http://127.0.0.1:8000/runs/4f1e27e3-1ae6-484f-8604-b91d332eba35) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r005.json)
- [View run](http://127.0.0.1:8000/runs/eab2443d-4763-4e52-90c0-c8863f7e38c7) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r006.json)
- [View run](http://127.0.0.1:8000/runs/b333a1dc-3a82-41ca-89c7-92b0238ce386) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r007.json)
- [View run](http://127.0.0.1:8000/runs/dc0e5cc5-ae67-4e1d-b66e-354b1917d51b) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r008.json)
- [View run](http://127.0.0.1:8000/runs/d371bfc2-3fbd-4fba-a650-c683d83c3673) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r009.json)
- [View run](http://127.0.0.1:8000/runs/3debefd9-a2c1-473f-bef3-1b32c849fae6) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-contract_renewal_coordinator_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.cross_platform_account_health_score`

- [View run](http://127.0.0.1:8000/runs/13dc6635-7d22-47a7-af43-94081c974388) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r001.json)
- [View run](http://127.0.0.1:8000/runs/efc19f73-42ca-4cc6-aae7-68c24d59e38a) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r002.json)
- [View run](http://127.0.0.1:8000/runs/afaa0baf-a70f-4030-8204-91988e81941e) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r003.json)
- [View run](http://127.0.0.1:8000/runs/5cfa1609-bac8-411c-a99c-fe68f261e77f) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r004.json)
- [View run](http://127.0.0.1:8000/runs/5c322b17-6acf-482a-88b5-917b9339c0b3) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r005.json)
- [View run](http://127.0.0.1:8000/runs/b6878982-1e04-4233-a5ac-b7a3b01e9327) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r006.json)
- [View run](http://127.0.0.1:8000/runs/9bde6b88-5019-4d84-87b5-f5a805ec4671) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r007.json)
- [View run](http://127.0.0.1:8000/runs/13bf72df-203e-47b9-9d08-2d75c96cc61a) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r008.json)
- [View run](http://127.0.0.1:8000/runs/eb44e21d-a558-4897-b693-3c6a9e65027a) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r009.json)
- [View run](http://127.0.0.1:8000/runs/6134d655-0f21-490b-8235-bc3fcab3b7f4) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-cross_platform_account_health_score_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.demo_scheduling`

- [View run](http://127.0.0.1:8000/runs/cb345d09-91e9-4b52-98da-9b7b6097dd85) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r001.json)
- [View run](http://127.0.0.1:8000/runs/1926a4b8-bfc8-4d80-885e-9b67677b1346) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r002.json)
- [View run](http://127.0.0.1:8000/runs/d15a5a44-0c66-45a5-915f-c99496a86d2b) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r003.json)
- [View run](http://127.0.0.1:8000/runs/3ce1fd31-353b-4ad2-9186-11b9d0c90821) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r004.json)
- [View run](http://127.0.0.1:8000/runs/0a5e8546-66e0-4609-9bb1-7af94436257f) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r005.json)
- [View run](http://127.0.0.1:8000/runs/6f80eb1c-ba91-417a-a7db-43ce04aa15bc) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r006.json)
- [View run](http://127.0.0.1:8000/runs/8e65ddb1-4516-485b-ac94-c7be203527cf) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r007.json)
- [View run](http://127.0.0.1:8000/runs/a0a51558-c079-4fa7-ad5e-68bc86f349a9) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r008.json)
- [View run](http://127.0.0.1:8000/runs/36eb3cc4-b9ce-4b74-83c2-9d37f238423f) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r009.json)
- [View run](http://127.0.0.1:8000/runs/16c4334a-7c1a-449e-957d-ffa4e2b1e087) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-demo_scheduling_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.event_to_opportunity_pipeline`

- [View run](http://127.0.0.1:8000/runs/961b9719-9aaf-43dc-a96d-e7de88405e8a) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r001.json)
- [View run](http://127.0.0.1:8000/runs/f92f08d8-a9be-4141-8c97-eba2a3cb5bb6) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r002.json)
- [View run](http://127.0.0.1:8000/runs/edbbaa79-f39b-4e59-9864-a1705777af4f) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r003.json)
- [View run](http://127.0.0.1:8000/runs/0737ea7d-7721-495f-8965-d61799933ce7) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r004.json)
- [View run](http://127.0.0.1:8000/runs/ced25b25-ab2c-4baf-a9d3-a633d351b7d8) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r005.json)
- [View run](http://127.0.0.1:8000/runs/1c0c38f1-ad02-4c64-871e-178bc2b4f46d) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r006.json)
- [View run](http://127.0.0.1:8000/runs/c44069be-a8fb-4752-b773-9a885122ce1c) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r007.json)
- [View run](http://127.0.0.1:8000/runs/070e2c87-7f28-4aef-b8a0-cbc38c949f91) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r008.json)
- [View run](http://127.0.0.1:8000/runs/f9ca5bd2-3712-462d-8a01-03f8aae1a177) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r009.json)
- [View run](http://127.0.0.1:8000/runs/53dc92e3-4b38-4172-9938-88f637de8ae1) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-event_to_opportunity_pipeline_r010.json)

### `a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c` / `sales.full_sales_cycle_orchestrator`

- [View run](http://127.0.0.1:8000/runs/ebe4d2e2-6b1c-422e-b477-ac0435addd64) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r001.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r001.json)
- [View run](http://127.0.0.1:8000/runs/92c5970a-4412-4c9c-a2ed-d576ddb189fd) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r002.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r002.json)
- [View run](http://127.0.0.1:8000/runs/c9ada7cf-abb0-417d-89a9-3d41810af588) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r003.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r003.json)
- [View run](http://127.0.0.1:8000/runs/1977f06c-3964-4b38-9845-1d6d328c3569) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r004.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r004.json)
- [View run](http://127.0.0.1:8000/runs/7e3c957a-abfd-499f-b37a-7521224d5393) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r005.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r005.json)
- [View run](http://127.0.0.1:8000/runs/255b56cc-e9b7-43c0-8b93-8a376daf5793) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r006.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r006.json)
- [View run](http://127.0.0.1:8000/runs/ef7f6d3c-808b-4765-b9ea-bc28c3f93631) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r007.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r007.json)
- [View run](http://127.0.0.1:8000/runs/98b450a5-7a43-4912-afe2-230a9abf5823) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r008.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r008.json)
- [View run](http://127.0.0.1:8000/runs/62dd45a2-77ec-4df5-8241-bbbd98f25599) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r009.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r009.json)
- [View run](http://127.0.0.1:8000/runs/2503418d-d30c-474c-ac5c-d14f52b76918) · [a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r010.json](a596d592316e3fc98ff5fb79f351c8075a68f798809eba416c7a8f0cfef5453c_sales-full_sales_cycle_orchestrator_r010.json)
