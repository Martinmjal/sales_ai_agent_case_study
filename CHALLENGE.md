## The Challenge

**Build a small AI agent that carries out long‑running, multi‑step tasks on a user's behalf.**

The user describes a high‑level goal, your agent breaks it into work, executes it using tools, and returns a result.

You pick the domain (research assistant, coding helper, ops assistant, document analyst, project planner, whatever you can show well) and the interaction model (CLI, chat, minimal UI).

**The interesting part is not the happy path.** Long‑running tasks rarely go exactly to plan, and a fixed sequence of prompts won't get you far. We're interested in how your agent decides what to do next, keeps track of where it is, and copes when things don't go smoothly. How you approach that is up to you, and it's a large part of what we're looking at.

> **Important:** Please do **not** use agent frameworks (LangChain, LangGraph, AutoGen, CrewAI, etc.). We want to see your own loop, prompts, and context handling. Thin, non‑agent libraries (an HTTP client, a vector store, the provider SDK) are fine.
> 

---

## Keep It Simple

We are not looking for a reusable agent framework or a platform. We want the simplest harness that does the job well. Developing a solution that's overly/unjustifiably complex will count against you. A narrow, polished, well‑understood agent beats an ambitious half‑finished one.

## Evaluation

How do you know your agent is any good? **Build a runnable evaluation harness, use it to evaluate your own agent, and tell us what you learned and what you'd improve.** We care more about sound thinking here than breadth.

---

## Deliverables

1. **Source Code** — Public Git repository with clear structure and run instructions.
2. **README** — In your own words: how your agent works, the key decisions you made and why, and what you'd do with more time.
3. **Evaluation Harness** — A runnable eval harness and the results of running it on your agent.
4. **Example Run** — A real task from start to finish.
5. **Short Video (3–5 min)** — Explain in your own words how your agent works, how information and tools flow through it, and how you'd extend it.
6. **Build Session Logs** — Assuming you used AI to help build your solution (eg claude code, codex, copilot, etc), export all raw session logs into a `build_sessions/` directory. Do not edit these, as we want to see how you work.

## Time

Aim for roughly 4–6 hours, but it's really up to you. Spend your time where you think it best shows your judgment, and tell us in the README how you spent it and what you traded off.

---

## How We Evaluate

- **Harness engineering (40%)** — the agent loop, how it decides and adapts, context and state handling, and robustness over many steps. Observability into what the agent did (clear tracing) is a big plus.
- **Evaluation (30%)** — a runnable eval harness and what you did with it.
- **Prompt and context engineering (15%)**
- **Code quality, simplicity, and judgment (15%)**

---

## Questions?

If anything is unclear, feel free to reach out during the application process.