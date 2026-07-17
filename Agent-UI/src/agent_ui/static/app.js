const state = {
  tasks: [],
  runtimes: [],
  selectedRuntimeId: null,
  sessions: [],
  selectedTask: null,
  selectedSession: null,
  activeSessionId: null,
  stoppingSessionId: null,
  eventSource: null,
  worldChanges: new Map(),
};

const elements = {
  appShell: document.querySelector("#app-shell"),
  browser: document.querySelector("#task-browser"),
  closeHistory: document.querySelector("#close-history"),
  closeInspector: document.querySelector("#close-inspector"),
  config: document.querySelector("#config-list"),
  connection: document.querySelector("#connection-status"),
  errorList: document.querySelector("#execution-error-list"),
  errors: document.querySelector("#execution-errors"),
  evidenceMetrics: document.querySelector("#evidence-metrics"),
  drawerBackdrop: document.querySelector("#drawer-backdrop"),
  finalBlock: document.querySelector("#final-block"),
  finalResponse: document.querySelector("#final-response"),
  historyCount: document.querySelector("#history-count"),
  historyContent: document.querySelector("#history-content"),
  historyEmpty: document.querySelector("#history-empty"),
  historyList: document.querySelector("#history-list"),
  historyPanel: document.querySelector("#history-panel"),
  historyResizer: document.querySelector("#history-resizer"),
  historySearch: document.querySelector("#history-search"),
  historyToggle: document.querySelector("#history-toggle"),
  inspector: document.querySelector("#inspector"),
  inspectorContent: document.querySelector("#inspector-content"),
  inspectorEmpty: document.querySelector("#inspector-empty"),
  inspectorPrompt: document.querySelector("#inspector-prompt"),
  inspectorResizer: document.querySelector("#inspector-resizer"),
  inspectorState: document.querySelector("#inspector-state"),
  openHistory: document.querySelector("#open-history"),
  openInspector: document.querySelector("#open-inspector"),
  assertionList: document.querySelector("#assertion-list"),
  assertionTotal: document.querySelector("#assertion-total"),
  initialWorld: document.querySelector("#initial-world-snapshot"),
  preview: document.querySelector("#task-preview"),
  progressBlock: document.querySelector("#progress-block"),
  progressCopy: document.querySelector("#progress-copy"),
  progressTitle: document.querySelector("#progress-title"),
  planBlock: document.querySelector("#structured-plan"),
  planEmpty: document.querySelector("#plan-empty"),
  planGenerations: document.querySelector("#plan-generations"),
  planGoal: document.querySelector("#plan-goal"),
  planSummary: document.querySelector("#plan-summary"),
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
  sessionRuntimeLabel: document.querySelector("#session-runtime-label"),
  sessionWorkspace: document.querySelector("#session-workspace"),
  stopRun: document.querySelector("#stop-run"),
  taskList: document.querySelector("#task-list"),
  runtimePicker: document.querySelector("#runtime-picker"),
  toolCount: document.querySelector("#tool-count"),
  toolDefinitions: document.querySelector("#tool-definitions"),
  toast: document.querySelector("#toast"),
  trace: document.querySelector("#causal-trace"),
  technicalWorldDiff: document.querySelector("#technical-world-diff"),
  worldActivity: document.querySelector("#world-activity"),
  worldSection: document.querySelector("#world-section"),
  worldSummary: document.querySelector("#world-summary"),
  worldDiff: document.querySelector("#world-diff"),
};

const narrowLayout = window.matchMedia("(max-width: 740px)");
const mediumLayout = window.matchMedia("(min-width: 741px) and (max-width: 1180px)");
const paneWidthStorageKey = "agent-ui-pane-widths";
const defaultPaneWidths = { history: 230, inspector: 330 };
const paneWidthLimits = {
  history: { min: 180, max: 420 },
  inspector: { min: 280, max: 720 },
};
const preferredPaneWidths = loadPaneWidths();
let effectivePaneWidths = { ...defaultPaneWidths };
let openDrawer = null;
let drawerTrigger = null;

function loadPaneWidths() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(paneWidthStorageKey));
    return Object.fromEntries(Object.entries(defaultPaneWidths).map(([pane, fallback]) => [
      pane,
      Number.isFinite(saved?.[pane]) ? saved[pane] : fallback,
    ]));
  } catch {
    return { ...defaultPaneWidths };
  }
}

function savePaneWidths() {
  try {
    window.localStorage.setItem(paneWidthStorageKey, JSON.stringify(preferredPaneWidths));
  } catch {
    // Resizing still works when browser storage is unavailable.
  }
}

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

function applyPaneWidths() {
  if (narrowLayout.matches) return;

  const shellWidth = elements.appShell.clientWidth;
  const collapsedHistory = elements.appShell.classList.contains("history-collapsed");
  const centerMinimum = mediumLayout.matches ? 320 : 480;
  const separatorWidth = mediumLayout.matches || collapsedHistory ? 8 : 16;
  let history = clamp(
    preferredPaneWidths.history,
    paneWidthLimits.history.min,
    paneWidthLimits.history.max,
  );
  let inspector = clamp(
    preferredPaneWidths.inspector,
    paneWidthLimits.inspector.min,
    paneWidthLimits.inspector.max,
  );

  if (mediumLayout.matches || collapsedHistory) {
    inspector = clamp(
      inspector,
      paneWidthLimits.inspector.min,
      Math.min(paneWidthLimits.inspector.max, shellWidth - 58 - separatorWidth - centerMinimum),
    );
  } else {
    const combinedMaximum = shellWidth - separatorWidth - centerMinimum;
    let overflow = history + inspector - combinedMaximum;
    if (overflow > 0) {
      const historyReduction = Math.min(overflow, history - paneWidthLimits.history.min);
      history -= historyReduction;
      overflow -= historyReduction;
      inspector = Math.max(paneWidthLimits.inspector.min, inspector - overflow);
    }
  }

  effectivePaneWidths = { history, inspector };
  elements.appShell.style.setProperty("--history-width", `${history}px`);
  elements.appShell.style.setProperty("--inspector-width", `${inspector}px`);
  updateResizerValue("history");
  updateResizerValue("inspector");
}

function paneBounds(pane) {
  const limits = paneWidthLimits[pane];
  const shellWidth = elements.appShell.clientWidth;
  const centerMinimum = mediumLayout.matches ? 320 : 480;
  const collapsedHistory = elements.appShell.classList.contains("history-collapsed");
  const otherWidth = pane === "history"
    ? effectivePaneWidths.inspector
    : (mediumLayout.matches || collapsedHistory ? 58 : effectivePaneWidths.history);
  const separatorWidth = mediumLayout.matches || collapsedHistory ? 8 : 16;
  return {
    min: limits.min,
    max: Math.max(
      limits.min,
      Math.min(limits.max, shellWidth - otherWidth - separatorWidth - centerMinimum),
    ),
  };
}

function updateResizerValue(pane) {
  const resizer = pane === "history" ? elements.historyResizer : elements.inspectorResizer;
  const bounds = paneBounds(pane);
  const width = Math.round(effectivePaneWidths[pane]);
  resizer.setAttribute("aria-valuemin", String(bounds.min));
  resizer.setAttribute("aria-valuemax", String(Math.round(bounds.max)));
  resizer.setAttribute("aria-valuenow", String(width));
  resizer.setAttribute("aria-valuetext", `${width} pixels wide`);
}

function setPaneWidth(pane, width, persist = false) {
  const bounds = paneBounds(pane);
  preferredPaneWidths[pane] = clamp(width, bounds.min, bounds.max);
  applyPaneWidths();
  if (persist) savePaneWidths();
}

function beginPaneResize(event, pane, resizer) {
  if (event.button !== 0 || narrowLayout.matches) return;
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = effectivePaneWidths[pane];
  const direction = pane === "history" ? 1 : -1;
  resizer.setPointerCapture(event.pointerId);
  resizer.classList.add("is-resizing");
  document.body.classList.add("pane-resizing");

  const move = (moveEvent) => {
    setPaneWidth(pane, startWidth + ((moveEvent.clientX - startX) * direction));
  };
  const finish = () => {
    resizer.classList.remove("is-resizing");
    document.body.classList.remove("pane-resizing");
    resizer.removeEventListener("pointermove", move);
    resizer.removeEventListener("pointerup", finish);
    resizer.removeEventListener("pointercancel", finish);
    savePaneWidths();
  };
  resizer.addEventListener("pointermove", move);
  resizer.addEventListener("pointerup", finish);
  resizer.addEventListener("pointercancel", finish);
}

function resizePaneFromKeyboard(event, pane) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const bounds = paneBounds(pane);
  const step = event.shiftKey ? 40 : 12;
  let width = effectivePaneWidths[pane];
  if (event.key === "Home") width = pane === "history" ? bounds.min : bounds.max;
  if (event.key === "End") width = pane === "history" ? bounds.max : bounds.min;
  if (event.key === "ArrowLeft") width += pane === "history" ? -step : step;
  if (event.key === "ArrowRight") width += pane === "history" ? step : -step;
  setPaneWidth(pane, width, true);
}

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
  if (["protocol_error", "model_error"].includes(event.kind)) return "failed";
  if (["budget_exhausted", "cancellation"].includes(event.kind)) return "stopped";
  return "completed";
}

function sessionRuntime(session) {
  if (session.runtime?.label && session.runtime?.version) return session.runtime;
  const version = session.agent?.agent_version || "Unknown";
  return {
    id: session.agent?.runtime_id || "legacy",
    label: session.agent?.runtime_label || version,
    version: session.agent?.runtime_version || version,
  };
}

function reducePlanEvents(events) {
  const plans = [];
  const reviews = new Map();
  let activeStep = null;

  const currentPlan = () => plans.at(-1);
  const findStep = (stepId) => {
    for (const plan of [...plans].reverse()) {
      const step = plan.steps.find((item) => item.id === stepId);
      if (step) return step;
    }
    return null;
  };
  const supersedePending = (plan) => {
    if (!plan) return;
    for (const step of plan.steps) {
      if (step.state === "pending") step.state = "superseded";
    }
  };
  const failActive = () => {
    if (activeStep && ["active", "retrying"].includes(activeStep.state)) {
      activeStep.state = "failed";
    }
    activeStep = null;
  };

  for (const event of [...events].sort((left, right) => left.sequence - right.sequence)) {
    if (event.kind === "plan_created") {
      const previous = currentPlan();
      if (previous) {
        failActive();
        supersedePending(previous);
        previous.current = false;
      }
      const content = event.content || {};
      plans.push({
        id: event.correlation_id,
        goal: content.goal || "Goal unavailable",
        current: true,
        steps: (content.steps || []).map((step) => ({
          id: step.id,
          objective: step.objective,
          requiredEvidence: Array.isArray(step.required_evidence)
            ? step.required_evidence.map((item) =>
                typeof item === "string" ? item : item.requirement,
              )
            : [],
          state: "pending",
        })),
      });
    } else if (event.kind === "step_started") {
      const step = findStep(event.content?.id || event.correlation_id);
      if (step) {
        failActive();
        step.state = "active";
        activeStep = step;
      }
    } else if (event.kind === "review") {
      const step = findStep(event.parent_id);
      reviews.set(event.correlation_id, step);
      const decision = event.content?.decision;
      if (step && ["step_completed", "goal_completed"].includes(decision)) {
        step.state = "completed";
        if (activeStep === step) activeStep = null;
      } else if (step && decision === "retry_step") {
        step.state = "retrying";
        activeStep = step;
      } else if (step && decision === "replan") {
        step.state = "failed";
        if (activeStep === step) activeStep = null;
      }
    } else if (event.kind === "step_retry") {
      const step = findStep(event.correlation_id);
      if (step) {
        step.state = "retrying";
        activeStep = step;
      }
    } else if (event.kind === "replan") {
      const failed = reviews.get(event.parent_id);
      if (failed && failed.state !== "completed") failed.state = "failed";
      failActive();
      supersedePending(currentPlan());
    } else if (["cancellation", "budget_exhausted", "protocol_error", "model_error"].includes(event.kind)) {
      failActive();
    } else if (event.kind === "completion") {
      if (event.content?.status === "completed") {
        if (activeStep) activeStep.state = "completed";
        activeStep = null;
        supersedePending(currentPlan());
      } else {
        failActive();
      }
    }
  }
  return { plans };
}

function renderPlan(session) {
  const reduced = reducePlanEvents(session.events || []);
  const hasPlan = reduced.plans.length > 0;
  const runtime = sessionRuntime(session);
  const emptyIsKnown = runtime.id === "mock-baseline"
    || session.status !== "Running"
    || (session.events || []).some((event) => event.kind !== "planning");
  elements.planBlock.hidden = !hasPlan && !emptyIsKnown;
  elements.planEmpty.hidden = hasPlan;
  elements.planGoal.hidden = !hasPlan;
  elements.planGenerations.hidden = !hasPlan;
  elements.planGenerations.replaceChildren();
  if (!hasPlan) {
    elements.planSummary.textContent = runtime.label;
    elements.planGoal.textContent = "";
    return;
  }

  const latestPlan = reduced.plans.at(-1);
  const steps = reduced.plans.flatMap((plan) => plan.steps);
  const completed = steps.filter((step) => step.state === "completed").length;
  elements.planGoal.textContent = latestPlan.goal;
  elements.planSummary.textContent = `${completed} of ${steps.length} completed`;

  reduced.plans.forEach((plan, planIndex) => {
    const generation = document.createElement("section");
    generation.className = `plan-generation ${plan.current ? "current" : "previous"}`;
    generation.dataset.planId = plan.id;
    if (reduced.plans.length > 1) {
      const label = document.createElement("h3");
      label.textContent = plan.current
        ? `Replacement plan ${planIndex + 1}`
        : `Plan ${planIndex + 1} history`;
      generation.append(label);
    }
    const list = document.createElement("ol");
    list.className = "plan-step-list";
    for (const step of plan.steps) {
      const item = document.createElement("li");
      item.className = `plan-step plan-step-${step.state}`;
      item.dataset.planStepId = step.id;
      item.dataset.state = step.state;
      const heading = document.createElement("div");
      heading.className = "plan-step-heading";
      const objective = document.createElement("strong");
      objective.textContent = step.objective;
      const status = document.createElement("span");
      status.className = "plan-step-status";
      status.textContent = step.state;
      heading.append(objective, status);
      item.append(heading);
      const evidence = document.createElement("ul");
      evidence.className = "plan-evidence";
      for (const requirement of step.requiredEvidence) {
        const entry = document.createElement("li");
        entry.textContent = requirement;
        evidence.append(entry);
      }
      item.append(evidence);
      list.append(item);
    }
    generation.append(list);
    elements.planGenerations.append(generation);
  });
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
  if (elements.worldSection.dataset.sessionId !== session.session_id) {
    elements.worldSection.open = false;
    elements.worldSection.querySelectorAll(":scope > details").forEach((disclosure) => {
      disclosure.open = false;
    });
    elements.worldSection.dataset.sessionId = session.session_id;
  }
  elements.initialWorld.textContent = displayValue(session.initial_world);
  elements.finalWorld.textContent = displayValue(session.final_world);
  elements.worldActivity.replaceChildren();
  elements.worldDiff.replaceChildren();
  if (session.initial_world == null || session.final_world == null) {
    elements.worldSummary.textContent = "Unavailable";
    elements.technicalWorldDiff.hidden = true;
    const unavailable = document.createElement("p");
    unavailable.className = "unavailable-evidence";
    unavailable.textContent = "World changes unavailable";
    elements.worldActivity.append(unavailable);
    return;
  }
  const changes = state.worldChanges.get(session.session_id)
    ?? collectWorldChanges(session.initial_world, session.final_world);
  if (changes.length === 0) {
    elements.worldSummary.textContent = "No changes";
    elements.technicalWorldDiff.hidden = true;
    const unchanged = document.createElement("p");
    unchanged.className = "unchanged-evidence";
    unchanged.textContent = "No world changes recorded.";
    elements.worldActivity.append(unchanged);
    return;
  }
  elements.technicalWorldDiff.hidden = false;
  const applications = new Set();
  const records = new Set();
  for (const change of changes) {
    const application = change.path.match(/^world\.([^.[]+)/)?.[1] || "world";
    const record = change.path.match(/^world\.[^.[]+\.[^.[]+\[\d+\]/)?.[0]
      || `world.${application}`;
    applications.add(application);
    records.add(record);
  }
  elements.worldSummary.textContent = [
    `${applications.size} ${applications.size === 1 ? "application" : "applications"}`,
    `${records.size} ${records.size === 1 ? "record" : "records"}`,
    `${changes.length} ${changes.length === 1 ? "change" : "changes"}`,
  ].join(" · ");
  renderWorldActivity(changes, session);
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

function renderWorldActivity(changes, session) {
  const applications = new Map();
  for (const change of changes) {
    const application = change.application
      || change.path.match(/^world\.([^.[]+)/)?.[1]
      || "world";
    const record = change.record || {
      path: `world.${application}`,
      collection: "state",
      identity: [],
    };
    if (!applications.has(application)) applications.set(application, new Map());
    const records = applications.get(application);
    if (!records.has(record.path)) records.set(record.path, { ...record, changes: [] });
    records.get(record.path).changes.push(change);
  }

  for (const [application, records] of [...applications].sort(([left], [right]) => left.localeCompare(right))) {
    const disclosure = document.createElement("details");
    disclosure.className = "world-application";
    disclosure.dataset.worldApplication = application;
    const summary = document.createElement("summary");
    const name = document.createElement("strong");
    const total = document.createElement("span");
    const changeCount = [...records.values()].reduce((sum, record) => sum + record.changes.length, 0);
    name.textContent = humanizeWorldName(application);
    total.textContent = `${records.size} ${records.size === 1 ? "record" : "records"} · ${changeCount} ${changeCount === 1 ? "change" : "changes"}`;
    summary.append(name, total);
    disclosure.append(summary);

    for (const record of records.values()) {
      const article = document.createElement("article");
      article.className = "world-record";
      const heading = document.createElement("strong");
      const wholeRecordChange = record.changes.length === 1
        && record.changes[0].path === record.path;
      const action = wholeRecordChange && record.changes[0].action === "Added"
        ? "Created"
        : wholeRecordChange && record.changes[0].action === "Removed"
          ? "Removed"
          : "Updated";
      const recordType = singularWorldName(record.collection);
      const identity = record.identity.map((value) => String(value)).join(" / ");
      heading.textContent = `${action} ${recordType}${identity ? ` ${identity}` : ""}`;
      article.append(heading);
      renderRecordEvidence(article, record, session);

      for (const change of record.changes) {
        const field = document.createElement("div");
        field.className = "world-field-change";
        const label = document.createElement("span");
        const fieldName = change.path === record.path
          ? action
          : humanizeWorldName(change.path.split(".").at(-1));
        label.textContent = fieldName;
        field.append(label);
        if (change.before !== undefined) addEvidence(field, "Before", change.before);
        if (change.after !== undefined) addEvidence(field, "After", change.after);
        article.append(field);
      }
      disclosure.append(article);
    }
    elements.worldActivity.append(disclosure);
  }
}

function renderRecordEvidence(article, record, session) {
  const evidence = document.createElement("div");
  evidence.className = "world-record-evidence";
  const origins = new Map();
  const assertions = new Map();
  for (const change of record.changes) {
    if (change.origin?.correlation_id) {
      origins.set(change.origin.correlation_id, change.origin);
    }
    for (const assertion of change.assertions || []) {
      assertions.set(assertion.index, assertion);
    }
  }

  if (origins.size === 1) {
    const origin = [...origins.values()][0];
    const reference = document.createElement("button");
    reference.type = "button";
    reference.className = "world-evidence-reference world-tool-reference";
    reference.dataset.toolReference = origin.correlation_id;
    reference.textContent = `Write · ${origin.tool_name}`;
    reference.setAttribute(
      "aria-label",
      `Show ${origin.tool_name} in the Execution spine`,
    );
    reference.addEventListener("click", () => revealToolEvidence(origin.correlation_id));
    evidence.append(reference);
  } else {
    const uncorrelated = document.createElement("span");
    uncorrelated.className = "world-evidence-unavailable";
    uncorrelated.textContent = "Originating write unavailable · uncorrelated";
    evidence.append(uncorrelated);
  }

  if (!Array.isArray(session.evaluation?.assertions)) {
    const unavailable = document.createElement("span");
    unavailable.className = "world-evidence-unavailable";
    unavailable.textContent = "Assertion evidence unavailable";
    evidence.append(unavailable);
  } else if (assertions.size === 0) {
    const unmatched = document.createElement("span");
    unmatched.className = "world-evidence-unavailable";
    unmatched.textContent = "No matching scored assertions";
    evidence.append(unmatched);
  } else {
    for (const assertion of [...assertions.values()].sort((left, right) => left.index - right.index)) {
      const reference = document.createElement("button");
      reference.type = "button";
      reference.className = `world-evidence-reference world-assertion-${assertion.status}`;
      reference.dataset.assertionReference = assertion.index;
      reference.textContent = `${assertion.status_label} · ${assertion.type}`;
      reference.setAttribute(
        "aria-label",
        `Show ${assertion.type} in Assertions: ${assertion.status_label}`,
      );
      reference.addEventListener("click", () => revealAssertionEvidence(assertion.index));
      evidence.append(reference);
    }
  }
  article.append(evidence);
}

function revealToolEvidence(correlationId) {
  const target = [...elements.trace.querySelectorAll("[data-correlation-id]")]
    .find((item) => item.dataset.correlationId === correlationId);
  if (!target) {
    showToast("Execution evidence for this write is unavailable.");
    return;
  }
  if (target instanceof HTMLDetailsElement) target.open = true;
  const focusTarget = target.querySelector("summary") || target;
  focusTarget.focus();
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("trace-linked-evidence");
  window.setTimeout(() => target.classList.remove("trace-linked-evidence"), 1800);
}

function revealAssertionEvidence(index) {
  const target = elements.assertionList.querySelector(`[data-assertion-index="${index}"]`);
  if (!target) {
    showToast("Assertion evidence is unavailable.");
    return;
  }
  target.open = true;
  target.querySelector("summary").focus();
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

function humanizeWorldName(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function singularWorldName(value) {
  const names = { meetings: "meeting", messages: "message", rows: "row" };
  return names[value] || (value.endsWith("s") ? value.slice(0, -1) : value);
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
    for (const [index, assertion] of assertions.entries()) {
      const explicitlyExcluded = assertion.params?.excluded === true || assertion.params?.scored === false;
      const statusName = assertion.excluded ? "excluded" : assertion.passed ? "passed" : "failed";
      const item = document.createElement("details");
      item.className = `assertion-result assertion-${statusName}`;
      item.dataset.assertionStatus = statusName;
      item.dataset.assertionIndex = index;
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
    ["Runtime", sessionRuntime(session).label],
    ["Runtime version", sessionRuntime(session).version],
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

  const lifecycleTitles = {
    planning: "Planning",
    plan_created: "Plan created",
    step_started: "Step started",
    step_retry: "Step retry",
    replan: "Plan replaced",
    review: "Planner review",
    protocol_correction: "Protocol correction",
    protocol_error: "Protocol error",
    provider_retry: "Provider retry",
    model_error: "Model error",
    budget_exhausted: "Budget exhausted",
    cancellation: "Cancellation",
  };

  for (const event of events) {
    if (event.kind in lifecycleTitles) {
      const lifecycle = traceNode(event.kind, lifecycleTitles[event.kind], nodeState(session, event), event.correlation_id);
      addEvidence(lifecycle, "Details", event.content);
      addEvidence(lifecycle, "Duration", event.duration_ms == null ? null : `${event.duration_ms} ms`);
      elements.trace.append(lifecycle);
    } else if (["model_turn", "executor_turn"].includes(event.kind)) {
      const title = event.kind === "executor_turn" ? "Executor turn" : "Assistant turn";
      const turn = traceNode(event.kind, title, nodeState(session, event), event.correlation_id);
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
  elements.inspector.querySelectorAll("summary").forEach((summary) => {
    summary.tabIndex = 0;
  });
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

function setHistoryCollapsed(collapsed) {
  elements.historyPanel.classList.toggle("collapsed", collapsed);
  elements.appShell.classList.toggle("history-collapsed", collapsed);
  elements.historyContent.hidden = collapsed;
  elements.historyToggle.textContent = collapsed ? ">" : "<";
  elements.historyToggle.setAttribute("aria-expanded", String(!collapsed));
  const action = collapsed ? "Expand" : "Collapse";
  elements.historyToggle.setAttribute("aria-label", `${action} history`);
  elements.historyToggle.title = `${action} history`;
  applyPaneWidths();
}

function closeResponsiveDrawer(restoreFocus = true) {
  if (!openDrawer) return;
  const panel = openDrawer;
  const trigger = drawerTrigger;
  panel.classList.remove("drawer-open");
  panel.setAttribute("aria-hidden", "true");
  panel.removeAttribute("aria-modal");
  panel.removeAttribute("role");
  elements.drawerBackdrop.hidden = true;
  document.body.classList.remove("drawer-active");
  elements.openHistory.setAttribute("aria-expanded", "false");
  elements.openInspector.setAttribute("aria-expanded", "false");
  openDrawer = null;
  drawerTrigger = null;
  if (restoreFocus) trigger?.focus();
}

function openResponsiveDrawer(panel, trigger, closeButton) {
  if (!narrowLayout.matches) return;
  closeResponsiveDrawer(false);
  openDrawer = panel;
  drawerTrigger = trigger;
  panel.classList.add("drawer-open");
  panel.setAttribute("aria-hidden", "false");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("role", "dialog");
  elements.drawerBackdrop.hidden = false;
  document.body.classList.add("drawer-active");
  trigger.setAttribute("aria-expanded", "true");
  closeButton.focus();
}

function openDrawerFromKeyboard(event, panel, trigger, closeButton) {
  if (!["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  openResponsiveDrawer(panel, trigger, closeButton);
  window.setTimeout(() => closeButton.focus(), 50);
}

function syncResponsiveLayout() {
  closeResponsiveDrawer(false);
  if (narrowLayout.matches) {
    setHistoryCollapsed(false);
    elements.historyPanel.setAttribute("aria-hidden", "true");
    elements.inspector.setAttribute("aria-hidden", "true");
    return;
  }
  elements.historyPanel.removeAttribute("aria-hidden");
  elements.inspector.removeAttribute("aria-hidden");
  elements.historyPanel.removeAttribute("aria-modal");
  elements.historyPanel.removeAttribute("role");
  elements.inspector.removeAttribute("aria-modal");
  elements.inspector.removeAttribute("role");
  setHistoryCollapsed(mediumLayout.matches);
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

function renderRuntimePicker(payload) {
  state.runtimes = payload.runtimes;
  state.selectedRuntimeId = payload.default_runtime_id;
  elements.runtimePicker.replaceChildren();
  for (const runtime of state.runtimes) {
    const option = document.createElement("option");
    option.value = runtime.id;
    option.textContent = runtime.label;
    option.title = `${runtime.label} · ${runtime.version}`;
    elements.runtimePicker.append(option);
  }
  elements.runtimePicker.value = state.selectedRuntimeId;
  syncRuntimePicker();
}

function syncRuntimePicker() {
  const active = Boolean(state.activeSessionId);
  elements.runtimePicker.disabled = active;
  elements.runtimePicker.title = active
    ? "The runtime is frozen for the active session"
    : "Choose the runtime for the next session";
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
      body: JSON.stringify({
        task_id: task.task_id,
        runtime_id: state.selectedRuntimeId,
      }),
    });
    state.activeSessionId = summary.session_id;
    syncRuntimePicker();
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
  details.textContent = `${session.runtime_label} · ${new Date(session.created_at).toLocaleString()} | ${score}`;
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
  syncRuntimePicker();
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
  elements.sessionRuntimeLabel.textContent = sessionRuntime(session).label;
  elements.sessionStatus.textContent = session.status;
  elements.sessionStatus.className = `status-badge ${session.status.toLowerCase()}`;
  renderPlan(session);

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
      const completed = await fetchSession(session.session_id);
      renderSession(completed);
      await refreshHistory();
    }
    elements.connection.textContent = `${state.tasks.length} tasks ready`;
  });
  source.onerror = async () => {
    if (state.selectedSession?.session_id !== session.session_id) return;
    const materialized = await fetchSession(session.session_id);
    renderSession(materialized);
    if (materialized.status !== "Running") {
      closeEventStream();
      await refreshHistory();
    }
  };
}

async function loadSession(sessionId) {
  closeEventStream();
  const session = await fetchSession(sessionId);
  renderSession(session);
  if (narrowLayout.matches && openDrawer === elements.historyPanel) {
    closeResponsiveDrawer(false);
    elements.sessionTaskName.focus();
  }
  if (session.status === "Running") {
    streamSession(session);
  } else {
    await refreshHistory();
  }
}

async function fetchSession(sessionId) {
  const [session, evidence] = await Promise.all([
    api(`/api/sessions/${sessionId}`),
    api(`/api/sessions/${sessionId}/world-changes`),
  ]);
  state.worldChanges.set(sessionId, evidence.changes);
  return session;
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
elements.runtimePicker.addEventListener("change", () => {
  state.selectedRuntimeId = elements.runtimePicker.value;
});
elements.historySearch.addEventListener("input", renderHistory);
elements.returnActive.addEventListener("click", () => loadSession(state.activeSessionId));
elements.stopRun.addEventListener("click", stopActiveRun);
elements.historyToggle.addEventListener("click", () => {
  setHistoryCollapsed(!elements.historyPanel.classList.contains("collapsed"));
});
elements.openHistory.addEventListener("click", (event) => {
  event.preventDefault();
  if (openDrawer !== elements.historyPanel) {
    openResponsiveDrawer(elements.historyPanel, elements.openHistory, elements.closeHistory);
  }
});
elements.openHistory.addEventListener("keydown", (event) => {
  openDrawerFromKeyboard(
    event,
    elements.historyPanel,
    elements.openHistory,
    elements.closeHistory,
  );
});
elements.openInspector.addEventListener("click", (event) => {
  event.preventDefault();
  if (openDrawer !== elements.inspector) {
    openResponsiveDrawer(elements.inspector, elements.openInspector, elements.closeInspector);
  }
});
elements.openInspector.addEventListener("keydown", (event) => {
  openDrawerFromKeyboard(
    event,
    elements.inspector,
    elements.openInspector,
    elements.closeInspector,
  );
});
elements.closeHistory.addEventListener("click", () => closeResponsiveDrawer());
elements.closeInspector.addEventListener("click", () => closeResponsiveDrawer());
elements.drawerBackdrop.addEventListener("click", () => closeResponsiveDrawer());
elements.historyResizer.addEventListener("pointerdown", (event) => {
  beginPaneResize(event, "history", elements.historyResizer);
});
elements.inspectorResizer.addEventListener("pointerdown", (event) => {
  beginPaneResize(event, "inspector", elements.inspectorResizer);
});
elements.historyResizer.addEventListener("keydown", (event) => {
  resizePaneFromKeyboard(event, "history");
});
elements.inspectorResizer.addEventListener("keydown", (event) => {
  resizePaneFromKeyboard(event, "inspector");
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && openDrawer) closeResponsiveDrawer();
  if (event.key === "Tab" && openDrawer) {
    const focusable = [...openDrawer.querySelectorAll("button, input, summary")]
      .filter((element) => !element.disabled && element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable.at(-1);
    if (first && last) {
      if (event.shiftKey && (document.activeElement === first || !openDrawer.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !openDrawer.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }
  }
  if (
    ["Enter", " "].includes(event.key)
    && event.target instanceof HTMLElement
    && event.target.matches("details > summary")
  ) {
    event.preventDefault();
    event.target.parentElement.open = !event.target.parentElement.open;
  }
});
narrowLayout.addEventListener("change", syncResponsiveLayout);
mediumLayout.addEventListener("change", syncResponsiveLayout);
window.addEventListener("resize", applyPaneWidths);

async function initialize() {
  try {
    const [taskPayload, runtimePayload, sessionPayload] = await Promise.all([
      api("/api/tasks"),
      api("/api/runtimes"),
      api("/api/sessions"),
    ]);
    state.tasks = taskPayload.tasks;
    state.sessions = sessionPayload.sessions;
    state.activeSessionId = state.sessions.find((session) => session.status === "Running")?.session_id || null;
    renderRuntimePicker(runtimePayload);
    const active = state.sessions.find((session) => session.status === "Running");
    if (active?.runtime_id) {
      state.selectedRuntimeId = active.runtime_id;
      elements.runtimePicker.value = active.runtime_id;
    }
    syncRuntimePicker();
    renderTasks();
    renderHistory();
    elements.connection.textContent = `${state.tasks.length} tasks ready`;
    if (active) await loadSession(active.session_id);
  } catch (error) {
    elements.connection.textContent = "Unavailable";
    showToast(error.message);
  }
}

syncResponsiveLayout();
applyPaneWidths();
initialize();
