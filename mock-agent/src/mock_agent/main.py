from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from automationbench.domains.sales.tasks import get_zoom_calendar_conflict_task
from automationbench.rubric import partial_credit, task_completed_correctly
from automationbench.schema.world import WorldState
from automationbench.tools.zapier.google_calendar import google_calendar_find_event
from automationbench.tools.zapier.google_sheets import google_sheets_get_many_rows
from automationbench.tools.zapier.slack import slack_send_channel_message
from automationbench.tools.zapier.zoom import zoom_list_meetings, zoom_update_meeting


EXPERIMENT_SYSTEM_PROMPT = """You are a useful Sales agent.
Use the available tools to proactively resolve the problem that is presented to you.
Treat the spreadsheet policy as authoritative. Preserve source titles and identifiers verbatim.
Do not guess tool results, do not make unrelated changes.
"""

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parent
API_KEY_PLACEHOLDER = "replace-with-your-openai-api-key"


def load_openai_api_key(
    repository_env: Path = REPOSITORY_ROOT / ".env",
    project_env: Path = PROJECT_ROOT / ".env",
) -> str | None:
    """Load the repository key first, falling back to the project .env file."""
    load_dotenv(repository_env, override=True)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == API_KEY_PLACEHOLDER:
        load_dotenv(project_env, override=True)
    return os.environ.get("OPENAI_API_KEY")


def make_task_tools(world: WorldState) -> list[BaseTool]:
    """Bind the five least-privilege tools needed by this benchmark task."""

    @tool
    def read_priority_policy() -> str:
        """Read every row of the authoritative Meeting Priority Policy spreadsheet."""
        return google_sheets_get_many_rows(
            world,
            spreadsheet_id="ss_meeting_policy",
            worksheet_id="ws_priority_rules",
            row_count=50,
        )

    @tool
    def list_zoom_meetings(start_at: str | None = None) -> str:
        """List Zoom meetings, optionally starting at an ISO-8601 timestamp."""
        return zoom_list_meetings(world, start_at=start_at)

    @tool
    def find_primary_calendar_events(start_time: str, end_time: str) -> str:
        """Find primary-calendar events overlapping an ISO-8601 time window."""
        return google_calendar_find_event(
            world,
            calendarid="primary",
            start_time=start_time,
            end_time=end_time,
        )

    @tool
    def update_zoom_meeting_topic(meeting_id: int, topic: str) -> str:
        """Change only the topic of an existing Zoom meeting."""
        return zoom_update_meeting(world, meeting_id=meeting_id, topic=topic)

    @tool
    def post_ops_update(text: str) -> str:
        """Post a resolution summary only to the ops-updates Slack channel."""
        return slack_send_channel_message(world, channel_name="ops-updates", text=text)

    return [
        read_priority_policy,
        list_zoom_meetings,
        find_primary_calendar_events,
        update_zoom_meeting_topic,
        post_ops_update,
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


def make_openai_model(model: str, tools: list[BaseTool]) -> Runnable:
    return ChatOpenAI(model=model).bind_tools(tools)


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
    agent_model: Runnable[Any, BaseMessage],
    *,
    model_name: str,
    max_steps: int = 12,
) -> dict[str, Any]:
    task = get_zoom_calendar_conflict_task()
    world = WorldState(**copy.deepcopy(task["info"]["initial_state"]))
    tools = make_task_tools(world)
    graph = build_graph(agent_model, tools)

    prompt_messages: list[BaseMessage] = [SystemMessage(content=EXPERIMENT_SYSTEM_PROMPT)]
    prompt_messages.extend(
        SystemMessage(content=item["content"])
        if item["role"] == "system"
        else HumanMessage(content=item["content"])
        for item in task["prompt"]
    )
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
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/sales.zoom_calendar_conflict.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = load_openai_api_key()
    if not api_key or api_key == API_KEY_PLACEHOLDER:
        raise SystemExit(
            "Set OPENAI_API_KEY in the repository-root .env or mock-agent/.env before running"
        )
    task = get_zoom_calendar_conflict_task()
    bootstrap_world = WorldState(**copy.deepcopy(task["info"]["initial_state"]))
    tools = make_task_tools(bootstrap_world)
    model = make_openai_model(args.model, tools)
    result = run_benchmark(model, model_name=args.model, max_steps=args.max_steps)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    score = result["score"]
    print(f"task: {result['task']}")
    print(f"partial_credit: {score['partial_credit']:.3f}")
    print(f"task_completed_correctly: {score['task_completed_correctly']:.0f}")
    print(f"result: {args.output}")


if __name__ == "__main__":
    main()
