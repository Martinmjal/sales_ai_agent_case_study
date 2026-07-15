# Mock Agent

A deliberately small LangGraph ReAct loop for one cherry-picked AutomationBench task:
`sales.zoom_calendar_conflict` (example 603).

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

Place your OpenAI API key in the repository-root `.env`:

```bash
LIBRA_INTERVIEW_API_KEY=replace-with-your-libra-api-key
```

## Run the single benchmark task

```bash
uv run mock-agent
```

The command prints AutomationBench's `partial_credit` and strict
`task_completed_correctly` metrics. It also writes the complete trace, assertion results,
token usage, and final simulated world to
`results/sales.zoom_calendar_conflict.json`.

The agent uses `gpt-5.6-sol` through the Libra Azure Responses API endpoint.

## Verify the graph without an API call

```bash
uv run pytest
```

The integration test drives the same agent node, `ToolNode`, world mutations, and official
AutomationBench scorer with a scripted model. This checks wiring and scoring; it is not an LLM
benchmark result.

To expand to 10–12 tasks later, pass each selected task dictionary to `run_benchmark`; its prompt,
initial state, assertions, and tool list are all loaded from that task.
