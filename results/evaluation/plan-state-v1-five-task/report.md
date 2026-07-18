# Offline Evaluation Report

## Report Status

- Mode: `final`
- Complete: `yes`
- Configuration: `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b`
- Expected repetitions per selected task: 10
- Applied task filters: none
- Coverage complete: `yes`

## Configuration

```json
{
  "evaluation_protocol_version": "sales-panel/v1",
  "execution_limits": {
    "deadline_seconds": 300,
    "max_consecutive_no_progress_turns": 3,
    "max_model_turns": 30,
    "max_plan_revisions": 3,
    "max_tool_calls": 64,
    "plan_steps": 6,
    "provider_retries": 2,
    "reserved_finalization_calls": 1
  },
  "harness_version": "plan-state/1.0.0",
  "identity": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b",
  "model": "gpt-5.6-sol",
  "prompt_version": "plan-state-prompts/v1",
  "runtime": {
    "id": "custom",
    "label": "Custom agent",
    "version": "plan-state/1.0.0"
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
    "unscorable": [
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r009_infrastructure_f187af0c7206fc61.json",
        "repetition": 9,
        "task_id": "sales.cross_platform_account_health_score"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r001_infrastructure_16be187a8aa3af2d.json",
        "repetition": 1,
        "task_id": "sales.demo_scheduling"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r004_infrastructure_5381b1d3329bfa53.json",
        "repetition": 4,
        "task_id": "sales.demo_scheduling"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r005_infrastructure_47521f1281682c89.json",
        "repetition": 5,
        "task_id": "sales.demo_scheduling"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r005_infrastructure_57dea205b6674a2c.json",
        "repetition": 5,
        "task_id": "sales.demo_scheduling"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r007_infrastructure_7242f7f8986e0922.json",
        "repetition": 7,
        "task_id": "sales.demo_scheduling"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r009_infrastructure_151ff8bc6cbd119c.json",
        "repetition": 9,
        "task_id": "sales.demo_scheduling"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r009_infrastructure_74d54a1f5d56a1ad.json",
        "repetition": 9,
        "task_id": "sales.demo_scheduling"
      },
      {
        "artifact": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r010_infrastructure_5a499cae526cf22c.json",
        "repetition": 10,
        "task_id": "sales.demo_scheduling"
      }
    ]
  },
  "selection": {
    "configuration_identity": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b",
    "manifest": {
      "panel_id": "sales-historical-five-task-replay-2026-07-18",
      "preregistered_by": "repository-owner-historical-report-scope",
      "tasks": [
        "sales.contract_renewal_coordinator",
        "sales.event_to_opportunity_pipeline",
        "sales.full_sales_cycle_orchestrator",
        "sales.cross_platform_account_health_score",
        "sales.demo_scheduling"
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
    "task_filters": []
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
        "deadline_seconds": 300,
        "max_consecutive_no_progress_turns": 3,
        "max_model_turns": 30,
        "max_plan_revisions": 3,
        "max_tool_calls": 64,
        "plan_steps": 6,
        "provider_retries": 2,
        "reserved_finalization_calls": 1
      },
      "harness_version": "plan-state/1.0.0",
      "identity": "59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b",
      "model": "gpt-5.6-sol",
      "prompt_version": "plan-state-prompts/v1",
      "runtime": {
        "id": "custom",
        "label": "Custom agent",
        "version": "plan-state/1.0.0"
      }
    },
    "coverage": {
      "scorable_count": 50,
      "task_count": 5
    },
    "duration_ms": {
      "maximum": 419551.991,
      "median": 233914.069,
      "minimum": 84639.82
    },
    "model_turns": {
      "maximum": 25,
      "median": 18.5
    },
    "partial_credit": {
      "maximum": 1.0,
      "mean": 0.681,
      "minimum": 0.0,
      "sample_standard_deviation": 0.351
    },
    "runs_containing_tool_errors": 46,
    "strict_completion": {
      "count": 18,
      "percentage": 36.0
    },
    "termination_reasons": {
      "goal_completed": 38,
      "partial": 12
    },
    "tokens": {
      "maximum": 645112,
      "median": 397471.5,
      "minimum": 67442
    },
    "tool_calls": {
      "maximum": 68,
      "median": 36.5
    }
  }
]
```

## Per-task Results

### `sales.contract_renewal_coordinator` — `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b`

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
    "maximum": 324681.745,
    "median": 274975.821,
    "minimum": 221806.856
  },
  "model_turns": {
    "maximum": 22,
    "median": 19.5
  },
  "partial_credit": {
    "maximum": 0.75,
    "mean": 0.692,
    "minimum": 0.25,
    "sample_standard_deviation": 0.157
  },
  "runs_containing_tool_errors": 10,
  "strict_completion": {
    "count": 0,
    "percentage": 0.0
  },
  "task_id": "sales.contract_renewal_coordinator",
  "termination_reasons": {
    "goal_completed": 8,
    "partial": 2
  },
  "tokens": {
    "maximum": 643812,
    "median": 451210.0,
    "minimum": 377863
  },
  "tool_calls": {
    "maximum": 54,
    "median": 44.5
  }
}
```

### `sales.cross_platform_account_health_score` — `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b`

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
    "maximum": 419551.991,
    "median": 246458.894,
    "minimum": 84639.82
  },
  "model_turns": {
    "maximum": 21,
    "median": 13.5
  },
  "partial_credit": {
    "maximum": 0.6,
    "mean": 0.16,
    "minimum": 0.0,
    "sample_standard_deviation": 0.222
  },
  "runs_containing_tool_errors": 10,
  "strict_completion": {
    "count": 0,
    "percentage": 0.0
  },
  "task_id": "sales.cross_platform_account_health_score",
  "termination_reasons": {
    "goal_completed": 2,
    "partial": 8
  },
  "tokens": {
    "maximum": 645112,
    "median": 499792.5,
    "minimum": 67442
  },
  "tool_calls": {
    "maximum": 68,
    "median": 65.5
  }
}
```

### `sales.demo_scheduling` — `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b`

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
    "maximum": 290470.36,
    "median": 214737.335,
    "minimum": 106826.357
  },
  "model_turns": {
    "maximum": 23,
    "median": 18.0
  },
  "partial_credit": {
    "maximum": 1.0,
    "mean": 0.917,
    "minimum": 0.5,
    "sample_standard_deviation": 0.18
  },
  "runs_containing_tool_errors": 10,
  "strict_completion": {
    "count": 8,
    "percentage": 80.0
  },
  "task_id": "sales.demo_scheduling",
  "termination_reasons": {
    "goal_completed": 10
  },
  "tokens": {
    "maximum": 536516,
    "median": 406600.5,
    "minimum": 175539
  },
  "tool_calls": {
    "maximum": 52,
    "median": 38.5
  }
}
```

### `sales.event_to_opportunity_pipeline` — `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b`

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
    "maximum": 319075.918,
    "median": 194449.092,
    "minimum": 143217.933
  },
  "model_turns": {
    "maximum": 24,
    "median": 20.5
  },
  "partial_credit": {
    "maximum": 1.0,
    "mean": 0.86,
    "minimum": 0.0,
    "sample_standard_deviation": 0.31
  },
  "runs_containing_tool_errors": 8,
  "strict_completion": {
    "count": 6,
    "percentage": 60.0
  },
  "task_id": "sales.event_to_opportunity_pipeline",
  "termination_reasons": {
    "goal_completed": 8,
    "partial": 2
  },
  "tokens": {
    "maximum": 307471,
    "median": 224384.5,
    "minimum": 72456
  },
  "tool_calls": {
    "maximum": 34,
    "median": 28.5
  }
}
```

### `sales.full_sales_cycle_orchestrator` — `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b`

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
    "maximum": 293431.237,
    "median": 202720.7915,
    "minimum": 142558.139
  },
  "model_turns": {
    "maximum": 25,
    "median": 18.0
  },
  "partial_credit": {
    "maximum": 1.0,
    "mean": 0.775,
    "minimum": 0.5,
    "sample_standard_deviation": 0.242
  },
  "runs_containing_tool_errors": 8,
  "strict_completion": {
    "count": 4,
    "percentage": 40.0
  },
  "task_id": "sales.full_sales_cycle_orchestrator",
  "termination_reasons": {
    "goal_completed": 10
  },
  "tokens": {
    "maximum": 579876,
    "median": 359131.5,
    "minimum": 222375
  },
  "tool_calls": {
    "maximum": 39,
    "median": 27.0
  }
}
```

## Termination Evidence

- `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.contract_renewal_coordinator` — `goal_completed`: 8, `partial`: 2.
- `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.cross_platform_account_health_score` — `goal_completed`: 2, `partial`: 8.
- `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.demo_scheduling` — `goal_completed`: 10.
- `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.event_to_opportunity_pipeline` — `goal_completed`: 8, `partial`: 2.
- `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.full_sales_cycle_orchestrator` — `goal_completed`: 10.

## Run Artifacts

### `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.contract_renewal_coordinator`

- [View run](http://127.0.0.1:8000/runs/7d05a027-171a-41b9-82f1-952fbe68edc3) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r001.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r001.json)
- [View run](http://127.0.0.1:8000/runs/eb3e3b42-dc1f-474a-b3bd-b2da342046da) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r002.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r002.json)
- [View run](http://127.0.0.1:8000/runs/08e3714d-0dfa-4fb8-af41-3a46bb280036) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r003.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r003.json)
- [View run](http://127.0.0.1:8000/runs/2ae5539e-f822-4dff-ba21-35b5f678dc6d) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r004.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r004.json)
- [View run](http://127.0.0.1:8000/runs/ed1bf1ac-deb1-4d41-84aa-6116625a2f4e) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r005.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r005.json)
- [View run](http://127.0.0.1:8000/runs/e5ebcdf0-1c56-4445-83a0-0ea469febf7f) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r006.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r006.json)
- [View run](http://127.0.0.1:8000/runs/c1c897a1-e7df-4db5-8c5e-d5b3169038b6) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r007.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r007.json)
- [View run](http://127.0.0.1:8000/runs/1539a59a-8463-41dc-956a-1fdcbee5bc1a) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r008.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r008.json)
- [View run](http://127.0.0.1:8000/runs/91fa8e42-670e-44a1-ba5c-bcd4aeddbf95) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r009.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r009.json)
- [View run](http://127.0.0.1:8000/runs/151cf168-19c6-4506-85e5-4e254b574d08) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r010.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-contract_renewal_coordinator_r010.json)

### `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.cross_platform_account_health_score`

- [View run](http://127.0.0.1:8000/runs/722db675-c115-4aa3-a18a-0857e0f29092) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r001.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r001.json)
- [View run](http://127.0.0.1:8000/runs/1086caa3-5e34-4f5d-8229-a605839e9e0e) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r002.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r002.json)
- [View run](http://127.0.0.1:8000/runs/515f5165-9e3d-4734-851b-c1f96b0bb30b) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r003.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r003.json)
- [View run](http://127.0.0.1:8000/runs/99994ef8-53d5-4298-a317-21722efe711b) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r004.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r004.json)
- [View run](http://127.0.0.1:8000/runs/d9eff6f9-b3bb-481b-8847-6a28024f7185) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r005.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r005.json)
- [View run](http://127.0.0.1:8000/runs/633e61ab-c015-4a2a-a7a0-5678a01daca1) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r006.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r006.json)
- [View run](http://127.0.0.1:8000/runs/e7b2c01d-1d16-4776-bfd0-0e7d8274114e) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r007.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r007.json)
- [View run](http://127.0.0.1:8000/runs/eaee306a-71ce-434d-8e49-370fec0af465) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r008.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r008.json)
- [View run](http://127.0.0.1:8000/runs/8a162705-770c-4834-b89e-77a05a325aee) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r009.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r009.json)
- [View run](http://127.0.0.1:8000/runs/99ae3309-e63b-46a6-b63c-9a95d3946ab9) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r010.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-cross_platform_account_health_score_r010.json)

### `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.demo_scheduling`

- [View run](http://127.0.0.1:8000/runs/0ce152e1-c98f-4ac0-b1e2-2a2f07e6d0a5) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r001.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r001.json)
- [View run](http://127.0.0.1:8000/runs/b20ded65-49d3-43da-9f5f-3b5d04a655fa) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r002.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r002.json)
- [View run](http://127.0.0.1:8000/runs/3baa461f-3276-4066-95a7-0572ea65b182) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r003.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r003.json)
- [View run](http://127.0.0.1:8000/runs/550791b2-59ee-42ac-86a9-d888e4d2fd12) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r004.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r004.json)
- [View run](http://127.0.0.1:8000/runs/ab08f531-51fd-491d-b3c6-5be0c7bb5bdf) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r005.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r005.json)
- [View run](http://127.0.0.1:8000/runs/7e1de4c9-7b98-4ae2-b51b-b22da6196eac) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r006.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r006.json)
- [View run](http://127.0.0.1:8000/runs/043e8800-9f94-4cc5-8eb0-3de7b5f37333) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r007.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r007.json)
- [View run](http://127.0.0.1:8000/runs/1f8ba666-4f4a-4bae-94b7-26d3b557c3a6) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r008.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r008.json)
- [View run](http://127.0.0.1:8000/runs/104ff192-1ec3-4f9f-8e1e-263881f792fd) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r009.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r009.json)
- [View run](http://127.0.0.1:8000/runs/7e3ab241-c780-4b97-b9c0-e11f4c28a8c8) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r010.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-demo_scheduling_r010.json)

### `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.event_to_opportunity_pipeline`

- [View run](http://127.0.0.1:8000/runs/a0403db6-d9cf-4746-8941-e8122eb70fc4) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r001.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r001.json)
- [View run](http://127.0.0.1:8000/runs/753b77a8-299a-482d-bae0-6cda7537c7bc) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r002.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r002.json)
- [View run](http://127.0.0.1:8000/runs/0142deed-16ed-4fad-b0f0-eb858ff57d83) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r003.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r003.json)
- [View run](http://127.0.0.1:8000/runs/5bcb00f0-5c33-40d0-bd56-5df7351b4b33) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r004.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r004.json)
- [View run](http://127.0.0.1:8000/runs/636f8626-32ee-4e13-9b9d-ff58d9f363a7) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r005.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r005.json)
- [View run](http://127.0.0.1:8000/runs/e7114b71-a1d8-4a6c-a666-84cd52b26b3b) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r006.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r006.json)
- [View run](http://127.0.0.1:8000/runs/4d3a87f4-006a-4c72-86ca-95c4bc215224) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r007.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r007.json)
- [View run](http://127.0.0.1:8000/runs/ba4e6fc5-95d6-4370-9111-f8fa2f79db66) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r008.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r008.json)
- [View run](http://127.0.0.1:8000/runs/da7eeb34-737d-43b7-ab03-1623ecd280d1) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r009.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r009.json)
- [View run](http://127.0.0.1:8000/runs/331dcf0e-846d-46e0-a700-4414161fe2aa) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r010.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-event_to_opportunity_pipeline_r010.json)

### `59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b` / `sales.full_sales_cycle_orchestrator`

- [View run](http://127.0.0.1:8000/runs/bb70bfd0-8c7f-4c6b-941b-961d60edf070) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r001.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r001.json)
- [View run](http://127.0.0.1:8000/runs/34de13fb-e193-483d-bf62-ae92ccf9238d) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r002.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r002.json)
- [View run](http://127.0.0.1:8000/runs/1f088448-73bc-4e78-b440-821377a5e977) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r003.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r003.json)
- [View run](http://127.0.0.1:8000/runs/60ac3419-bcea-4e4d-a0ca-d4158f525d94) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r004.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r004.json)
- [View run](http://127.0.0.1:8000/runs/5b2b1bca-bc10-4775-be98-007b27960969) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r005.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r005.json)
- [View run](http://127.0.0.1:8000/runs/ae268a47-97c1-4dc3-b7f1-1a784f7f9d2d) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r006.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r006.json)
- [View run](http://127.0.0.1:8000/runs/619129b7-ecf8-411f-80b0-266dff3f49e4) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r007.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r007.json)
- [View run](http://127.0.0.1:8000/runs/7e453596-02f8-4948-8560-0f380d853612) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r008.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r008.json)
- [View run](http://127.0.0.1:8000/runs/b3bd571b-29fb-4903-8b19-240abb72644b) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r009.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r009.json)
- [View run](http://127.0.0.1:8000/runs/e20a518b-11b9-4303-b6c8-7a3aee91cd06) · [59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r010.json](59bce79c02dab639248d03840769762392a67466419877868147a8528e16c89b_sales-full_sales_cycle_orchestrator_r010.json)
