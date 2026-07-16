const state = {
  tasks: [],
  sessions: [],
  selectedTask: null,
  selectedSession: null,
  eventSource: null,
};

const elements = {
  browser: document.querySelector("#task-browser"),
  config: document.querySelector("#config-list"),
  connection: document.querySelector("#connection-status"),
  finalBlock: document.querySelector("#final-block"),
  finalResponse: document.querySelector("#final-response"),
  historyCount: document.querySelector("#history-count"),
  historyEmpty: document.querySelector("#history-empty"),
  historyList: document.querySelector("#history-list"),
  inspectorState: document.querySelector("#inspector-state"),
  preview: document.querySelector("#task-preview"),
  progressBlock: document.querySelector("#progress-block"),
  progressCopy: document.querySelector("#progress-copy"),
  progressTitle: document.querySelector("#progress-title"),
  score: document.querySelector("#session-score"),
  search: document.querySelector("#task-search"),
  sessionStatus: document.querySelector("#session-status"),
  sessionTaskId: document.querySelector("#session-task-id"),
  sessionTaskName: document.querySelector("#session-task-name"),
  sessionPrompt: document.querySelector("#session-prompt"),
  sessionWorkspace: document.querySelector("#session-workspace"),
  taskList: document.querySelector("#task-list"),
  toast: document.querySelector("#toast"),
};

function userPrompt(prompt) {
  const messages = [...prompt].reverse();
  return (messages.find((message) => message.role === "user") || messages[0] || {}).content || "";
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
    await loadSession(summary.session_id);
    await refreshHistory();
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
    button.textContent = "Run task";
  }
}

function renderHistory() {
  elements.historyCount.textContent = String(state.sessions.length);
  elements.historyEmpty.hidden = state.sessions.length > 0;
  elements.historyList.replaceChildren();
  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    if (session.session_id === state.selectedSession?.session_id) button.classList.add("active");
    const name = document.createElement("strong");
    const status = document.createElement("span");
    name.textContent = session.task_name;
    status.textContent = session.status;
    button.append(name, status);
    button.addEventListener("click", () => loadSession(session.session_id));
    elements.historyList.append(button);
  }
}

async function refreshHistory() {
  const payload = await api("/api/sessions");
  state.sessions = payload.sessions;
  renderHistory();
}

function renderSession(session) {
  state.selectedSession = session;
  elements.browser.hidden = true;
  elements.sessionWorkspace.hidden = false;
  elements.sessionTaskName.textContent = session.task.name;
  elements.sessionTaskId.textContent = session.task.task_id;
  elements.sessionPrompt.textContent = userPrompt(session.task.prompt);
  elements.sessionStatus.textContent = session.status;
  elements.sessionStatus.className = `status-badge ${session.status.toLowerCase()}`;

  const running = session.status === "Running";
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
    elements.finalResponse.textContent = session.final_response || "No final response was produced.";
    const partial = session.evaluation?.partial_credit;
    elements.score.textContent = partial == null ? "Unavailable" : `${Math.round(partial * 100)}%`;
  }

  elements.config.replaceChildren();
  const configItems = [
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
  elements.inspectorState.textContent = running ? "Execution is owned by the local server." : `Session ${session.status.toLowerCase()} with a durable artifact.`;
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

document.querySelector("#back-to-tasks").addEventListener("click", () => {
  closeEventStream();
  elements.browser.hidden = false;
  elements.sessionWorkspace.hidden = true;
  elements.connection.textContent = `${state.tasks.length} tasks ready`;
});

elements.search.addEventListener("input", () => renderTasks(elements.search.value));

async function initialize() {
  try {
    const [taskPayload, sessionPayload] = await Promise.all([
      api("/api/tasks"),
      api("/api/sessions"),
    ]);
    state.tasks = taskPayload.tasks;
    state.sessions = sessionPayload.sessions;
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
