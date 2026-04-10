const API_BASE = "";

let sessionId = null;
let currentObservation = null;
let selectedArtifactId = null;

const presets = {
  pagination: {
    task_id: "pagination-regression",
    title: "Still missing page validation",
    file: "utils/pagination.py",
    severity: "medium",
    line: "start = (page - 1) * page_size",
    rationale: "The off-by-one fix is correct, but page 0 or negative values still produce negative slicing from the end of the list and return the wrong results.",
    recommendation: "Validate page >= 1 before computing slice boundaries and raise ValueError for invalid page numbers.",
  },
  auth: {
    task_id: "tenant-export-auth",
    title: "Export route is missing authz guards",
    file: "api/admin_exports.py",
    severity: "critical",
    line: "export_invoices",
    rationale: "The handler trusts account_id from the query string and never calls require_admin or require_account_scope, so another tenant's invoices can be exported.",
    recommendation: "Call require_admin and require_account_scope before reading account_id or invoking invoice_repo.export_csv.",
  },
  refund: {
    task_id: "refund-idempotency",
    title: "Retry path can send duplicate refunds",
    file: "workers/refunds.py",
    severity: "critical",
    line: "process_refund",
    rationale: "The timeout branch calls the payment processor again without a persisted idempotency key, so concurrent workers or timeout-after-success cases can issue a second refund.",
    recommendation: "Persist an idempotency_key on the refund row, reuse it on every retry, and claim the job before calling the processor.",
  },
};

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-load-new").addEventListener("click", () => loadEpisode());
  document.getElementById("btn-submit").addEventListener("click", submitFinding);
  document.querySelectorAll("[data-preset]").forEach((button) => {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  });

  checkHealth();
  loadEpisode();
});

async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    const data = await response.json();
    const dot = document.getElementById("status-dot");
    const text = document.getElementById("status-text");
    if (data.status === "ok") {
      dot.classList.add("status-dot--live");
      text.textContent = "Live";
    } else {
      text.textContent = "Degraded";
    }
  } catch (error) {
    document.getElementById("status-text").textContent = "Offline";
  }
}

async function loadEpisode(overrideTaskId = null) {
  try {
    let taskId = overrideTaskId;
    if (!taskId) {
       const selector = document.getElementById("task-selector");
       if (selector) taskId = selector.value;
    }
    const response = await fetch(`${API_BASE}/reset`, { 
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(taskId ? { task_id: taskId } : {})
    });
    const data = await response.json();
    sessionId = data.session_id;
    currentObservation = data.observation;
    selectedArtifactId = currentObservation.opened_artifacts[0]?.artifact_id || currentObservation.available_artifacts[0]?.artifact_id || null;
    renderObservation(currentObservation);
    resetResultPanels();
    clearForm();
  } catch (error) {
    document.getElementById("task-title").textContent = "Failed to load task";
    document.getElementById("task-summary").textContent = "The backend did not respond to /reset.";
  }
}

function renderObservation(observation) {
  document.getElementById("task-title").textContent = observation.title;
  document.getElementById("task-id").textContent = observation.task_id;
  document.getElementById("task-difficulty").textContent = observation.difficulty;
  document.getElementById("task-step-limit").textContent = `${observation.step_limit} steps`;
  document.getElementById("task-summary").textContent = observation.summary;
  document.getElementById("steps-value").textContent = observation.metadata?.step_count ?? 0;
  document.getElementById("done-value").textContent = observation.done ? "Done" : "Active";
  document.getElementById("score-value").textContent = Number(observation.score || 0).toFixed(2);

  renderArtifacts(observation.available_artifacts || []);
  renderArtifactContent(observation, selectedArtifactId);
  renderList("events-list", observation.recent_events || [], "No events yet.");
}

function renderArtifacts(artifacts) {
  const container = document.getElementById("artifact-list");
  container.innerHTML = "";
  artifacts.forEach((artifact) => {
    const button = document.createElement("button");
    button.className = `artifact-chip${artifact.artifact_id === selectedArtifactId ? " artifact-chip--active" : ""}`;
    button.textContent = `${artifact.artifact_id} • ${artifact.kind}`;
    button.addEventListener("click", async () => {
      selectedArtifactId = artifact.artifact_id;
      if (!artifact.opened) {
        await openArtifact(artifact.artifact_id);
      } else {
        renderObservation(currentObservation);
      }
    });
    container.appendChild(button);
  });
}

function renderArtifactContent(observation, artifactId) {
  const artifact = (observation.available_artifacts || []).find((item) => item.artifact_id === artifactId)
    || observation.opened_artifacts?.[0]
    || observation.available_artifacts?.[0];
  if (!artifact) {
    document.getElementById("artifact-content").textContent = "No artifact available.";
    return;
  }
  const content = artifact.opened ? artifact.content : `${artifact.preview}\n\nClick the artifact to open full content.`;
  document.getElementById("artifact-content").textContent = content || artifact.preview || "No content available.";
}

async function openArtifact(artifactId) {
  const response = await fetch(`${API_BASE}/step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      action: {
        action_type: "open_artifact",
        artifact_id: artifactId,
      },
    }),
  });
  const data = await response.json();
  currentObservation = data.observation;
  renderObservation(currentObservation);
  updateReward(data.reward || 0, currentObservation.score || 0, currentObservation.done);
  renderBreakdown(currentObservation.metadata || {});
}

async function submitFinding() {
  const finding = buildFinding();
  if (!finding) {
    return;
  }

  const button = document.getElementById("btn-submit");
  button.disabled = true;
  button.textContent = "Submitting...";

  try {
    const response = await fetch(`${API_BASE}/step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        action: {
          action_type: "submit_review",
          findings: [finding],
        },
      }),
    });
    const data = await response.json();
    currentObservation = data.observation;
    renderObservation(currentObservation);
    updateReward(data.reward || 0, currentObservation.score || 0, currentObservation.done);
    renderBreakdown(currentObservation.metadata || {});
  } catch (error) {
    alert("Submission failed. Check the backend logs.");
  } finally {
    button.disabled = false;
    button.textContent = "Submit Review";
  }
}

function buildFinding() {
  const title = document.getElementById("finding-title").value.trim();
  const filePath = document.getElementById("finding-file").value.trim();
  const lineHint = document.getElementById("finding-line").value.trim();
  const severity = document.getElementById("finding-severity").value;
  const rationale = document.getElementById("finding-rationale").value.trim();
  const recommendation = document.getElementById("finding-recommendation").value.trim();

  if (!title || !filePath || !rationale || !recommendation) {
    alert("Fill title, file path, rationale, and recommendation before submitting.");
    return null;
  }

  return {
    title,
    file_path: filePath,
    line_hint: lineHint || null,
    severity,
    rationale,
    recommendation,
  };
}

async function applyPreset(name) {
  const preset = presets[name];
  if (!preset) {
    return;
  }
  
  if (!currentObservation || currentObservation.task_id !== preset.task_id) {
    const selector = document.getElementById("task-selector");
    if (selector) selector.value = preset.task_id;
    await loadEpisode(preset.task_id);
  }

  document.getElementById("finding-title").value = preset.title;
  document.getElementById("finding-file").value = preset.file;
  document.getElementById("finding-severity").value = preset.severity;
  document.getElementById("finding-line").value = preset.line;
  document.getElementById("finding-rationale").value = preset.rationale;
  document.getElementById("finding-recommendation").value = preset.recommendation;
}

function clearForm() {
  document.getElementById("finding-title").value = "";
  document.getElementById("finding-file").value = "";
  document.getElementById("finding-severity").value = "medium";
  document.getElementById("finding-line").value = "";
  document.getElementById("finding-rationale").value = "";
  document.getElementById("finding-recommendation").value = "";
}

function updateReward(reward, score, done) {
  document.getElementById("reward-value").textContent = Number(reward).toFixed(2);
  document.getElementById("score-value").textContent = Number(score).toFixed(2);
  document.getElementById("done-value").textContent = done ? "Done" : "Active";
}

function renderBreakdown(metadata) {
  const components = metadata.reward_breakdown || {};
  const graderDetails = metadata.grader_details || [];
  renderList(
    "criteria-list",
    graderDetails.map((detail) => `${detail.criterion_id}: ${detail.score}`),
    "No graded criteria yet."
  );
  renderList(
    "components-list",
    Object.entries(components).map(([key, value]) => `${key}: ${value}`),
    "No reward components yet."
  );
}

function renderList(elementId, items, emptyText) {
  const list = document.getElementById(elementId);
  list.innerHTML = "";
  if (!items.length) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    list.appendChild(item);
    return;
  }
  items.forEach((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    list.appendChild(item);
  });
}

function resetResultPanels() {
  updateReward(0, 0, false);
  renderList("criteria-list", [], "No graded criteria yet.");
  renderList("components-list", [], "No reward components yet.");
}
