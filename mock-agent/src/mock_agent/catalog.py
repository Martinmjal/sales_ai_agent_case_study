from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import lru_cache
import json
from typing import Any

from automationbench.domains.sales.tasks import get_sales_dataset


class UnknownTaskError(LookupError):
    """Raised when a canonical benchmark task ID is not registered."""


@dataclass(frozen=True)
class PromptMessage:
    role: str
    content: str


@dataclass(frozen=True)
class TaskSummary:
    task_id: str
    example_id: int
    prompt: tuple[PromptMessage, ...]
    tools: tuple[str, ...]
    assertion_count: int


@dataclass(frozen=True)
class TaskDefinition:
    summary: TaskSummary
    info: dict[str, Any]

    def to_benchmark_task(self) -> dict[str, Any]:
        return {
            "task": self.summary.task_id,
            "example_id": self.summary.example_id,
            "prompt": [
                {"role": message.role, "content": message.content}
                for message in self.summary.prompt
            ],
            "info": copy.deepcopy(self.info),
        }


class TaskCatalog:
    def __init__(self, tasks: list[TaskDefinition]):
        self._tasks = {task.summary.task_id: task for task in tasks}
        if len(self._tasks) != len(tasks):
            raise ValueError("Task catalog contains duplicate canonical IDs")

    @classmethod
    @lru_cache(maxsize=1)
    def from_sales_dataset(cls) -> TaskCatalog:
        tasks = []
        for record in get_sales_dataset():
            info = record["info"]
            if isinstance(info, str):
                info = json.loads(info)
            normalized_info = copy.deepcopy(info)
            prompt = tuple(
                PromptMessage(role=message["role"], content=message["content"])
                for message in record["prompt"]
            )
            summary = TaskSummary(
                task_id=record["task"],
                example_id=int(record["example_id"]),
                prompt=prompt,
                tools=tuple(normalized_info["zapier_tools"]),
                assertion_count=len(normalized_info["assertions"]),
            )
            tasks.append(TaskDefinition(summary=summary, info=normalized_info))
        return cls(tasks)

    def list_tasks(self) -> tuple[TaskSummary, ...]:
        return tuple(task.summary for task in self._tasks.values())

    def get_task(self, task_id: str) -> TaskDefinition:
        try:
            task = self._tasks[task_id]
        except KeyError as error:
            raise UnknownTaskError(f"Unknown task ID: {task_id}") from error
        return TaskDefinition(summary=task.summary, info=copy.deepcopy(task.info))
