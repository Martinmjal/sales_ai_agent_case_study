import pytest

from mock_agent.runtime_support import BudgetExhausted, RunBudget


def test_run_budget_atomically_owns_turn_tool_revision_and_no_progress_limits():
    now = [100.0]
    budget = RunBudget(
        max_model_turns=2,
        max_tool_calls=3,
        max_plan_revisions=1,
        deadline_seconds=10,
        max_consecutive_no_progress_turns=2,
        clock=lambda: now[0],
    )

    budget.claim_model_turn()
    budget.claim_model_turn()
    with pytest.raises(BudgetExhausted, match="model_turns"):
        budget.claim_model_turn()

    budget.claim_tool_calls(2)
    with pytest.raises(BudgetExhausted, match="tool_calls"):
        budget.claim_tool_calls(2)
    assert budget.tool_calls == 2

    budget.claim_plan_revision()
    with pytest.raises(BudgetExhausted, match="plan_revisions"):
        budget.claim_plan_revision()

    assert budget.record_turn(progress=False) == "continue"
    assert budget.record_turn(progress=False) == "warn"
    assert budget.record_turn(progress=False) == "finalize"
    assert budget.record_turn(progress=True) == "continue"

    budget.claim_finalization()
    with pytest.raises(BudgetExhausted, match="finalization_calls"):
        budget.claim_finalization()

    now[0] = 111.0
    with pytest.raises(BudgetExhausted, match="deadline"):
        budget.check_deadline()
