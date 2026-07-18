from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


MAX_PLAN_STEPS = 6
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StepState = Literal["pending", "active", "completed"]


class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Goal(ImmutableModel):
    id: NonEmptyString
    objective: NonEmptyString


class EvidenceRequirement(ImmutableModel):
    id: NonEmptyString
    requirement: NonEmptyString
    source_tools: tuple[NonEmptyString, ...] = Field(min_length=1)


class PlanStepDraft(ImmutableModel):
    id: NonEmptyString
    objective: NonEmptyString
    required_evidence: tuple[EvidenceRequirement, ...] = Field(min_length=1)


class PlanDraft(ImmutableModel):
    goal: Goal
    steps: tuple[PlanStepDraft, ...] = Field(min_length=1, max_length=MAX_PLAN_STEPS)

    @model_validator(mode="after")
    def globally_unique_ids(self) -> PlanDraft:
        identifiers = [self.goal.id]
        for step in self.steps:
            identifiers.append(step.id)
            identifiers.extend(item.id for item in step.required_evidence)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Goal, step, and evidence requirement IDs must be unique")
        return self


class PlanStep(PlanStepDraft):
    state: StepState = "pending"


class AcceptedEvidence(ImmutableModel):
    step_id: NonEmptyString
    requirement_id: NonEmptyString
    fact: NonEmptyString
    source_call_id: NonEmptyString


class SuccessfulToolCall(ImmutableModel):
    call_id: NonEmptyString
    step_id: NonEmptyString
    tool_name: NonEmptyString


class PlanState(ImmutableModel):
    revision: int = Field(ge=1)
    goal: Goal
    steps: tuple[PlanStep, ...]
    active_step_id: str | None = None
    accepted_evidence: tuple[AcceptedEvidence, ...] = ()
    successful_tool_calls: tuple[SuccessfulToolCall, ...] = ()


class EvidenceClaim(ImmutableModel):
    requirement_id: NonEmptyString
    fact: NonEmptyString
    source_call_id: NonEmptyString


class CompleteStep(ImmutableModel):
    plan_revision: int = Field(ge=1)
    step_id: NonEmptyString
    summary: NonEmptyString
    evidence: tuple[EvidenceClaim, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_evidence_requirements(self) -> CompleteStep:
        identifiers = [item.requirement_id for item in self.evidence]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Evidence requirement IDs must be unique")
        return self


class Finish(ImmutableModel):
    outcome: Literal["completed"]
    final_response: NonEmptyString


ERROR_MESSAGES = {
    "undeclared_evidence_source": "Plan evidence names tools that are not available.",
    "active_step_exists": "A step is already active.",
    "no_pending_step": "The plan has no pending step.",
    "source_call_not_visible": "Evidence must reference a call made for the active step.",
    "duplicate_tool_call_id": "Successful tool call IDs must be unique.",
    "stale_plan_revision": "The control action used a stale plan revision.",
    "unknown_step": "The control action names an unknown step.",
    "inactive_step": "Only the active step may be completed.",
    "invalid_evidence_requirements": "Evidence must map exactly to the active step requirements.",
    "unknown_or_unsuccessful_source_call": "Evidence must reference a successful tool call.",
    "incompatible_source_tool": "The source tool is not allowed for this evidence requirement.",
    "incomplete_plan": "The plan cannot finish while required steps remain incomplete.",
}


class PlanStateError(ValueError):
    def __init__(self, code: str, **details: Any):
        self.code = code
        self.message = ERROR_MESSAGES[code]
        self.details = details
        super().__init__(self.message)

    def observation(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            value["details"] = self.details
        return value


def create_plan_state(
    draft: PlanDraft, *, declared_tools: set[str] | frozenset[str]
) -> PlanState:
    for step in draft.steps:
        for requirement in step.required_evidence:
            undeclared = sorted(set(requirement.source_tools) - set(declared_tools))
            if undeclared:
                raise PlanStateError(
                    "undeclared_evidence_source",
                    step_id=step.id,
                    requirement_id=requirement.id,
                    undeclared_tools=undeclared,
                )
    return PlanState(
        revision=1,
        goal=draft.goal,
        steps=tuple(
            PlanStep(
                id=step.id,
                objective=step.objective,
                required_evidence=step.required_evidence,
            )
            for step in draft.steps
        ),
    )


def activate_next_step(state: PlanState) -> PlanState:
    if state.active_step_id is not None:
        raise PlanStateError(
            "active_step_exists",
            active_step_id=state.active_step_id,
        )
    next_index = next(
        (index for index, step in enumerate(state.steps) if step.state == "pending"),
        None,
    )
    if next_index is None:
        raise PlanStateError("no_pending_step")
    steps = list(state.steps)
    steps[next_index] = steps[next_index].model_copy(update={"state": "active"})
    return state.model_copy(
        update={
            "revision": state.revision + 1,
            "steps": tuple(steps),
            "active_step_id": steps[next_index].id,
        }
    )


def record_successful_tool_call(
    state: PlanState, call: SuccessfulToolCall
) -> PlanState:
    if state.active_step_id != call.step_id:
        raise PlanStateError(
            "source_call_not_visible",
            active_step_id=state.active_step_id,
            call_step_id=call.step_id,
        )
    if any(item.call_id == call.call_id for item in state.successful_tool_calls):
        raise PlanStateError(
            "duplicate_tool_call_id",
            source_call_id=call.call_id,
        )
    return state.model_copy(
        update={
            "revision": state.revision + 1,
            "successful_tool_calls": state.successful_tool_calls + (call,),
        }
    )


def complete_step(state: PlanState, action: CompleteStep) -> PlanState:
    if action.plan_revision != state.revision:
        raise PlanStateError(
            "stale_plan_revision",
            expected_revision=state.revision,
            received_revision=action.plan_revision,
        )
    step = next((item for item in state.steps if item.id == action.step_id), None)
    if step is None:
        raise PlanStateError("unknown_step", step_id=action.step_id)
    if state.active_step_id != step.id or step.state != "active":
        raise PlanStateError(
            "inactive_step",
            active_step_id=state.active_step_id,
            step_id=step.id,
        )

    requirements = {item.id: item for item in step.required_evidence}
    claims = {item.requirement_id: item for item in action.evidence}
    missing = sorted(requirements.keys() - claims.keys())
    unknown = sorted(claims.keys() - requirements.keys())
    if missing or unknown:
        raise PlanStateError(
            "invalid_evidence_requirements",
            missing_requirement_ids=missing,
            unknown_requirement_ids=unknown,
        )

    calls = {item.call_id: item for item in state.successful_tool_calls}
    accepted = []
    for requirement_id, claim in claims.items():
        source_call = calls.get(claim.source_call_id)
        if source_call is None:
            raise PlanStateError(
                "unknown_or_unsuccessful_source_call",
                source_call_id=claim.source_call_id,
            )
        if source_call.step_id != step.id:
            raise PlanStateError(
                "source_call_not_visible",
                source_call_id=source_call.call_id,
                source_step_id=source_call.step_id,
                active_step_id=step.id,
            )
        requirement = requirements[requirement_id]
        if source_call.tool_name not in requirement.source_tools:
            raise PlanStateError(
                "incompatible_source_tool",
                source_call_id=source_call.call_id,
                source_tool=source_call.tool_name,
                allowed_source_tools=list(requirement.source_tools),
            )
        accepted.append(
            AcceptedEvidence(
                step_id=step.id,
                requirement_id=requirement_id,
                fact=claim.fact,
                source_call_id=claim.source_call_id,
            )
        )

    steps = tuple(
        item.model_copy(update={"state": "completed"}) if item.id == step.id else item
        for item in state.steps
    )
    return state.model_copy(
        update={
            "revision": state.revision + 1,
            "steps": steps,
            "active_step_id": None,
            "accepted_evidence": state.accepted_evidence + tuple(accepted),
        }
    )


def finish(state: PlanState, action: Finish) -> str:
    incomplete = [step.id for step in state.steps if step.state != "completed"]
    if incomplete:
        raise PlanStateError(
            "incomplete_plan",
            incomplete_step_ids=incomplete,
        )
    return action.final_response
