from __future__ import annotations

import copy
from dataclasses import dataclass
import inspect
import json
from typing import Any, get_type_hints

from automationbench.rubric import partial_credit, task_completed_correctly
from automationbench.schema.world import WorldState
from automationbench.tools import ALL_TOOLS
from pydantic import BaseModel, ValidationError, create_model

from mock_agent.catalog import PromptMessage, TaskCatalog, TaskDefinition


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    value: Any = None
    error: dict[str, Any] | None = None


class ToolDispatcher:
    def __init__(
        self,
        tools: dict[str, Any],
        validators: dict[str, type[BaseModel]],
        world: WorldState,
    ):
        self._tools = tools
        self._validators = validators
        self._world = world

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            return ToolResult(
                error={"type": "unknown_tool", "message": f"Unknown tool: {name}"}
            )
        try:
            values = self._validators[name].model_validate(arguments).model_dump()
        except ValidationError as error:
            details = [
                {
                    "location": list(item["loc"]),
                    "message": item["msg"],
                    "code": item["type"],
                }
                for item in error.errors(include_url=False, include_input=False)
            ]
            return ToolResult(
                error={
                    "type": "invalid_arguments",
                    "message": "Tool arguments failed validation.",
                    "details": details,
                }
            )
        try:
            result = self._tools[name](self._world, **values)
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    pass
            return ToolResult(value=result)
        except Exception as error:
            return ToolResult(
                error={
                    "type": "tool_exception",
                    "message": f"{type(error).__name__}: {error}",
                }
            )


@dataclass(frozen=True)
class AgentTask:
    prompt: tuple[PromptMessage, ...]
    tools: tuple[ToolSpec, ...]
    dispatcher: ToolDispatcher


class AutomationBenchSession:
    def __init__(
        self, definition: TaskDefinition, world: WorldState, agent_task: AgentTask
    ):
        self.agent_task = agent_task
        self._definition = definition
        self._world = world

    def evaluate(self) -> tuple[dict[str, Any], dict[str, Any]]:
        task = self._definition.to_benchmark_task()
        state = {
            "info": task["info"],
            "initial_state": copy.deepcopy(task["info"]["initial_state"]),
            "world": self._world,
        }
        score = {
            "partial_credit": partial_credit(state),
            "task_completed_correctly": task_completed_correctly(state),
            "assertions": state.get("_assertion_results", []),
        }
        return score, self._world.model_dump(mode="json")


class AutomationBenchAdapter:
    def __init__(self, catalog: TaskCatalog | None = None):
        self._catalog = catalog or TaskCatalog.from_sales_dataset()
        self._registry = {tool.__name__: tool for tool in ALL_TOOLS}

    def open(self, task_id: str) -> AutomationBenchSession:
        definition = self._catalog.get_task(task_id)
        world = WorldState(**copy.deepcopy(definition.info["initial_state"]))
        missing = set(definition.summary.tools) - self._registry.keys()
        if missing:
            raise ValueError(f"Unknown task tools: {sorted(missing)}")
        functions = {name: self._registry[name] for name in definition.summary.tools}
        validators = {name: _arguments_model(functions[name]) for name in functions}
        specs = tuple(
            ToolSpec(
                name=name,
                description=functions[name].__doc__ or name,
                input_schema=validators[name].model_json_schema(),
            )
            for name in definition.summary.tools
        )
        task = AgentTask(
            prompt=definition.summary.prompt,
            tools=specs,
            dispatcher=ToolDispatcher(functions, validators, world),
        )
        return AutomationBenchSession(definition, world, task)


def _arguments_model(function: Any) -> type[BaseModel]:
    hints = get_type_hints(function)
    fields = {}
    for name, parameter in inspect.signature(function).parameters.items():
        if name == "world":
            continue
        default = (
            ... if parameter.default is inspect.Parameter.empty else parameter.default
        )
        fields[name] = (hints.get(name, Any), default)
    return create_model(f"{function.__name__}_arguments", **fields)
