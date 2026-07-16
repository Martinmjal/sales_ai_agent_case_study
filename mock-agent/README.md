# Mock Agent

A deliberately small LangGraph ReAct loop with two consumers:

- The original command-line workflow runs the cherry-picked
  `sales.zoom_calendar_conflict` task (example 603).
- A framework-neutral evaluator runtime exposes all 100 registered AutomationBench sales
  tasks by canonical task ID.

The graph has exactly two nodes:

```text
START -> agent -> tools -> agent -> ... -> END
```

The model receives exactly the tools declared by the selected task's `info["zapier_tools"]`
list. The runner resolves those names from AutomationBench's tool registry and binds each tool
to a fresh in-memory world for that run.

## Set up

From this directory:

```bash
uv sync
```

Copy the example environment file and fill in the interview API key and endpoint:

```bash
cp .env.example .env
```

The runner also loads the repository-root `.env`, so an existing `OPENAI_API_KEY`
there remains available as an API-key fallback. Keep both `.env` files local; they
are excluded by the repository's `.gitignore`.

## Evaluator runtime

`mock_agent.catalog.TaskCatalog` reads only the registered sales dataset. Its stable summaries
contain the canonical task ID, normalized prompt messages, configured tool names, and assertion
count. `get_task()` raises `UnknownTaskError` for an unregistered ID instead of falling back.

Evaluator code can depend on `mock_agent.contract.AgentRuntime` and its dataclasses without
importing LangGraph or LangChain types. `mock_agent.runtime.MockAgentRuntime` is the temporary
LangGraph adapter:

```python
from mock_agent.catalog import TaskCatalog
from mock_agent.contract import RuntimeRequest
from mock_agent.runtime import MockAgentRuntime

catalog = TaskCatalog.from_sales_dataset()
summaries = catalog.list_tasks()

outcome = await MockAgentRuntime(catalog=catalog).run(
    RuntimeRequest(
        task_id="sales.zoom_calendar_conflict",
        model_name="gpt-5.6-sol",
    ),
    event_sink=handle_event,
)
```

The sink receives ordered model-turn, tool-call, tool-result, tool-error, and completion events.
Tool calls and results share correlation IDs; observable timestamps, metadata, usage, and
durations are retained. A `CancellationSignal` stops cooperatively after a model boundary or a
completed tool batch. Every run returns a `Completed`, `Stopped`, or `Failed` outcome containing
the available trace, final response, world state, official score, usage, and terminal error.

## Run the single benchmark task

```bash
uv run mock-agent
```

The command prints AutomationBench's `partial_credit` and strict
`task_completed_correctly` metrics. It also writes the complete trace, assertion results,
token usage, and final simulated world to
`results/sales.zoom_calendar_conflict.json`.

The agent uses `gpt-5.6-sol` through the Libra Azure Responses API endpoint.

## Framework-free planner-executor

`mock_agent.planner_executor.PlannerExecutorRuntime` is the custom runtime under
development. It uses a direct Responses API client, creates a bounded structured plan,
executes one step at a time through framework-free tool specifications and validation,
and asks the planner to review tool-grounded evidence. AutomationBench task identity,
assertions, expected values, raw world state, and scoring remain inside the adapter.

Run it through the existing evaluator while retaining this LangGraph baseline:

```bash
cd ../Agent-UI
AGENT_RUNTIME=planner-executor uv run agent-ui
```

## Verify the graph without an API call

```bash
uv run pytest
```

The compact test suite drives the same agent node, `ToolNode`, world mutations, and official
AutomationBench scorer with scripted models. It covers the catalog, correlated runtime events,
tool errors, cooperative stop and failure outcomes, and the original CLI-compatible runner. It
requires no model API key and is not an LLM benchmark result.
