# Mock Agent

A deliberately small LangGraph ReAct loop for one cherry-picked AutomationBench task:
`sales.zoom_calendar_conflict` (example 603).

The graph has exactly two nodes:

```text
START -> agent -> tools -> agent -> ... -> END
```

The model receives only five task-scoped tools. Read access is limited to the meeting policy,
Zoom meetings, and primary-calendar events. Write access is limited to renaming a Zoom meeting
and posting to `#ops-updates`; the agent cannot modify Calendar or post to another channel.

## Set up

From this directory:

```bash
uv sync
```

Place your OpenAI API key in the repository-root `.env` or replace the placeholder in
`mock-agent/.env`:

```bash
OPENAI_API_KEY=replace-with-your-openai-api-key
```

## Run the single benchmark task

```bash
uv run mock-agent
```

The command prints AutomationBench's `partial_credit` and strict
`task_completed_correctly` metrics. It also writes the complete trace, assertion results,
token usage, and final simulated world to
`results/sales.zoom_calendar_conflict.json`.

The default model is `gpt-5.6-terra`. You can override it explicitly, for example:

```bash
uv run mock-agent --model gpt-5.5
```

## Verify the graph without an API call

```bash
uv run pytest
```

The integration test drives the same agent node, `ToolNode`, world mutations, and official
AutomationBench scorer with a scripted model. This checks wiring and scoring; it is not an LLM
benchmark result.

To expand to 10–12 tasks later, keep the graph unchanged and add one task adapter per selected
task: its task loader plus a least-privilege tool factory.
