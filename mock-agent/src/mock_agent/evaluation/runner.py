from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from mock_agent.adapter import AutomationBenchAdapter
from mock_agent.artifacts import RunArtifactStore, artifact_from_outcome, task_snapshot
from mock_agent.catalog import TaskCatalog
from mock_agent.contract import AgentRuntime, EventKind, RuntimeOutcome, RuntimeRequest
from mock_agent.evaluation.records import (
    EvaluationConfiguration,
    EvaluationManifest,
    completed_triples,
)


RuntimeFactory = Callable[[], AgentRuntime]


def infrastructure_failure(outcome: RuntimeOutcome) -> bool:
    return any(
        event.kind is EventKind.MODEL_ERROR
        and isinstance(event.content, dict)
        and event.content.get("infrastructure_failure") is True
        for event in outcome.events
    )


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
    resuming = any(
        identity == config.identity
        and task_id in manifest.tasks
        and 1 <= repetition <= repetitions
        for identity, task_id, repetition in existing
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
            replacements = 0
            while True:
                started_at = datetime.now(timezone.utc).isoformat()
                started = monotonic()
                # A factory call per attempt guarantees empty runtime state, including retries.
                outcome = await runtime_factory().run(
                    RuntimeRequest(task_id=task_id, model_name=config.values["model"])
                )
                finished_at = datetime.now(timezone.utc).isoformat()
                if infrastructure_failure(outcome):
                    replacements += 1
                    continue
                artifact = artifact_from_outcome(
                    outcome,
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
                filename = f"{config.identity}_{task_id.replace('.', '-')}_r{repetition:03}.json"
                store.write(artifact, filename=filename)
                existing.add(triple)
                break
