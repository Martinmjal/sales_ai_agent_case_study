from __future__ import annotations

import os

from dotenv import load_dotenv
import uvicorn

from agent_ui.app import AgentConfig, REPOSITORY_ROOT, create_app
from mock_agent.model import OpenAIModelClient
from mock_agent.planner_executor import PlannerExecutorRuntime


load_dotenv(REPOSITORY_ROOT / "mock-agent" / ".env")
load_dotenv(REPOSITORY_ROOT / ".env")

runtime_name = os.environ.get("AGENT_RUNTIME", "langgraph")
if runtime_name not in {"langgraph", "planner-executor"}:
    raise RuntimeError("AGENT_RUNTIME must be langgraph or planner-executor")
runtime = (
    PlannerExecutorRuntime(model_client=OpenAIModelClient())
    if runtime_name == "planner-executor"
    else None
)

app = create_app(
    runtime=runtime,
    config=AgentConfig(
        model=os.environ.get("AGENT_MODEL", "gpt-5.6-sol"),
        max_steps=int(os.environ.get("AGENT_MAX_STEPS", "12")),
        agent_version=os.environ.get(
            "AGENT_VERSION",
            "planner-executor/0.1.0"
            if runtime_name == "planner-executor"
            else "mock-agent/0.1.0",
        ),
    ),
)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
