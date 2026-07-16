const state = {
  tasks: [],
  sessions: [],
  selectedTask: null,
  selectedSession: null,
  activeSessionId: null,
  stoppingSessionId: null,
  eventSource: null,
};

const elements = {
  appShell: document.querySelector("#app-shell"),
  browser: document.querySelector("#task-browser"),
  config: document.querySelector("#config-list"),
  connection: document.querySelector("#connection-status"),
  errorList: document.querySelector("#execution-error-list"),
  errors: document.querySelector("#execution-errors"),
  evidenceMetrics: document.querySelector("#evidence-metrics"),
  finalBlock: document.querySelector("#final-block"),
  finalResponse: document.querySelector("#final-response"),
  historyCount: document.querySelector("#history-count"),
  historyContent: document.querySelector("#history-content"),
  historyEmpty: document.querySelector("#history-empty"),
  historyList: document.querySelector("#history-list"),
  historyPanel: document.querySelector("#history-panel"),
  historySearch: document.querySelector("#history-search"),
  historyToggle: document.querySelector("#history-toggle"),
  inspector: document.querySelector("#inspector"),
  inspectorContent: document.querySelector("#inspector-content"),
  inspectorEmpty: document.querySelector("#inspector-empty"),
  inspectorPrompt: document.querySelector("#inspector-prompt"),
  inspectorState: document.querySelector("#inspector-state"),
  assertionList: document.querySelector("#assertion-list"),
  assertionTotal: document.querySelector("#assertion-total"),
  initialWorld: document.querySelector("#initial-world-snapshot"),
  preview: document.querySelector("#task-preview"),
  progressBlock: document.querySelector("#progress-block"),
  progressCopy: document.querySelector("#progress-copy"),
  progressTitle: document.querySelector("#progress-title"),
  finalWorld: document.querySelector("#final-world-snapshot"),
  rawSession: document.querySelector("#raw-session-json"),
  reasoningEvidence: document.querySelector("#reasoning-evidence"),
  reasoningSummaries: document.querySelector("#reasoning-summaries"),
  returnActive: document.querySelector("#return-active"),
  score: document.querySelector("#session-score"),
  search: document.querySelector("#task-search"),
  sessionStatus: document.querySelector("#session-status"),
  sessionTaskId: document.querySelector("#session-task-id"),
  sessionTaskName: document.querySelector("#session-task-name"),
  sessionPrompt: document.querySelector("#session-prompt"),
  sessionWorkspace: document.querySelector("#session-workspace"),
  stopRun: document.querySelector("#stop-run"),
  taskList: document.querySelector("#task-list"),
  toolCount: document.querySelector("#tool-count"),
  toolDefinitions: document.querySelector("#tool-definitions"),
  toast: document.querySelector("#toast"),
  trace: document.querySelector("#causal-trace"),
  worldDiff: document.querySelector("#world-diff"),
};

function userPrompt(prompt) {
  const messages = [...prompt].reverse();
  return (messages.find((message) => message.role === "user") || messages[0] || {}).content || "";
}

function displayValue(value) {
  if (value == null) return "Unavailable";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function nodeState(session, event, result) {
  if (event.kind === "tool_call") {
    if (result?.kind === "tool_error") return "failed";
    if (result) return "completed";
    return session.status === "Running" ? "running" : session.status.toLowerCase();
  }
  if (event.kind === "completion") return session.status.toLowerCase();
  return "completed";
}

function traceNode(kind, title, stateName, correlationId) {
  const node = document.createElement("article");
  node.className = `trace-node trace-${kind} trace-state-${stateName}`;
  node.dataset.traceKind = kind;
  node.dataset.state = stateName;
  if (correlationId) node.dataset.correlationId = correlationId;
  node.setAttribute("aria-label", `${title}, ${stateName}`);

  const heading = document.createElement("div");
  heading.className = "trace-node-heading";
  const label = document.createElement("strong");
  label.textContent = title;
  const stateLabel = document.createElement("span");
  stateLabel.className = "trace-node-state";
  stateLabel.textContent = stateName;
  heading.append(label, stateLabel);
  node.append(heading);
  return node;
}

function addEvidence(node, label, value) {
  if (value == null) return;
  const row = document.createElement("div");
  row.className = "trace-evidence";
  const term = document.createElement("span");
  const content = document.createElement("pre");
  term.textContent = label;
  content.textContent = displayValue(value);
  row.append(term, content);
  node.append(row);
}

function durationLabel(session) {
  const start = Date.parse(session.lifecycle.created_at);
  const end = Date.parse(session.lifecycle.completed_at || session.lifecycle.updated_at);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "Unavailable";
  const seconds = (end - start) / 1000;
  return `${seconds.toFixed(seconds < 10 && !Number.isInteger(seconds) ? 2 : 0)} s`;
}

function usageLabel(usage) {
  if (!usage) return "Unavailable";
  const parts = [];
  const reasoningTokens = usage.reasoning_tokens ?? usage.output_token_details?.reasoning;
  if (usage.input_tokens != null) parts.push(`${usage.input_tokens} input`);
  if (usage.output_tokens != null) parts.push(`${usage.output_tokens} output`);
  if (usage.total_tokens != null) parts.push(`${usage.total_tokens} total`);
  if (reasoningTokens != null) parts.push(`${reasoningTokens} reasoning`);
  return parts.length > 0 ? parts.join(" · ") : "Unavailable";
}

function metric(label, value, stateName = null) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value;
  if (stateName) detail.dataset.metricState = stateName;
  row.append(term, detail);
  return row;
}

function collectWorldChanges(initialValue, finalValue, path = "world", changes = []) {
  if (JSON.stringify(initialValue) === JSON.stringify(finalValue)) return changes;
  if (
    initialValue == null
    || finalValue == null
    || typeof initialValue !== "object"
    || typeof finalValue !== "object"
  ) {
    changes.push({
      action: initialValue === undefined ? "Added" : finalValue === undefined ? "Removed" : "Changed",
      path,
      before: initialValue,
      after: finalValue,
    });
    return changes;
  }
  if (Array.isArray(initialValue) || Array.isArray(finalValue)) {
    const before = Array.isArray(initialValue) ? initialValue : [];
    const after = Array.isArray(finalValue) ? finalValue : [];
    for (let index = 0; index < Math.max(before.length, after.length); index += 1) {
      collectWorldChanges(before[index], after[index], `${path}[${index}]`, changes);
    }
    return changes;
  }
  const keys = new Set([...Object.keys(initialValue), ...Object.keys(finalValue)]);
  for (const key of [...keys].sort()) {
    collectWorldChanges(initialValue[key], finalValue[key], `${path}.${key}`, changes);
  }
  return changes;
}

function renderWorldEvidence(session) {
  elements.initialWorld.textContent = displayValue(session.initial_world);
  elements.finalWorld.textContent = displayValue(session.final_world);
  elements.worldDiff.replaceChildren();
  if (session.initial_world == null || session.final_world == null) {
    const unavailable = document.createElement("p");
    unavailable.className = "unavailable-evidence";
    unavailable.textContent = "World changes unavailable";
    elements.worldDiff.append(unavailable);
    return;
  }
  const changes = collectWorldChanges(session.initial_world, session.final_world);
  if (changes.length === 0) {
    const unchanged = document.createElement("p");
    unchanged.className = "unchanged-evidence";
    unchanged.textContent = "No world changes recorded.";
    elements.worldDiff.append(unchanged);
    return;
  }
  for (const change of changes) {
    const row = document.createElement("article");
    row.className = "world-change";
    const heading = document.createElement("div");
    const action = document.createElement("strong");
    const path = document.createElement("code");
    action.textContent = change.action;
    path.textContent = change.path;
    heading.append(action, path);
    row.append(heading);
    if (change.before !== undefined) addEvidence(row, "Before", change.before);
    if (change.after !== undefined) addEvidence(row, "After", change.after);
    elements.worldDiff.append(row);
  }
}

function renderEvaluationEvidence(session) {
  const evaluation = session.evaluation;
  const partial = evaluation?.partial_credit;
  const strict = evaluation?.task_completed_correctly;
  elements.evidenceMetrics.replaceChildren(
    metric("Lifecycle", session.status, session.status.toLowerCase()),
    metric("Partial credit", partial == null ? "Unavailable" : `${Math.round(partial * 100)}%`),
    metric(
      "Strict completion",
      strict == null ? "Unavailable" : Number(strict) === 1 ? "Passed" : "Failed",
      strict == null ? "unavailable" : Number(strict) === 1 ? "passed" : "failed",
    ),
    metric("Duration", durationLabel(session)),
    metric("Token usage", usageLabel(session.usage)),
  );

  const assertions = evaluation?.assertions;
  elements.assertionList.replaceChildren();
  if (!Array.isArray(assertions)) {
    elements.assertionTotal.textContent = "Unavailable";
    const unavailable = document.createElement("p");
    unavailable.className = "unavailable-evidence";
    unavailable.textContent = "Assertion results unavailable";
    elements.assertionList.append(unavailable);
  } else {
    const scored = assertions.filter((assertion) => !assertion.excluded);
    const passed = scored.filter((assertion) => assertion.passed).length;
    elements.assertionTotal.textContent = `${passed} of ${scored.length} scored assertions passed`;
    for (const assertion of assertions) {
      const explicitlyExcluded = assertion.params?.excluded === true || assertion.params?.scored === false;
      const statusName = assertion.excluded ? "excluded" : assertion.passed ? "passed" : "failed";
      const item = document.createElement("details");
      item.className = `assertion-result assertion-${statusName}`;
      item.dataset.assertionStatus = statusName;
      const summary = document.createElement("summary");
      const name = document.createElement("strong");
      const status = document.createElement("span");
      name.textContent = assertion.type;
      status.textContent = assertion.excluded
        ? explicitlyExcluded ? "Excluded" : "Pre-satisfied · excluded"
        : assertion.passed ? "Passed" : "Failed";
      summary.append(name, status);
      const params = document.createElement("pre");
      params.textContent = displayValue(assertion.params || {});
      item.append(summary, params);
      elements.assertionList.append(item);
    }
  }

  renderWorldEvidence(session);
  const summaries = session.events.flatMap((event) => {
    const summary = event.metadata?.reasoning_summary ?? event.metadata?.reasoning?.summary;
    return Array.isArray(summary) ? summary : summary == null ? [] : [summary];
  });
  elements.reasoningEvidence.hidden = summaries.length === 0;
  elements.reasoningSummaries.replaceChildren();
  for (const summary of summaries) {
    const content = document.createElement("p");
    content.textContent = displayValue(summary);
    elements.reasoningSummaries.append(content);
  }
  elements.rawSession.textContent = JSON.stringify(session, null, 2);
}

function renderToolCall(session, call, result) {
  const stateName = nodeState(session, call, result);
  const disclosure = document.createElement("details");
  disclosure.className = `trace-node trace-tool-call trace-state-${stateName}`;
  disclosure.dataset.traceKind = "tool_call";
  disclosure.dataset.correlationId = call.correlation_id;
  disclosure.dataset.state = stateName;
  disclosure.setAttribute("aria-label", `${call.name || "Tool call"}, ${stateName}`);
  if (stateName === "failed") disclosure.open = true;

  const summary = document.createElement("summary");
  const name = document.createElement("strong");
  const stateLabel = document.createElement("span");
  name.textContent = call.name || "Tool call";
  stateLabel.className = "trace-node-state";
  stateLabel.textContent = stateName;
  summary.append(name, stateLabel);
  disclosure.append(summary);
  addEvidence(disclosure, "Arguments", call.arguments);
  addEvidence(disclosure, "Result", result?.result);
  addEvidence(disclosure, "Error", result?.error);
  addEvidence(disclosure, "Duration", result?.duration_ms == null ? null : `${result.duration_ms} ms`);
  addEvidence(disclosure, "Correlation ID", call.correlation_id);
  return disclosure;
}

function renderInspector(session) {
  elements.inspectorEmpty.hidden = true;
  elements.inspectorContent.hidden = false;
  elements.inspectorPrompt.textContent = session.task.prompt
    .map((message) => `${message.role}: ${displayValue(message.content)}`)
    .join("\n\n");
  renderEvaluationEvidence(session);

  const tools = session.task.tool_definitions || (session.task.tools || []).map((name) => ({ name }));
  elements.toolCount.textContent = `${tools.length} available tools`;
  elements.toolDefinitions.replaceChildren();
  for (const tool of tools) {
    const definition = document.createElement("section");
    const name = document.createElement("strong");
    const description = document.createElement("p");
    const schema = document.createElement("pre");
    name.textContent = tool.name;
    description.textContent = tool.description || "No description provided.";
    schema.textContent = displayValue(tool.input_schema || {});
    definition.append(name, description, schema);
    elements.toolDefinitions.append(definition);
  }

  elements.config.replaceChildren();
  const configItems = [
    ["Session ID", session.session_id],
    ["Model", session.agent.model],
    ["Maximum steps", session.agent.max_steps],
    ["Agent version", session.agent.agent_version],
  ];
  for (const [label, value] of configItems) {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value;
    row.append(term, detail);
    elements.config.append(row);
  }

  elements.trace.replaceChildren();
  const events = [...session.events].sort((left, right) => left.sequence - right.sequence);
  const results = new Map(
    events
      .filter((event) => ["tool_result", "tool_error"].includes(event.kind))
      .map((event) => [event.correlation_id, event]),
  );
  const callsByParent = new Map();
  const knownCalls = new Set();
  const renderedCalls = new Set();
  let hasCompletion = false;
  for (const event of events.filter((item) => item.kind === "tool_call")) {
    knownCalls.add(event.correlation_id);
    const calls = callsByParent.get(event.parent_id) || [];
    calls.push(event);
    callsByParent.set(event.parent_id, calls);
  }

  for (const event of events) {
    if (event.kind === "model_turn") {
      const turn = traceNode("model_turn", "Assistant turn", nodeState(session, event), event.correlation_id);
      addEvidence(turn, "Response", event.content);
      addEvidence(turn, "Duration", event.duration_ms == null ? null : `${event.duration_ms} ms`);
      elements.trace.append(turn);
      const calls = callsByParent.get(event.correlation_id) || [];
      if (calls.length > 0) {
        const batch = document.createElement("div");
        batch.className = calls.length > 1 ? "parallel-tool-batch" : "tool-batch";
        batch.dataset.parentId = event.correlation_id;
        batch.setAttribute("aria-label", calls.length > 1 ? "Parallel tool calls" : "Tool call");
        for (const call of calls) {
          batch.append(renderToolCall(session, call, results.get(call.correlation_id)));
          renderedCalls.add(call.correlation_id);
        }
        elements.trace.append(batch);
      }
    } else if (event.kind === "tool_call" && !renderedCalls.has(event.correlation_id)) {
      const batch = document.createElement("div");
      batch.className = "tool-batch";
      batch.append(renderToolCall(session, event, results.get(event.correlation_id)));
      elements.trace.append(batch);
      renderedCalls.add(event.correlation_id);
    } else if (
      ["tool_result", "tool_error"].includes(event.kind)
      && !knownCalls.has(event.correlation_id)
    ) {
      const stateName = event.kind === "tool_error" ? "failed" : "completed";
      const evidence = traceNode(
        event.kind,
        event.name || (event.kind === "tool_error" ? "Tool error" : "Tool result"),
        stateName,
        event.correlation_id,
      );
      addEvidence(evidence, "Result", event.result);
      addEvidence(evidence, "Error", event.error);
      addEvidence(evidence, "Duration", event.duration_ms == null ? null : `${event.duration_ms} ms`);
      addEvidence(evidence, "Correlation ID", event.correlation_id);
      elements.trace.append(evidence);
    } else if (event.kind === "completion") {
      hasCompletion = true;
      const completion = traceNode("completion", "Final response", nodeState(session, event), event.correlation_id);
      addEvidence(completion, "Response", session.final_response || "No final response was produced.");
      elements.trace.append(completion);
    }
  }

  if (!hasCompletion && session.status !== "Running") {
    const outcome = traceNode(
      "completion",
      "Execution outcome",
      session.status.toLowerCase(),
      session.session_id,
    );
    addEvidence(outcome, "Response", session.final_response || "No final response was produced.");
    addEvidence(outcome, "Terminal error", session.lifecycle.terminal_error);
    elements.trace.append(outcome);
  } else if (events.length === 0) {
    const empty = document.createElement("p");
    empty.className = "trace-empty";
    empty.textContent = session.status === "Running" ? "Waiting for the first assistant turn." : "No runtime events were recorded.";
    elements.trace.append(empty);
  }
}

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : detail.message);
  }
  return payload;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  window.setTimeout(() => { elements.toast.hidden = true; }, 4200);
}

function renderTasks(query = "") {
  const needle = query.trim().toLowerCase();
  const tasks = state.tasks.filter((task) => (
    task.name.toLowerCase().includes(needle) || task.task_id.toLowerCase().includes(needle)
  ));
  elements.taskList.replaceChildren();
  for (const task of tasks) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "task-item";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", task.task_id === state.selectedTask?.task_id ? "true" : "false");
    if (task.task_id === state.selectedTask?.task_id) button.classList.add("active");
    const name = document.createElement("strong");
    const id = document.createElement("code");
    name.textContent = task.name;
    id.textContent = task.task_id;
    button.append(name, id);
    button.addEventListener("click", () => selectTask(task));
    elements.taskList.append(button);
  }
}

function selectTask(task) {
  state.selectedTask = task;
  renderTasks(elements.search.value);
  elements.preview.className = "task-preview";
  elements.preview.replaceChildren();

  const eyebrow = document.createElement("span");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = task.task_id;
  const title = document.createElement("h2");
  title.textContent = task.name;
  const prompt = document.createElement("p");
  prompt.className = "preview-prompt";
  prompt.textContent = userPrompt(task.prompt);
  const meta = document.createElement("div");
  meta.className = "meta-row";
  for (const label of [`${task.tools.length} tools`, `${task.assertion_count} assertions`]) {
    const chip = document.createElement("span");
    chip.className = "meta-chip";
    chip.textContent = label;
    meta.append(chip);
  }
  const run = document.createElement("button");
  run.type = "button";
  run.className = "run-button";
  run.textContent = "Run task";
  run.addEventListener("click", () => startTask(task, run));
  elements.preview.append(eyebrow, title, prompt, meta, run);
  elements.inspectorState.textContent = `${task.tools.length} declared tools and ${task.assertion_count} deterministic assertions.`;
}

async function startTask(task, button) {
  button.disabled = true;
  button.textContent = "Starting...";
  try {
    const summary = await api("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: task.task_id }),
    });
    state.activeSessionId = summary.session_id;
    await loadSession(summary.session_id);
    await refreshHistory();
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
    button.textContent = "Run task";
  }
}

function renderHistory() {
  const needle = elements.historySearch.value.trim().toLowerCase();
  const sessions = state.sessions.filter((session) => (
    session.task_name.toLowerCase().includes(needle) || session.task_id.toLowerCase().includes(needle)
  ));
  elements.historyCount.textContent = String(state.sessions.length);
  elements.historyEmpty.hidden = sessions.length > 0;
  elements.historyEmpty.textContent = state.sessions.length > 0 ? "No matching runs" : "No runs yet";
  elements.returnActive.hidden = !state.activeSessionId || state.selectedSession?.session_id === state.activeSessionId;
  elements.historyList.replaceChildren();
  const groups = new Map([
    ["Today", []],
    ["Previous 7 days", []],
    ["Older", []],
  ]);
  for (const session of sessions) groups.get(historyGroup(session.created_at)).push(session);
  for (const [label, groupSessions] of groups) {
    if (groupSessions.length === 0) continue;
    const group = document.createElement("section");
    group.className = "history-group";
    const heading = document.createElement("h3");
    heading.textContent = label;
    group.append(heading);
    for (const session of groupSessions) group.append(historyItem(session));
    elements.historyList.append(group);
  }
}

function historyGroup(timestamp) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const created = new Date(timestamp);
  created.setHours(0, 0, 0, 0);
  const daysAgo = Math.floor((today - created) / 86400000);
  if (daysAgo <= 0) return "Today";
  return daysAgo <= 7 ? "Previous 7 days" : "Older";
}

function historyItem(session) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "history-item";
  button.dataset.sessionId = session.session_id;
  if (session.session_id === state.selectedSession?.session_id) button.classList.add("selected");
  if (session.session_id === state.activeSessionId) button.classList.add("active-run");

  const heading = document.createElement("span");
  heading.className = "history-item-heading";
  const name = document.createElement("strong");
  const status = document.createElement("span");
  status.className = "history-status";
  status.classList.add(session.status.toLowerCase());
  name.textContent = session.task_name;
  status.textContent = session.status;
  heading.append(name, status);

  const taskId = document.createElement("code");
  taskId.textContent = session.task_id;
  const details = document.createElement("span");
  details.className = "history-details";
  const score = session.partial_credit == null ? "No score" : `${Math.round(session.partial_credit * 100)}%`;
  details.textContent = `${new Date(session.created_at).toLocaleString()} | ${score}`;
  const sessionId = document.createElement("span");
  sessionId.className = "history-session-id";
  sessionId.textContent = session.session_id;
  button.append(heading, taskId, details, sessionId);
  button.addEventListener("click", () => loadSession(session.session_id));
  return button;
}

async function refreshHistory() {
  const payload = await api("/api/sessions");
  state.sessions = payload.sessions;
  state.activeSessionId = state.sessions.find((session) => session.status === "Running")?.session_id || null;
  renderHistory();
}

function renderSession(session) {
  state.selectedSession = session;
  elements.sessionWorkspace.dataset.sessionId = session.session_id;
  elements.inspector.dataset.sessionId = session.session_id;
  elements.browser.hidden = true;
  elements.sessionWorkspace.hidden = false;
  elements.sessionTaskName.textContent = session.task.name;
  elements.sessionTaskId.textContent = session.task.task_id;
  elements.sessionPrompt.textContent = userPrompt(session.task.prompt);
  elements.sessionStatus.textContent = session.status;
  elements.sessionStatus.className = `status-badge ${session.status.toLowerCase()}`;

  const running = session.status === "Running";
  const stopping = state.stoppingSessionId === session.session_id;
  elements.stopRun.hidden = !running || session.session_id !== state.activeSessionId;
  elements.stopRun.disabled = stopping;
  elements.stopRun.textContent = stopping ? "Stopping..." : "Stop run";
  elements.progressBlock.hidden = !running;
  elements.finalBlock.hidden = running;
  if (running) {
    const latest = session.events.at(-1);
    if (latest?.kind === "completion") {
      elements.progressTitle.textContent = "Evaluation";
      elements.progressCopy.textContent = "Scoring the final benchmark world.";
    } else if (["tool_call", "tool_result", "tool_error"].includes(latest?.kind)) {
      elements.progressTitle.textContent = "Tool batch activity";
      elements.progressCopy.textContent = latest.kind === "tool_call" ? `Running ${latest.name || "a benchmark tool"}.` : "Collecting completed tool results.";
    } else {
      elements.progressTitle.textContent = "Model activity";
      elements.progressCopy.textContent = latest ? "Preparing the next benchmark action." : "Reviewing the prompt and available tools.";
    }
  } else {
    if (state.stoppingSessionId === session.session_id) {
      state.stoppingSessionId = null;
    }
    elements.finalResponse.textContent = session.final_response || "Final response unavailable";
    const partial = session.evaluation?.partial_credit;
    elements.score.textContent = partial == null ? "Unavailable" : `${Math.round(partial * 100)}%`;
    const errors = [];
    if (session.lifecycle.terminal_error) errors.push(session.lifecycle.terminal_error);
    elements.errors.hidden = errors.length === 0;
    elements.errorList.replaceChildren();
    for (const error of errors) {
      const message = document.createElement("pre");
      message.textContent = error;
      elements.errorList.append(message);
    }
  }

  renderInspector(session);
  renderHistory();
}

function closeEventStream() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

function streamSession(session) {
  closeEventStream();
  const after = session.events.at(-1)?.sequence || 0;
  const source = new EventSource(`/api/sessions/${session.session_id}/events?after=${after}`);
  state.eventSource = source;
  elements.connection.textContent = "Live";

  source.addEventListener("runtime", (message) => {
    if (state.selectedSession?.session_id !== session.session_id) return;
    const event = JSON.parse(message.data);
    const latest = state.selectedSession.events.at(-1)?.sequence || 0;
    if (event.sequence <= latest) return;
    state.selectedSession.events.push(event);
    renderSession(state.selectedSession);
  });
  source.addEventListener("session", async () => {
    closeEventStream();
    if (state.selectedSession?.session_id === session.session_id) {
      const completed = await api(`/api/sessions/${session.session_id}`);
      renderSession(completed);
      await refreshHistory();
    }
    elements.connection.textContent = `${state.tasks.length} tasks ready`;
  });
  source.onerror = async () => {
    if (state.selectedSession?.session_id !== session.session_id) return;
    const materialized = await api(`/api/sessions/${session.session_id}`);
    renderSession(materialized);
    if (materialized.status !== "Running") {
      closeEventStream();
      await refreshHistory();
    }
  };
}

async function loadSession(sessionId) {
  closeEventStream();
  const session = await api(`/api/sessions/${sessionId}`);
  renderSession(session);
  if (session.status === "Running") {
    streamSession(session);
  } else {
    await refreshHistory();
  }
}

async function stopActiveRun() {
  const session = state.selectedSession;
  if (!session || session.status !== "Running" || session.session_id !== state.activeSessionId) return;
  state.stoppingSessionId = session.session_id;
  renderSession(session);
  try {
    await api(`/api/sessions/${session.session_id}/stop`, { method: "POST" });
    elements.progressTitle.textContent = "Stopping execution";
    elements.progressCopy.textContent = "Waiting for the current safe boundary.";
  } catch (error) {
    state.stoppingSessionId = null;
    renderSession(session);
    showToast(error.message);
  }
}

document.querySelector("#back-to-tasks").addEventListener("click", () => {
  closeEventStream();
  elements.browser.hidden = false;
  elements.sessionWorkspace.hidden = true;
  elements.connection.textContent = `${state.tasks.length} tasks ready`;
});

elements.search.addEventListener("input", () => renderTasks(elements.search.value));
elements.historySearch.addEventListener("input", renderHistory);
elements.returnActive.addEventListener("click", () => loadSession(state.activeSessionId));
elements.stopRun.addEventListener("click", stopActiveRun);
elements.historyToggle.addEventListener("click", () => {
  const collapsed = elements.historyPanel.classList.toggle("collapsed");
  elements.appShell.classList.toggle("history-collapsed", collapsed);
  elements.historyContent.hidden = collapsed;
  elements.historyToggle.textContent = collapsed ? ">" : "<";
  elements.historyToggle.setAttribute("aria-expanded", String(!collapsed));
  const action = collapsed ? "Expand" : "Collapse";
  elements.historyToggle.setAttribute("aria-label", `${action} history`);
  elements.historyToggle.title = `${action} history`;
});

async function initialize() {
  try {
    const [taskPayload, sessionPayload] = await Promise.all([
      api("/api/tasks"),
      api("/api/sessions"),
    ]);
    state.tasks = taskPayload.tasks;
    state.sessions = sessionPayload.sessions;
    state.activeSessionId = state.sessions.find((session) => session.status === "Running")?.session_id || null;
    renderTasks();
    renderHistory();
    elements.connection.textContent = `${state.tasks.length} tasks ready`;
    const active = state.sessions.find((session) => session.status === "Running");
    if (active) await loadSession(active.session_id);
  } catch (error) {
    elements.connection.textContent = "Unavailable";
    showToast(error.message);
  }
}

initialize();
