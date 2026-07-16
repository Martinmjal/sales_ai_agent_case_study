from __future__ import annotations

import argparse
import copy
from functools import wraps
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolMessage,
    convert_to_messages,
)
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from automationbench.domains.sales.tasks import get_zoom_calendar_conflict_task
from automationbench.rubric import partial_credit, task_completed_correctly
from automationbench.schema.world import WorldState
from automationbench.tool_wrapper import _create_tool_wrapper
from automationbench.tools import ALL_TOOLS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parent


def make_task_tools(task: dict[str, Any], world: WorldState) -> list[BaseTool]:
    """Bind the task's declared Zapier tools to its in-memory world."""
    registry = {tool.__name__: tool for tool in ALL_TOOLS}
    names = task["info"]["zapier_tools"]
    unknown = set(names) - registry.keys()
    if unknown:
        raise ValueError(f"Unknown task tools: {sorted(unknown)}")

    def bind_world(func):
        visible_func = _create_tool_wrapper(func, args_to_skip=["world"])

        @wraps(visible_func)
        def bound(*args, **kwargs):
            return func(world, *args, **kwargs)

        return bound

    return [
        StructuredTool.from_function(
            func=bind_world(registry[name]),
            name=name,
            description=registry[name].__doc__ or name,
        )
        for name in names
    ]


def build_graph(agent_model: Runnable[Any, BaseMessage], tools: list[BaseTool]):
    """Build the entire loop: one agent node, one ToolNode, and two edges."""

    def agent_node(state: MessagesState) -> dict[str, list[BaseMessage]]:
        return {"messages": [agent_model.invoke(state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()


def score_world(task: dict[str, Any], world: WorldState) -> dict[str, Any]:
    benchmark_state: dict[str, Any] = {
        "info": task["info"],
        "initial_state": copy.deepcopy(task["info"]["initial_state"]),
        "world": world,
    }
    score = partial_credit(benchmark_state)
    strict_pass = task_completed_correctly(benchmark_state)
    return {
        "partial_credit": score,
        "task_completed_correctly": strict_pass,
        "assertions": benchmark_state.get("_assertion_results", []),
    }


def serialize_message(message: BaseMessage) -> dict[str, Any]:
    record: dict[str, Any] = {"type": message.type, "content": message.content}
    if isinstance(message, AIMessage):
        record["tool_calls"] = message.tool_calls
        if message.usage_metadata:
            record["usage_metadata"] = message.usage_metadata
    if isinstance(message, ToolMessage):
        record["name"] = message.name
        record["tool_call_id"] = message.tool_call_id
    return record


def run_benchmark(
    task: dict[str, Any],
    model_name: str,
    max_steps: int = 12,
    agent_model: Runnable[Any, BaseMessage] | None = None,
) -> dict[str, Any]:
    world = WorldState(**copy.deepcopy(task["info"]["initial_state"]))
    tools = make_task_tools(task, world)
    if agent_model is None:
        base_url = os.environ.get("LIBRA_BASE_URL")
        if not base_url:
            raise RuntimeError(
                "Set LIBRA_BASE_URL in mock-agent/.env before running the benchmark"
            )
        agent_model = ChatOpenAI(
            model=model_name,
            api_key=os.environ.get("LIBRA_INTERVIEW_API_KEY")
            or os.environ["OPENAI_API_KEY"],
            base_url=base_url,
            use_responses_api=True,
        ).bind_tools(tools)
    graph = build_graph(agent_model, tools)

    prompt_messages = convert_to_messages(task["prompt"])
    final_state = graph.invoke(
        {"messages": prompt_messages},
        config={"recursion_limit": max_steps * 2 + 1},
    )
    messages = final_state["messages"]
    score = score_world(task, world)

    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for message in messages:
        if isinstance(message, AIMessage) and message.usage_metadata:
            for key in usage:
                usage[key] += int(message.usage_metadata.get(key, 0))

    return {
        "task": task["task"],
        "example_id": task["example_id"],
        "model": model_name,
        "tools": [task_tool.name for task_tool in tools],
        "score": score,
        "usage": usage,
        "messages": [serialize_message(message) for message in messages],
        "end_state": world.model_dump(mode="json"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one AutomationBench task with LangGraph")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/sales.zoom_calendar_conflict.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(REPOSITORY_ROOT / ".env")
    task = get_zoom_calendar_conflict_task()
    result = run_benchmark(task, args.model, args.max_steps)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    score = result["score"]
    print(f"task: {result['task']}")
    print(f"partial_credit: {score['partial_credit']:.3f}")
    print(f"task_completed_correctly: {score['task_completed_correctly']:.0f}")
    print(f"result: {args.output}")


if __name__ == "__main__":
    main()
