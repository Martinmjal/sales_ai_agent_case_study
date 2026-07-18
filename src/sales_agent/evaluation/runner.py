from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import monotonic

from sales_agent.adapter import AutomationBenchAdapter
from sales_agent.artifacts import RunArtifactStore, artifact_from_outcome, task_snapshot
from sales_agent.catalog import TaskCatalog
from sales_agent.contract import AgentRuntime, EventKind, RuntimeOutcome, RuntimeRequest
from sales_agent.evaluation.records import (
    EvaluationConfiguration,
    EvaluationManifest,
    completed_triples,
    load_records,
)

RuntimeFactory = Callable[[], AgentRuntime]
MAX_INFRASTRUCTURE_REPLACEMENTS = 2


class InfrastructureReplacementLimitError(RuntimeError):
    """Raised after the final infrastructure-invalid attempt is persisted."""


def infrastructure_failure(outcome: RuntimeOutcome) -> bool:
    if outcome.evaluation_error is not None:
        return True
    return any(
        event.kind is EventKind.ADAPTER_ERROR
        or (
            event.kind is EventKind.MODEL_ERROR
            and isinstance(event.content, dict)
            and event.content.get("infrastructure_failure") is True
        )
        for event in outcome.events
    )


def _observation_filename(config_identity: str, task_id: str, repetition: int) -> str:
    return f"{config_identity}_{task_id.replace('.', '-')}_r{repetition:03}.json"


def _diagnostic_filename(observation_filename: str, run_id: str, started_at: str) -> str:
    identity = sha256(f"{run_id}\0{started_at}".encode()).hexdigest()[:16]
    return f"{observation_filename.removesuffix('.json')}_infrastructure_{identity}.json"


def _infrastructure_diagnostic(outcome: RuntimeOutcome, message: str) -> RuntimeOutcome:
    evaluation_error = message
    if outcome.evaluation_error:
        evaluation_error = f"{message}; scorer error: {outcome.evaluation_error}"
    return replace(outcome, score=None, evaluation_error=evaluation_error)


async def run_evaluations(
    manifest: EvaluationManifest,
    config: EvaluationConfiguration,
    repetitions: int,
    directory: Path,
    runtime_factory: RuntimeFactory,
) -> None:
    if repetitions < 1:
        raise ValueError("Repetitions must be positive")
    config.require_frozen_execution_limits()
    directory.mkdir(parents=True, exist_ok=True)
    existing = completed_triples(directory, config)
    records = load_records(directory)
    resuming = any(
        record.configuration_identity == config.identity
        and record.task_id in manifest.tasks
        and 1 <= record.repetition <= repetitions
        for record in records
    )
    catalog = TaskCatalog.from_sales_dataset()
    adapter = AutomationBenchAdapter(catalog=catalog)
    store = RunArtifactStore(directory)
    for task_id in manifest.tasks:
        task = catalog.get_task(task_id)
        initial_world = task.info["initial_state"]
        tools = adapter.open(task_id).agent_task.tools
        snapshot = task_snapshot(
            task,
            tool_definitions=[
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ],
        )
        for repetition in range(1, repetitions + 1):
            triple = (config.identity, task_id, repetition)
            if triple in existing:
                continue
            for replacements in range(MAX_INFRASTRUCTURE_REPLACEMENTS + 1):
                started_at = datetime.now(timezone.utc).isoformat()
                started = monotonic()
                # A factory call per attempt guarantees empty runtime state, including retries.
                outcome = await runtime_factory().run(
                    RuntimeRequest(task_id=task_id, model_name=config.values["model"])
                )
                finished_at = datetime.now(timezone.utc).isoformat()
                infrastructure_invalid = infrastructure_failure(outcome)
                if infrastructure_invalid and replacements < MAX_INFRASTRUCTURE_REPLACEMENTS:
                    continue
                failure_message = (
                    "Infrastructure replacement limit exhausted "
                    f"for {task_id} repetition {repetition} after "
                    f"{MAX_INFRASTRUCTURE_REPLACEMENTS} replacements "
                    f"({MAX_INFRASTRUCTURE_REPLACEMENTS + 1} failed attempts)"
                )
                persisted_outcome = (
                    _infrastructure_diagnostic(outcome, failure_message)
                    if infrastructure_invalid
                    else outcome
                )
                artifact = artifact_from_outcome(
                    persisted_outcome,
                    task=snapshot,
                    configuration=config.artifact_values(),
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=(monotonic() - started) * 1000,
                    initial_world=initial_world,
                    evaluation_context={
                        "configuration_identity": config.identity,
                        "repetition": repetition,
                        "fresh_world": True,
                        "resumed": resuming,
                        "infrastructure_replacement_count": replacements,
                    },
                )
                observation_filename = _observation_filename(config.identity, task_id, repetition)
                filename = (
                    _diagnostic_filename(observation_filename, outcome.run_id, started_at)
                    if infrastructure_invalid
                    else observation_filename
                )
                path = store.write(artifact, filename=filename)
                if infrastructure_invalid:
                    raise InfrastructureReplacementLimitError(
                        f"{failure_message}; diagnostic artifact: {path}"
                    )
                existing.add(triple)
                break
