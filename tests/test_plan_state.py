import pytest
from pydantic import ValidationError

from sales_agent.plan_state import (
    ActiveStepDisposition,
    CompleteStep,
    EvidenceClaim,
    Finish,
    PlanDraft,
    PlanRevision,
    PlanStateError,
    SuccessfulToolCall,
    activate_next_step,
    complete_step,
    create_plan_state,
    finish,
    record_successful_tool_call,
    revise_plan,
)

DECLARED_TOOLS = {"lookup_policy", "list_meetings", "update_meeting"}


def draft(*, steps=None):
    return PlanDraft.model_validate(
        {
            "goal": {"id": "goal-resolve", "objective": "Resolve the conflict."},
            "steps": steps
            or [
                {
                    "id": "inspect",
                    "objective": "Inspect the meeting policy.",
                    "required_evidence": [
                        {
                            "id": "policy-found",
                            "requirement": "The applicable priority policy",
                            "source_tools": ["lookup_policy"],
                        }
                    ],
                },
                {
                    "id": "resolve",
                    "objective": "Update the lower-priority meeting.",
                    "required_evidence": [
                        {
                            "id": "meeting-updated",
                            "requirement": "The updated meeting record",
                            "source_tools": ["update_meeting"],
                        }
                    ],
                },
            ],
        }
    )


def error_code(callable_):
    with pytest.raises(PlanStateError) as caught:
        callable_()
    return caught.value.code


def test_plan_state_transitions_activate_and_complete_ordered_steps():
    state = create_plan_state(draft(), declared_tools=DECLARED_TOOLS)

    assert state.revision == 1
    assert [step.state for step in state.steps] == ["pending", "pending"]

    state = activate_next_step(state)
    state = record_successful_tool_call(
        state,
        SuccessfulToolCall(
            call_id="policy-call",
            step_id="inspect",
            tool_name="lookup_policy",
        ),
    )
    state = complete_step(
        state,
        CompleteStep(
            plan_revision=state.revision,
            step_id="inspect",
            summary="The executive meeting has priority.",
            evidence=(
                EvidenceClaim(
                    requirement_id="policy-found",
                    fact="Executive sessions outrank product reviews.",
                    source_call_id="policy-call",
                ),
            ),
        ),
    )

    assert state.active_step_id is None
    assert [step.state for step in state.steps] == ["completed", "pending"]
    assert state.accepted_evidence[0].step_id == "inspect"
    assert state.accepted_evidence[0].source_call_id == "policy-call"

    state = activate_next_step(state)

    assert state.active_step_id == "resolve"
    assert [step.state for step in state.steps] == ["completed", "active"]


def test_plan_revision_replaces_remaining_work_without_losing_completed_evidence_or_side_effects():
    state = activate_next_step(create_plan_state(draft(), declared_tools=DECLARED_TOOLS))
    state = record_successful_tool_call(
        state,
        SuccessfulToolCall(
            call_id="policy-call",
            step_id="inspect",
            tool_name="lookup_policy",
            arguments={"sheet": "priority"},
            result={"priority": "executive"},
            side_effect=False,
        ),
    )
    state = complete_step(
        state,
        CompleteStep(
            plan_revision=state.revision,
            step_id="inspect",
            summary="The priority policy was verified.",
            evidence=(
                EvidenceClaim(
                    requirement_id="policy-found",
                    fact="Executive meetings have priority.",
                    source_call_id="policy-call",
                ),
            ),
        ),
    )
    state = activate_next_step(state)
    state = record_successful_tool_call(
        state,
        SuccessfulToolCall(
            call_id="update-call",
            step_id="resolve",
            tool_name="update_meeting",
            arguments={"meeting_id": "review"},
            result={"updated": True},
            side_effect=True,
        ),
    )
    before_evidence = state.accepted_evidence
    before_calls = state.successful_tool_calls

    revised = revise_plan(
        state,
        PlanRevision(
            plan_revision=state.revision,
            invalidation_reason="The update revealed a second calendar record.",
            active_step_disposition=ActiveStepDisposition.SUPERSEDED,
            replacement_steps=(
                {
                    "id": "reconcile-calendar",
                    "objective": "Reconcile the discovered calendar record.",
                    "required_evidence": (
                        {
                            "id": "calendar-reconciled",
                            "requirement": "The reconciled calendar record",
                            "source_tools": ("update_meeting",),
                        },
                    ),
                },
            ),
        ),
        declared_tools=DECLARED_TOOLS,
    )

    assert revised.revision == state.revision + 1
    assert [(step.id, step.state) for step in revised.steps] == [
        ("inspect", "completed"),
        ("resolve", "superseded"),
        ("reconcile-calendar", "pending"),
    ]
    assert revised.active_step_id is None
    assert revised.accepted_evidence == before_evidence
    assert revised.successful_tool_calls == before_calls
    assert revised.successful_tool_calls[-1].side_effect is True


def test_plan_revision_rejects_stale_reused_undeclared_and_oversized_replacements():
    state = activate_next_step(create_plan_state(draft(), declared_tools=DECLARED_TOOLS))

    def revision(**overrides):
        values = {
            "plan_revision": state.revision,
            "invalidation_reason": "Discovery invalidated remaining work.",
            "active_step_disposition": "failed",
            "replacement_steps": [
                {
                    "id": "replacement",
                    "objective": "Use a valid replacement.",
                    "required_evidence": [
                        {
                            "id": "replacement-evidence",
                            "requirement": "Replacement evidence",
                            "source_tools": ["list_meetings"],
                        }
                    ],
                }
            ],
        }
        values.update(overrides)
        return PlanRevision.model_validate(values)

    assert (
        error_code(
            lambda: revise_plan(
                state,
                revision(plan_revision=1),
                declared_tools=DECLARED_TOOLS,
            )
        )
        == "stale_plan_revision"
    )
    reused = revision(
        replacement_steps=[
            {
                "id": "inspect",
                "objective": "Attempt to replace an existing step.",
                "required_evidence": [
                    {
                        "id": "fresh-evidence",
                        "requirement": "Fresh evidence",
                        "source_tools": ["list_meetings"],
                    }
                ],
            }
        ]
    )
    assert (
        error_code(
            lambda: revise_plan(
                state,
                reused,
                declared_tools=DECLARED_TOOLS,
            )
        )
        == "duplicate_plan_identifier"
    )
    undeclared = revision(
        replacement_steps=[
            {
                "id": "undeclared",
                "objective": "Use an undeclared source.",
                "required_evidence": [
                    {
                        "id": "undeclared-evidence",
                        "requirement": "Undeclared evidence",
                        "source_tools": ["invented_tool"],
                    }
                ],
            }
        ]
    )
    assert (
        error_code(
            lambda: revise_plan(
                state,
                undeclared,
                declared_tools=DECLARED_TOOLS,
            )
        )
        == "undeclared_evidence_source"
    )
    with pytest.raises(ValidationError):
        revision(
            replacement_steps=[
                {
                    "id": f"replacement-{index}",
                    "objective": "Replacement work.",
                    "required_evidence": [
                        {
                            "id": f"evidence-{index}",
                            "requirement": "Evidence",
                            "source_tools": ["list_meetings"],
                        }
                    ],
                }
                for index in range(7)
            ]
        )


def test_plan_creation_rejects_invalid_identifiers_content_and_sources():
    duplicate_ids = {
        "goal": {"id": "shared", "objective": "Resolve the conflict."},
        "steps": [
            {
                "id": "shared",
                "objective": "Inspect the conflict.",
                "required_evidence": [
                    {
                        "id": "evidence",
                        "requirement": "A meeting record",
                        "source_tools": ["list_meetings"],
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(duplicate_ids)

    blank_objective = {
        **duplicate_ids,
        "goal": {"id": "goal", "objective": "   "},
        "steps": [{**duplicate_ids["steps"][0], "id": "step"}],
    }
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(blank_objective)

    undeclared = draft(
        steps=[
            {
                "id": "inspect",
                "objective": "Inspect the meeting.",
                "required_evidence": [
                    {
                        "id": "meeting-found",
                        "requirement": "A meeting record",
                        "source_tools": ["invented_tool"],
                    }
                ],
            }
        ]
    )
    assert (
        error_code(lambda: create_plan_state(undeclared, declared_tools=DECLARED_TOOLS))
        == "undeclared_evidence_source"
    )


def test_complete_step_rejects_stale_unknown_and_unproven_control_actions():
    state = activate_next_step(create_plan_state(draft(), declared_tools=DECLARED_TOOLS))
    state = record_successful_tool_call(
        state,
        SuccessfulToolCall(
            call_id="meeting-call",
            step_id="inspect",
            tool_name="list_meetings",
        ),
    )

    def action(**overrides):
        values = {
            "plan_revision": state.revision,
            "step_id": "inspect",
            "summary": "Inspected the policy.",
            "evidence": [
                {
                    "requirement_id": "policy-found",
                    "fact": "The policy was found.",
                    "source_call_id": "meeting-call",
                }
            ],
        }
        values.update(overrides)
        return CompleteStep.model_validate(values)

    assert (
        error_code(lambda: complete_step(state, action(plan_revision=1))) == "stale_plan_revision"
    )
    assert error_code(lambda: complete_step(state, action(step_id="missing"))) == "unknown_step"
    assert (
        error_code(
            lambda: complete_step(
                state,
                action(
                    evidence=[
                        {
                            "requirement_id": "policy-found",
                            "fact": "Invented evidence.",
                            "source_call_id": "invented-call",
                        }
                    ]
                ),
            )
        )
        == "unknown_or_unsuccessful_source_call"
    )
    assert error_code(lambda: complete_step(state, action())) == "incompatible_source_tool"


def test_complete_step_rejects_calls_from_an_unrelated_step():
    state = activate_next_step(create_plan_state(draft(), declared_tools=DECLARED_TOOLS))
    state = record_successful_tool_call(
        state,
        SuccessfulToolCall(
            call_id="policy-call",
            step_id="inspect",
            tool_name="lookup_policy",
        ),
    )
    state = complete_step(
        state,
        CompleteStep.model_validate(
            {
                "plan_revision": state.revision,
                "step_id": "inspect",
                "summary": "The policy was inspected.",
                "evidence": [
                    {
                        "requirement_id": "policy-found",
                        "fact": "Executive meetings have priority.",
                        "source_call_id": "policy-call",
                    }
                ],
            }
        ),
    )
    state = activate_next_step(state)

    unrelated = CompleteStep.model_validate(
        {
            "plan_revision": state.revision,
            "step_id": "resolve",
            "summary": "Claimed an update.",
            "evidence": [
                {
                    "requirement_id": "meeting-updated",
                    "fact": "The meeting was updated.",
                    "source_call_id": "policy-call",
                }
            ],
        }
    )

    assert error_code(lambda: complete_step(state, unrelated)) == "source_call_not_visible"


def test_finish_requires_every_step_and_a_final_response():
    state = activate_next_step(create_plan_state(draft(), declared_tools=DECLARED_TOOLS))

    assert (
        error_code(
            lambda: finish(
                state,
                Finish(outcome="completed", final_response="Conflict resolved."),
            )
        )
        == "incomplete_plan"
    )
    with pytest.raises(ValidationError):
        Finish(outcome="completed", final_response="   ")
