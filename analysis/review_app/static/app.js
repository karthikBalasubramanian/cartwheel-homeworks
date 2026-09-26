/* Cartwheel Review App - Frontend Application Logic */

const AppState = {
  sessions: [],
  currentIndex: 0,
  currentSession: null,
  taxonomy: [],
  currentAnnotation: {
    verdict: null,
    note: "",
    modes: {},
    step_notes: {},
  },
  progress: null,
  filter: "candidates_unverified_store_override",
  activeCandidates: {},
  candidateStats: null,
};

// Initialize App
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  await loadTaxonomy();
  await loadSessions();

  if (AppState.filter.startsWith("candidates_")) {
    await loadActiveCandidates(AppState.filter.replace("candidates_", ""));
    renderSidebarList();
  }

  // Check URL query parameters
  const urlParams = new URLSearchParams(window.location.search);
  const scenarioParam = urlParams.get("scenario");
  const sessionParam = urlParams.get("session");

  if (scenarioParam) {
    await loadByScenarioId(scenarioParam);
  } else if (sessionParam) {
    await loadBySessionId(sessionParam);
  } else if (AppState.sessions.length > 0) {
    const filtered = getFilteredSessions();
    if (filtered.length > 0) {
      await loadBySessionId(filtered[0].session_id);
    } else {
      await selectSessionByIndex(0);
    }
  }
});

// Setup Global Keyboard & Event Listeners
function setupEventListeners() {
  const scenarioInput = document.getElementById("scenario-input");
  scenarioInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const val = scenarioInput.value.trim();
      if (val) {
        loadByScenarioId(val);
      }
    }
  });

  const filterSelect = document.getElementById("filter-select");
  if (filterSelect) {
    filterSelect.addEventListener("change", async (e) => {
      AppState.filter = e.target.value;
      if (AppState.filter.startsWith("candidates_")) {
        const mode = AppState.filter.replace("candidates_", "");
        await loadActiveCandidates(mode);
      }
      renderSidebarList();
      const filtered = getFilteredSessions();
      if (filtered.length > 0) {
        const isCurrentInFiltered = filtered.some((s) => s.session_id === (AppState.currentSession && AppState.currentSession.session_id));
        if (!isCurrentInFiltered) {
          loadBySessionId(filtered[0].session_id);
        }
      }
    });
  }

  document.getElementById("btn-prev").addEventListener("click", () => navigate(-1));
  document.getElementById("btn-next").addEventListener("click", () => navigate(1));
  document.getElementById("btn-save-advance").addEventListener("click", () => saveAndAdvance());

  // Global Keyboard Shortcuts
  window.addEventListener("keydown", (e) => {
    // Ignore shortcuts when typing inside input or textarea
    const tag = e.target.tagName.toLowerCase();
    if (tag === "input" || tag === "textarea") {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        saveAndAdvance();
      }
      return;
    }

    if (e.key === "j" || e.key === "J") {
      e.preventDefault();
      navigate(1);
    } else if (e.key === "k" || e.key === "K") {
      e.preventDefault();
      navigate(-1);
    } else if (e.key === "p" || e.key === "P") {
      e.preventDefault();
      setVerdict("pass");
    } else if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      setVerdict("fail");
    } else if (e.key === "d" || e.key === "D") {
      e.preventDefault();
      setVerdict("defer");
    } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      saveAndAdvance();
    }
  });

  // Note change listener
  const notesTextarea = document.getElementById("notes-input");
  notesTextarea.addEventListener("input", (e) => {
    AppState.currentAnnotation.note = e.target.value;
  });
}

// Data Fetching
async function loadSessions() {
  try {
    const res = await fetch("/api/sessions");
    const data = await res.json();
    AppState.sessions = data.sessions || [];
    renderSidebarList();
    await updateProgress();
  } catch (err) {
    console.error("Failed to load sessions:", err);
  }
}

async function loadActiveCandidates(mode) {
  try {
    const res = await fetch(`/api/candidates?mode=${encodeURIComponent(mode)}&k=40`);
    if (res.ok) {
      const data = await res.json();
      AppState.activeCandidates[mode] = data.candidates || [];
      AppState.candidateStats = data.stats;
    }
  } catch (err) {
    console.error("Failed to load candidates:", err);
  }
}

async function loadTaxonomy() {
  try {
    const res = await fetch("/api/taxonomy");
    const data = await res.json();
    AppState.taxonomy = Array.isArray(data.modes) ? data.modes : [];
    renderTaxonomySection();
  } catch (err) {
    console.error("Failed to load taxonomy:", err);
  }
}

async function updateProgress() {
  try {
    const res = await fetch("/api/progress");
    const data = await res.json();
    AppState.progress = data;
    const progressPill = document.getElementById("progress-count");
    if (progressPill) {
      progressPill.textContent = `${data.reviewed_count} / 100 Reviewed (${data.total_sessions} total)`;
    }
  } catch (err) {
    console.error("Failed to update progress:", err);
  }
}

async function loadByScenarioId(scenarioId) {
  try {
    const cleanId = scenarioId.trim();
    const res = await fetch(`/api/scenario/${encodeURIComponent(cleanId)}`);
    if (!res.ok) {
      alert(`Scenario ${cleanId} not found`);
      return;
    }
    const sessionData = await res.json();
    const idx = AppState.sessions.findIndex((s) => s.session_id === sessionData.session_id);
    if (idx !== -1) {
      AppState.currentIndex = idx;
    }
    displaySession(sessionData);
  } catch (err) {
    console.error("Failed to load scenario:", err);
  }
}

async function loadBySessionId(sessionId) {
  try {
    const res = await fetch(`/api/session/${encodeURIComponent(sessionId)}`);
    if (!res.ok) return;
    const sessionData = await res.json();
    displaySession(sessionData);
  } catch (err) {
    console.error("Failed to load session:", err);
  }
}

async function selectSessionByIndex(idx) {
  if (idx < 0 || idx >= AppState.sessions.length) return;
  AppState.currentIndex = idx;
  const sessionSummary = AppState.sessions[idx];
  await loadBySessionId(sessionSummary.session_id);
}

function navigate(delta) {
  const newIndex = AppState.currentIndex + delta;
  if (newIndex >= 0 && newIndex < AppState.sessions.length) {
    selectSessionByIndex(newIndex);
  }
}

// Display Session Content
function displaySession(sessionData) {
  AppState.currentSession = sessionData;

  // Update URL without reload
  const url = new URL(window.location);
  url.searchParams.set("scenario", sessionData.scenario_id);
  window.history.replaceState({}, "", url);

  // Update Header Inputs
  const scenarioInput = document.getElementById("scenario-input");
  scenarioInput.value = sessionData.scenario_id;

  // Restore current annotation
  const existingAnn = (sessionData.annotations && sessionData.annotations[0]) || null;
  AppState.currentAnnotation = {
    session_id: sessionData.session_id,
    scenario_id: sessionData.scenario_id,
    trace_id: (sessionData.trace_ids && sessionData.trace_ids[0]) || sessionData.session_id,
    verdict: existingAnn ? (existingAnn.verdict || (existingAnn.label === 1 ? "pass" : existingAnn.label === 0 ? "fail" : null)) : null,
    note: existingAnn ? existingAnn.note || "" : "",
    modes: existingAnn && existingAnn.modes ? { ...existingAnn.modes } : {},
    step_notes: existingAnn && existingAnn.step_notes ? { ...existingAnn.step_notes } : {},
  };

  renderConversation(sessionData);
  renderAnnotationPanel();
  highlightActiveSidebarItem(sessionData.session_id);
}

// Collate inline notes into the right panel
function syncCollatedNotes() {
  const stepNotes = AppState.currentAnnotation.step_notes || {};
  const entries = Object.entries(stepNotes).filter(([_, val]) => val && val.text && val.text.trim());

  let lines = [];
  entries.forEach(([key, val]) => {
    const prefix = val.is_first_failure ? `[FIRST FAILURE - ${val.label || key}]` : `[${val.label || key}]`;
    lines.push(`${prefix}: ${val.text.trim()}`);
  });

  const collated = lines.join("\n\n");
  AppState.currentAnnotation.note = collated;
  const notesTextarea = document.getElementById("notes-input");
  if (notesTextarea) {
    notesTextarea.value = collated;
  }
}

// Render Left Pane
function renderConversation(session) {
  const container = document.getElementById("conversation-stream");
  container.innerHTML = "";

  // Banner
  const banner = document.createElement("div");
  banner.className = "session-meta-banner";
  banner.innerHTML = `
    <div class="meta-title-group">
      <span class="meta-scenario-id">${session.scenario_id}</span>
      <span class="role-badge role-${session.user_role}">${session.user_role}</span>
      <span style="font-size: 12px; color: var(--text-secondary);">User ID: ${session.user_id}</span>
      <span style="font-size: 12px; color: var(--text-muted);">Turns: ${session.turn_count} &bull; <strong style="color: #a78bfa;">${session.total_spans || 0} Spans</strong> (${session.tool_spans || 0} tool, ${session.gen_spans || 0} gen)</span>
    </div>
    <div>
      ${
        session.has_permission_denied
          ? `<span class="security-denied-badge">⚠️ Security Refusal (Permission Denied)</span>`
          : `<span style="font-size: 12px; color: var(--accent-emerald);">● Standard Access</span>`
      }
    </div>
  `;
  container.appendChild(banner);

  const stepNotes = AppState.currentAnnotation.step_notes || {};

  // Turns
  session.turns.forEach((turn, turnIdx) => {
    const turnDiv = document.createElement("div");
    turnDiv.className = "turn-container";

    let html = `<div class="turn-header">Turn ${turn.turn_index} of ${session.turn_count} &bull; Trace: ${turn.trace_id.slice(0, 8)}... &bull; <span style="color: #a78bfa; font-weight: 600;">🏷️ ${turn.span_count || 0} spans</span> (${turn.tool_span_count || 0} tool, ${turn.generation_span_count || 0} gen)</div>`;

    // System Prompt Accordion
    if (turn.system_prompt) {
      html += `
        <details class="system-details">
          <summary>System Prompt & Guidance (${turn.system_prompt.length} chars)</summary>
          <pre>${escapeHtml(turn.system_prompt)}</pre>
        </details>
      `;
    }

    // User Message
    if (turn.user_input) {
      html += `
        <div class="message-bubble user-bubble">
          <div style="font-size: 11px; font-weight: 700; color: var(--accent-blue); margin-bottom: 4px;">USER (${session.user_role.toUpperCase()} #${session.user_id})</div>
          <div>${escapeHtml(turn.user_input)}</div>
        </div>
      `;
    }

    // Steps (Tool Calls & Results)
    if (turn.steps && turn.steps.length > 0) {
      turn.steps.forEach((step, stepIdx) => {
        if (step.reasoning) {
          const delibKey = `turn_${turnIdx}_delib_${stepIdx}`;
          const curNote = stepNotes[delibKey] || { text: "", is_first_failure: false };
          const hasNote = !!(curNote.text && curNote.text.trim());
          const isFirst = !!curNote.is_first_failure;

          html += `
            <div class="deliberation-card">
              <div class="deliberation-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span>🧠 Deliberation & Intent</span>
                  <span class="deliberation-badge">Internal Reasoning</span>
                </div>
                <button class="inline-note-btn ${hasNote ? "has-note" : ""} ${isFirst ? "has-first-failure" : ""}" data-step-key="${delibKey}">
                  ${isFirst ? "🎯 Earliest Failure" : hasNote ? "💬 Note (1)" : "+ Note"}
                </button>
              </div>
              <div class="deliberation-body">${escapeHtml(step.reasoning)}</div>
              <div class="inline-note-container" id="box-${delibKey}" style="display: ${hasNote ? "flex" : "none"};">
                <div class="inline-note-toolbar">
                  <span class="inline-note-label">Observation on Deliberation:</span>
                  <label class="first-failure-pill">
                    <input type="checkbox" class="first-failure-cb" data-step-key="${delibKey}" data-label="Turn ${turn.turn_index} Deliberation" ${isFirst ? "checked" : ""}>
                    <span>🎯 Earliest Material Failure</span>
                  </label>
                </div>
                <textarea class="inline-note-textarea" data-step-key="${delibKey}" data-label="Turn ${turn.turn_index} Deliberation" placeholder="Describe reasoning issue (e.g. flawed assumption, leaking internal terms, ignoring user goal)...">${escapeHtml(curNote.text || "")}</textarea>
              </div>
            </div>
          `;
        }

        const isDenied = step.permission_denied;
        const toolKey = `turn_${turnIdx}_tool_${stepIdx}_${step.tool_name || "call"}`;
        const curToolNote = stepNotes[toolKey] || { text: "", is_first_failure: false };
        const hasToolNote = !!(curToolNote.text && curToolNote.text.trim());
        const isToolFirst = !!curToolNote.is_first_failure;

        let statusBadge = "";
        if (step.output && typeof step.output === "object") {
          const statusVal = step.output.status || (step.output.order && step.output.order.status);
          if (statusVal) {
            const isOk = statusVal === "auto_approved" || statusVal === "delivered" || statusVal === "shipped";
            const isWarn = statusVal === "queued_for_approval" || statusVal === "pending";
            const color = isOk ? "var(--accent-emerald)" : isWarn ? "var(--accent-amber)" : "var(--accent-rose)";
            const bg = isOk ? "rgba(16, 185, 129, 0.12)" : isWarn ? "rgba(245, 158, 11, 0.12)" : "rgba(244, 63, 94, 0.12)";
            statusBadge = `<span style="font-family: var(--font-mono); font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: ${bg}; color: ${color};">status: ${escapeHtml(statusVal)}</span>`;
          } else if (step.output.ok === false || step.output.error) {
            statusBadge = `<span style="font-family: var(--font-mono); font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: rgba(244, 63, 94, 0.15); color: var(--accent-rose);">error: ${escapeHtml(step.output.error || "failed")}</span>`;
          } else if (step.output.ok === true) {
            statusBadge = `<span style="font-family: var(--font-mono); font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: rgba(16, 185, 129, 0.12); color: var(--accent-emerald);">ok: true</span>`;
          }
        }

        html += `
          <div class="tool-card ${isDenied ? "denied" : ""}">
            <div class="tool-header-row">
              <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <div class="tool-name-badge">🛠️ ${step.tool_name}(${formatArgs(step.arguments)})</div>
                ${statusBadge}
              </div>
              <div style="display: flex; gap: 8px; align-items: center;">
                ${
                  isDenied
                    ? `<span class="security-denied-badge">Permission Refused</span>`
                    : `<span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${(step.latency || 0).toFixed(3)}s</span>`
                }
                <button class="inline-note-btn ${hasToolNote ? "has-note" : ""} ${isToolFirst ? "has-first-failure" : ""}" data-step-key="${toolKey}">
                  ${isToolFirst ? "🎯 Earliest Failure" : hasToolNote ? "💬 Note (1)" : "+ Note"}
                </button>
              </div>
            </div>
            ${
              step.permission_denied_reason
                ? `<div style="font-size: 12px; color: #fb7185; margin-bottom: 6px;"><strong>Refusal Reason:</strong> ${escapeHtml(step.permission_denied_reason)}</div>`
                : ""
            }
            <details open>
              <summary style="font-size: 11px; color: var(--text-muted); cursor: pointer; padding: 2px 0;">Tool Response Ground Truth</summary>
              <pre class="tool-payload">${escapeHtml(JSON.stringify(step.output, null, 2))}</pre>
            </details>
            <div class="inline-note-container" id="box-${toolKey}" style="display: ${hasToolNote ? "flex" : "none"};">
              <div class="inline-note-toolbar">
                <span class="inline-note-label">Observation on Tool (${step.tool_name}):</span>
                <label class="first-failure-pill">
                  <input type="checkbox" class="first-failure-cb" data-step-key="${toolKey}" data-label="Turn ${turn.turn_index} Tool (${step.tool_name})" ${isToolFirst ? "checked" : ""}>
                  <span>🎯 Earliest Material Failure</span>
                </label>
              </div>
              <textarea class="inline-note-textarea" data-step-key="${toolKey}" data-label="Turn ${turn.turn_index} Tool (${step.tool_name})" placeholder="Describe tool call issue (e.g. unnecessary tool call, wrong parameters, hallucinated output)...">${escapeHtml(curToolNote.text || "")}</textarea>
            </div>
          </div>
        `;
      });
    }

    // Final Assistant Response
    if (turn.final_reply) {
      const replyKey = `turn_${turnIdx}_reply`;
      const curReplyNote = stepNotes[replyKey] || { text: "", is_first_failure: false };
      const hasReplyNote = !!(curReplyNote.text && curReplyNote.text.trim());
      const isReplyFirst = !!curReplyNote.is_first_failure;

      html += `
        <div class="message-bubble assistant-bubble">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--accent-emerald); text-transform: uppercase; letter-spacing: 0.5px;">Assistant Response</div>
            <button class="inline-note-btn ${hasReplyNote ? "has-note" : ""} ${isReplyFirst ? "has-first-failure" : ""}" data-step-key="${replyKey}">
              ${isReplyFirst ? "🎯 Earliest Failure" : hasReplyNote ? "💬 Note (1)" : "+ Note"}
            </button>
          </div>
          <div style="white-space: pre-wrap;">${renderMarkdownLite(turn.final_reply)}</div>
          <div class="inline-note-container" id="box-${replyKey}" style="display: ${hasReplyNote ? "flex" : "none"};">
            <div class="inline-note-toolbar">
              <span class="inline-note-label">Observation on Assistant Response:</span>
              <label class="first-failure-pill">
                <input type="checkbox" class="first-failure-cb" data-step-key="${replyKey}" data-label="Turn ${turn.turn_index} Assistant Response" ${isReplyFirst ? "checked" : ""}>
                <span>🎯 Earliest Material Failure</span>
              </label>
            </div>
            <textarea class="inline-note-textarea" data-step-key="${replyKey}" data-label="Turn ${turn.turn_index} Assistant Response" placeholder="Describe response issue (e.g. premature success claim, misquoted policy, unprompted cancellation)...">${escapeHtml(curReplyNote.text || "")}</textarea>
          </div>
        </div>
      `;
    }

    // Metrics Bar
    const m = turn.metrics || {};
    html += `
      <div class="turn-metrics-bar">
        <span>⏱️ Latency: ${(turn.latency || 0).toFixed(2)}s</span>
        <span>🧠 Reasoning Tokens: ${m.reasoning_tokens || 0}</span>
        <span>⚡ Cached Tokens: ${m.cached_tokens || 0}</span>
        <span>📊 Total Tokens: ${m.total_tokens || 0}</span>
      </div>
    `;

    turnDiv.innerHTML = html;
    container.appendChild(turnDiv);
  });

  // Attach event listeners for inline note toggles and text inputs
  container.querySelectorAll(".inline-note-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.stepKey;
      const box = document.getElementById("box-" + key);
      if (!box) return;
      const isVisible = box.style.display === "flex";
      box.style.display = isVisible ? "none" : "flex";
      if (!isVisible) {
        const ta = box.querySelector(".inline-note-textarea");
        if (ta) ta.focus();
      }
    });
  });

  container.querySelectorAll(".inline-note-textarea").forEach((ta) => {
    ta.addEventListener("input", (e) => {
      const key = ta.dataset.stepKey;
      const label = ta.dataset.label;
      const box = document.getElementById("box-" + key);
      const cb = box ? box.querySelector(".first-failure-cb") : null;
      const isFirst = cb ? cb.checked : false;
      const val = e.target.value;

      if (!AppState.currentAnnotation.step_notes) {
        AppState.currentAnnotation.step_notes = {};
      }
      AppState.currentAnnotation.step_notes[key] = {
        text: val,
        is_first_failure: isFirst,
        label: label,
      };

      const btn = container.querySelector(`.inline-note-btn[data-step-key="${key}"]`);
      if (btn) {
        btn.classList.toggle("has-note", !!val.trim());
      }
      syncCollatedNotes();
    });
  });

  container.querySelectorAll(".first-failure-cb").forEach((cb) => {
    cb.addEventListener("change", (e) => {
      const key = cb.dataset.stepKey;
      const label = cb.dataset.label;
      const box = document.getElementById("box-" + key);
      const ta = box ? box.querySelector(".inline-note-textarea") : null;
      const val = ta ? ta.value : "";

      if (!AppState.currentAnnotation.step_notes) {
        AppState.currentAnnotation.step_notes = {};
      }
      AppState.currentAnnotation.step_notes[key] = {
        text: val,
        is_first_failure: e.target.checked,
        label: label,
      };

      const btn = container.querySelector(`.inline-note-btn[data-step-key="${key}"]`);
      if (btn) {
        btn.classList.toggle("has-first-failure", e.target.checked);
      }

      if (e.target.checked) {
        setVerdict("fail");
      }
      syncCollatedNotes();
    });
  });
}

// Render Right Annotation Panel
function renderAnnotationPanel() {
  const ann = AppState.currentAnnotation;

  // Verdict buttons
  document.querySelectorAll(".btn-verdict").forEach((btn) => {
    btn.classList.remove("active-pass", "active-fail", "active-defer");
  });
  if (ann.verdict === "pass") {
    document.getElementById("btn-verdict-pass").classList.add("active-pass");
  } else if (ann.verdict === "fail") {
    document.getElementById("btn-verdict-fail").classList.add("active-fail");
  } else if (ann.verdict === "defer") {
    document.getElementById("btn-verdict-defer").classList.add("active-defer");
  }

  // Notes textarea
  document.getElementById("notes-input").value = ann.note || "";

  // Judge evaluation box
  renderJudgeEvaluation();

  // Taxonomy checkboxes
  renderTaxonomySection();
}

function renderJudgeEvaluation() {
  const box = document.getElementById("judge-eval-box");
  if (!box) return;
  const jeval = AppState.currentSession && AppState.currentSession.judge_evaluation;
  const split = AppState.currentSession && AppState.currentSession.split;

  if (!jeval) {
    if (split === "train" || split === "test") {
      box.style.display = "block";
      document.getElementById("judge-model-name").textContent = "No Evaluation";
      const splitBadge = document.getElementById("judge-split-badge");
      if (splitBadge) {
        splitBadge.textContent = split.toUpperCase();
        splitBadge.style.background = split === "train" ? "#10b981" : "#ef4444";
      }
      const verdictPill = document.getElementById("judge-verdict-pill");
      if (verdictPill) {
        verdictPill.textContent = "Status: Not Evaluated";
        verdictPill.style.background = "rgba(100, 116, 139, 0.2)";
        verdictPill.style.color = "#cbd5e1";
        verdictPill.style.border = "1px solid #475569";
      }
      const banner = document.getElementById("judge-match-banner");
      if (banner) banner.style.display = "none";
      const subtextNote = document.getElementById("judge-subtext-note");
      if (subtextNote) subtextNote.style.display = "none";
      const critiqueEl = document.getElementById("judge-critique-text");
      if (critiqueEl) {
        critiqueEl.textContent = "No judge evaluation has been run on this trace.";
      }
      return;
    }
    box.style.display = "none";
    return;
  }
  box.style.display = "block";
  const modeTargetEl = document.getElementById("judge-mode-target");
  if (modeTargetEl) modeTargetEl.textContent = jeval.mode || "unverified_store_override";
  document.getElementById("judge-model-name").textContent = `${jeval.model || 'gpt-4o-mini'} (${jeval.judge_id || 'v0'})`;
  const splitBadge = document.getElementById("judge-split-badge");
  if (splitBadge) {
    splitBadge.textContent = (jeval.split || 'DEV').toUpperCase();
    splitBadge.style.background = jeval.split === "dev" ? "#3b82f6" : jeval.split === "test" ? "#ef4444" : "#10b981";
  }

  const verdictPill = document.getElementById("judge-verdict-pill");
  if (verdictPill) {
    verdictPill.textContent = `Judge Verdict: ${jeval.judge_verdict}`;
    verdictPill.style.background = jeval.judge_verdict === "Pass" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)";
    verdictPill.style.color = jeval.judge_verdict === "Pass" ? "#34d399" : "#f87171";
    verdictPill.style.border = `1px solid ${jeval.judge_verdict === "Pass" ? "#10b981" : "#ef4444"}`;
  }

  const banner = document.getElementById("judge-match-banner");
  const subtextNote = document.getElementById("judge-subtext-note");
  if (banner) {
    banner.style.display = "block";
    if (jeval.is_disagreement) {
      banner.textContent = "⚠️ DISAGREEMENT — Human didn't agree with judge";
      banner.style.background = "rgba(245, 158, 11, 0.18)";
      banner.style.color = "#fbbf24";
      banner.style.border = "1px solid #f59e0b";
      if (subtextNote) subtextNote.style.display = "block";
    } else {
      banner.textContent = "✓ MATCH — Human and judge agreed";
      banner.style.background = "rgba(16, 185, 129, 0.18)";
      banner.style.color = "#34d399";
      banner.style.border = "1px solid #10b981";
      if (subtextNote) subtextNote.style.display = "none";
    }
  }

  const critiqueEl = document.getElementById("judge-critique-text");
  if (critiqueEl) {
    critiqueEl.textContent = jeval.critique || "No critique text available.";
  }
}

function renderTaxonomySection() {

  const container = document.getElementById("taxonomy-checkboxes");
  if (!container) return;
  container.innerHTML = "";

  const currSession = AppState.sessions.find(s => s.session_id === (AppState.currentSession && AppState.currentSession.session_id)) || AppState.sessions[AppState.currentIndex];
  const isBatch1or2 = (AppState.filter === "batch1" || AppState.filter === "batch2") ||
                      (currSession && (currSession.batch1 || currSession.batch2));

  if (isBatch1or2) {
    container.innerHTML = `
      <div style="font-size: 12px; color: var(--text-muted); padding: 12px; border: 1px dashed var(--border); border-radius: 6px; line-height: 1.5; background: rgba(99, 102, 241, 0.04);">
        <strong style="color: var(--accent-indigo, #818cf8); display: block; margin-bottom: 4px;">Phase 1: Open Coding Discovery (Batches 1 &amp; 2)</strong>
        Formal failure modes are withheld during open coding to prevent classification bias. Record freeform observations and verdict; taxonomy modes emerge during Axial Coding and are applied in Batches 3 &amp; 4.
      </div>
    `;
    return;
  }

  if (!AppState.taxonomy || AppState.taxonomy.length === 0) {
    container.innerHTML = `
      <div style="font-size: 12px; color: var(--text-muted); padding: 12px; border: 1px dashed var(--border); border-radius: 6px; line-height: 1.4;">
        <strong>Open Coding Mode:</strong> No formal taxonomy modes assigned yet.<br>
        Record raw failure notes and assign Verdict (Pass/Fail/Defer). Modes will be created from observations during Axial Coding.
      </div>
    `;
    return;
  }

  AppState.taxonomy.forEach((mode) => {
    const modeKey = mode.mode || mode.name || mode.id;
    const isChecked = !!(AppState.currentAnnotation.modes && AppState.currentAnnotation.modes[modeKey]);
    const item = document.createElement("label");
    item.className = `taxonomy-item ${isChecked ? "checked" : ""}`;
    item.innerHTML = `
      <input type="checkbox" data-mode-id="${modeKey}" ${isChecked ? "checked" : ""}>
      <div>
        <div style="font-weight: 600;">${mode.name || modeKey}</div>
        <div style="font-size: 11px; color: var(--text-muted);">${mode.description || mode.desc || ""}</div>
      </div>
    `;

    item.querySelector("input").addEventListener("change", (e) => {
      if (!AppState.currentAnnotation.modes) AppState.currentAnnotation.modes = {};
      AppState.currentAnnotation.modes[modeKey] = e.target.checked;
      item.classList.toggle("checked", e.target.checked);
    });

    container.appendChild(item);
  });
}

function setVerdict(v) {
  AppState.currentAnnotation.verdict = v;
  renderAnnotationPanel();
}

function toggleTaxonomyModeByIndex(idx) {
  if (idx < 0 || idx >= AppState.taxonomy.length) return;
  const mode = AppState.taxonomy[idx];
  const modeKey = mode.mode || mode.name || mode.id;
  if (!AppState.currentAnnotation.modes) AppState.currentAnnotation.modes = {};
  const curr = !!AppState.currentAnnotation.modes[modeKey];
  AppState.currentAnnotation.modes[modeKey] = !curr;
  renderTaxonomySection();
}

// Save Annotation and Advance
async function saveAndAdvance() {
  const ann = AppState.currentAnnotation;
  if (!ann || !ann.session_id) return;

  const payload = {
    session_id: ann.session_id,
    scenario_id: ann.scenario_id,
    trace_id: ann.trace_id,
    verdict: ann.verdict,
    label: ann.verdict === "pass" ? 1 : ann.verdict === "fail" ? 0 : null,
    note: ann.note,
    modes: ann.modes,
    step_notes: ann.step_notes,
    ts: new Date().toISOString(),
    author: "human",
  };

  try {
    const res = await fetch("/api/annotations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      // Update local sidebar indicator
      const sItem = AppState.sessions[AppState.currentIndex];
      if (sItem) {
        sItem.is_reviewed = true;
        sItem.verdict = ann.verdict;
        renderSidebarList();
      }
      if (AppState.filter.startsWith("candidates_")) {
        const mode = AppState.filter.replace("candidates_", "");
        await loadActiveCandidates(mode);
      }
      await updateProgress();
      // Advance to next
      navigate(1);
    }
  } catch (err) {
    console.error("Save failed:", err);
  }
}

function getFilteredSessions() {
  const f = AppState.filter;
  if (f.startsWith("candidates_")) {
    const mode = f.replace("candidates_", "");
    const candList = AppState.activeCandidates[mode] || [];
    const sessionMap = new Map(AppState.sessions.map((s) => [s.session_id, s]));
    const result = [];
    for (const c of candList) {
      const s = sessionMap.get(c.session_id);
      if (s) {
        s.candidate_signal = c.signal;
        result.push(s);
      }
    }
    return result;
  }
  return AppState.sessions.filter((s) => {
    if (f === "dev_disagreements") return !!s.is_disagreement && s.split === "dev";
    if (f === "dev_split") return s.split === "dev";
    if (f === "train_split") return s.split === "train";
    if (f === "test_split") return s.split === "test";
    if (f === "batch1") return !!s.batch1;
    if (f === "batch2") return !!s.batch2;
    if (f === "batch3") return !!s.batch3;
    if (f === "batch4") return !!s.batch4;
    if (f === "all") return true;
    if (f === "multi_turn") return s.turn_count > 1;
    if (f === "security") return s.has_permission_denied;
    if (f === "escalation") return s.has_escalation;
    if (f === "role_shopper") return s.user_role === "shopper";
    if (f === "role_merchant") return s.user_role === "merchant";
    if (f === "role_support") return s.user_role === "support";
    if (f === "refund") return s.tools_called && (s.tools_called.includes("issue_refund") || s.tools_called.includes("get_order"));
    if (f === "policy") return s.tools_called && (s.tools_called.includes("get_policy") || s.tools_called.includes("search_help_center"));
    if (f === "unreviewed") return !s.is_reviewed;
    if (f === "reviewed") return s.is_reviewed;
    return true;
  });
}

// Render Sidebar List
function renderSidebarList() {
  const list = document.getElementById("session-list-items");
  if (!list) return;
  list.innerHTML = "";

  const filtered = getFilteredSessions();
  const countEl = document.getElementById("filtered-count");
  const statsEl = document.getElementById("active-learning-stats");
  if (statsEl) {
    if (AppState.filter.startsWith("candidates_") && AppState.candidateStats) {
      const st = AppState.candidateStats;
      statsEl.style.display = "block";
      statsEl.innerHTML = `<strong>🎯 ${escapeHtml(st.mode)}:</strong> <span style="color:#f87171; font-weight:700;">${st.fails} Fails</span> / ${st.target_fails} goal &nbsp;|&nbsp; <span style="color:#34d399; font-weight:700;">${st.passes} Passes</span> / ${st.target_passes} goal`;
    } else {
      statsEl.style.display = "none";
    }
  }

  if (countEl) {
    if (AppState.filter === "dev_disagreements") {
      countEl.textContent = `Disagreements: ${filtered.length} traces`;
    } else if (AppState.filter === "dev_split") {
      countEl.textContent = `Dev Split: ${filtered.length} traces`;
    } else if (AppState.filter === "train_split") {
      countEl.textContent = `Train Split: ${filtered.length} traces`;
    } else if (AppState.filter === "test_split") {
      countEl.textContent = `Test Split: ${filtered.length} traces`;
    } else if (AppState.filter.startsWith("candidates_")) {
      const revCount = filtered.filter((s) => s.is_reviewed).length;
      countEl.textContent = `Candidates: ${revCount} / ${filtered.length}`;
    } else if (AppState.filter === "batch1") {
      const reviewedCount = filtered.filter((s) => s.is_reviewed).length;
      countEl.textContent = `Batch 1: ${reviewedCount} / ${filtered.length} (${filtered.length} total)`;
    } else if (AppState.filter === "batch2") {
      const reviewedCount = filtered.filter((s) => s.is_reviewed).length;
      countEl.textContent = `Batch 2: ${reviewedCount} / ${filtered.length} (${filtered.length} total)`;
    } else if (AppState.filter === "batch3") {
      const reviewedCount = filtered.filter((s) => s.is_reviewed).length;
      countEl.textContent = `Batch 3: ${reviewedCount} / ${filtered.length} (${filtered.length} total)`;
    } else if (AppState.filter === "batch4") {
      const reviewedCount = filtered.filter((s) => s.is_reviewed).length;
      countEl.textContent = `Batch 4: ${reviewedCount} / ${filtered.length} (${filtered.length} total)`;
    } else {
      countEl.textContent = `${filtered.length} / ${AppState.sessions.length}`;
    }
  }

  if (filtered.length === 0) {
    list.innerHTML = '<li style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 12px;">No matching scenarios found</li>';
    return;
  }

  filtered.forEach((s) => {
    const li = document.createElement("li");
    const isActive = AppState.currentSession && AppState.currentSession.session_id === s.session_id;
    li.className = `session-item ${isActive ? "active" : ""}`;
    li.dataset.sessionId = s.session_id;

    let verdictDot = '<span class="dot-status"></span>';
    if (s.verdict === "pass") verdictDot = '<span class="dot-status dot-pass" title="Pass"></span>';
    else if (s.verdict === "fail") verdictDot = '<span class="dot-status dot-fail" title="Fail"></span>';
    else if (s.verdict === "defer") verdictDot = '<span class="dot-status dot-defer" title="Deferred"></span>';

    let judgeBadge = "";
    if (s.is_disagreement) {
      judgeBadge = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(239, 68, 68, 0.25); color: #f87171; font-weight: 700; border: 1px solid rgba(239, 68, 68, 0.4);" title="Judge disagreed with human label">⚠️ Disagree</span>`;
    } else if (s.judge_verdict) {
      const col = s.judge_verdict === "Pass" ? "#34d399" : "#f87171";
      judgeBadge = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(255, 255, 255, 0.08); color: ${col}; font-weight: 600;">Judge: ${s.judge_verdict}</span>`;
    }

    let batchBadge = "";
    if (AppState.filter.startsWith("candidates_")) {
      batchBadge = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(245, 158, 11, 0.15); color: #fbbf24; font-weight: 600;" title="${escapeHtml(s.candidate_signal || 'Semantic neighbor')}">[🎯 Candidate]</span>`;
    } else if (s.batch1_reason && AppState.filter === "batch1") {
      const isCluster = s.batch1_type === "cluster_rep";
      const color = isCluster ? "var(--primary)" : "var(--accent-cyan)";
      batchBadge = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(99, 102, 241, 0.15); color: ${color}; font-weight: 600;">[${escapeHtml(s.batch1_reason)}]</span>`;
    } else if (s.batch2_reason && AppState.filter === "batch2") {
      batchBadge = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(16, 185, 129, 0.15); color: var(--accent-emerald); font-weight: 600;">[${escapeHtml(s.batch2_reason)}]</span>`;
    } else if (s.batch3_reason && AppState.filter === "batch3") {
      batchBadge = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(168, 85, 247, 0.15); color: #c084fc; font-weight: 600;">[${escapeHtml(s.batch3_reason)}]</span>`;
    } else if (s.batch4_reason && AppState.filter === "batch4") {
      batchBadge = `<span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(59, 130, 246, 0.15); color: #60a5fa; font-weight: 600;">[${escapeHtml(s.batch4_reason)}]</span>`;
    }

    li.innerHTML = `
      <div class="session-item-header">
        <span class="scenario-tag">${s.scenario_id}</span>
        <span class="role-badge role-${s.user_role}">${s.user_role}</span>
      </div>
      <div class="session-preview">${escapeHtml(s.preview_text || "No preview")}</div>
      <div class="session-status-dots">
        ${verdictDot}
        ${judgeBadge}
        ${batchBadge}
        ${s.has_permission_denied ? '<span class="dot-status dot-denied" title="Permission Denied"></span>' : ""}
        ${s.has_escalation ? '<span style="font-size: 10px; color: var(--accent-amber); font-weight: 600;">[Escalated]</span>' : ""}
        ${s.turn_count > 1 ? `<span style="font-size: 10px; color: var(--accent-blue); font-weight: 600;">[${s.turn_count} turns]</span>` : ""}
        ${s.total_spans ? `<span style="font-size: 10px; color: #a78bfa; font-weight: 600; background: rgba(167, 139, 250, 0.12); padding: 1px 5px; border-radius: 3px;" title="${s.total_spans} total spans (${s.tool_spans || 0} tool, ${s.gen_spans || 0} gen)">${s.total_spans} spans</span>` : ""}
      </div>
    `;


    li.addEventListener("click", () => {
      const origIdx = AppState.sessions.findIndex((item) => item.session_id === s.session_id);
      if (origIdx !== -1) {
        AppState.currentIndex = origIdx;
      }
      loadBySessionId(s.session_id);
    });
    list.appendChild(li);
  });
}

function navigate(delta) {
  const filtered = getFilteredSessions();
  if (filtered.length === 0) return;

  const currentSid = AppState.currentSession ? AppState.currentSession.session_id : "";
  let currFilteredIdx = filtered.findIndex((s) => s.session_id === currentSid);
  if (currFilteredIdx === -1) currFilteredIdx = 0;

  const nextFilteredIdx = currFilteredIdx + delta;
  if (nextFilteredIdx >= 0 && nextFilteredIdx < filtered.length) {
    const nextSession = filtered[nextFilteredIdx];
    const origIdx = AppState.sessions.findIndex((s) => s.session_id === nextSession.session_id);
    if (origIdx !== -1) {
      AppState.currentIndex = origIdx;
    }
    loadBySessionId(nextSession.session_id);
  }
}

function highlightActiveSidebarItem(sessionId) {
  document.querySelectorAll(".session-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.sessionId === sessionId);
  });
}

// Utility Helpers
function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatArgs(args) {
  if (!args || typeof args !== "object") return "";
  const entries = Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`);
  return entries.join(", ");
}

function renderMarkdownLite(text) {
  if (!text) return "";
  let out = escapeHtml(text);
  // Bold **text**
  out = out.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Bullet lists
  out = out.replace(/^- (.*)$/gm, "&bull; $1");
  return out;
}
