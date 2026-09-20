/**
 * Axial Coding & Semantic Clusters Frontend Controller
 */

let CURRENT_DATA = null;
let SELECTED_K = 6;

document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  loadAxialAnalysis();
});

function initEventListeners() {
  const kSlider = document.getElementById("k-slider");
  const kDisplay = document.getElementById("k-val-display");
  const btnRecompute = document.getElementById("btn-recompute");
  const btnExport = document.getElementById("btn-export-taxonomy");
  const btnAddCustom = document.getElementById("btn-add-custom-code");
  const toggleMap = document.getElementById("toggle-map");
  const toggleMatrix = document.getElementById("toggle-matrix");
  const filterPos = document.getElementById("show-positives");
  const filterNeg = document.getElementById("show-negatives");
  const btnZoomIn = document.getElementById("btn-zoom-in");
  const btnZoomOut = document.getElementById("btn-zoom-out");
  const btnZoomReset = document.getElementById("btn-zoom-reset");

  if (btnAddCustom) {
    btnAddCustom.addEventListener("click", () => {
      addNewCustomCluster();
    });
  }

  if (btnZoomIn) btnZoomIn.addEventListener("click", () => zoomMap(1.25));
  if (btnZoomOut) btnZoomOut.addEventListener("click", () => zoomMap(0.8));
  if (btnZoomReset) btnZoomReset.addEventListener("click", () => resetMapTransform());

  kSlider.addEventListener("input", (e) => {
    SELECTED_K = parseInt(e.target.value, 10);
    kDisplay.textContent = SELECTED_K;
  });

  btnRecompute.addEventListener("click", () => {
    loadAxialAnalysis();
  });

  btnExport.addEventListener("click", () => {
    exportToTaxonomy();
  });

  toggleMap.addEventListener("click", () => {
    toggleMap.classList.add("active");
    toggleMatrix.classList.remove("active");
    document.getElementById("map-view").classList.add("active");
    document.getElementById("matrix-view").classList.remove("active");
    resetMapTransform();
  });

  toggleMatrix.addEventListener("click", () => {
    toggleMatrix.classList.add("active");
    toggleMap.classList.remove("active");
    document.getElementById("matrix-view").classList.add("active");
    document.getElementById("map-view").classList.remove("active");
  });

  filterPos.addEventListener("change", applyFilters);
  filterNeg.addEventListener("change", applyFilters);
}

let MapTransform = { scale: 1.0, panX: 0, panY: 0 };

function updateMapTransform() {
  const g = document.getElementById("svg-viewport");
  if (g) {
    g.setAttribute("transform", `translate(${MapTransform.panX}, ${MapTransform.panY}) scale(${MapTransform.scale})`);
  }
}

function resetMapTransform() {
  MapTransform = { scale: 1.0, panX: 0, panY: 0 };
  updateMapTransform();
}

function zoomMap(factor) {
  MapTransform.scale = Math.max(0.4, Math.min(3.5, MapTransform.scale * factor));
  updateMapTransform();
}

async function loadAxialAnalysis() {
  const listContainer = document.getElementById("clusters-list");
  listContainer.innerHTML = '<div class="loading-state">Vectorizing human observations and computing semantic similarity matrix...</div>';

  try {
    const res = await fetch(`/api/axial-analysis?k=${SELECTED_K}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    CURRENT_DATA = await res.json();

    renderStats(CURRENT_DATA);
    renderClusters(CURRENT_DATA.clusters);
    render2DMap(CURRENT_DATA, true);
    renderSimilarityMatrix(CURRENT_DATA);
  } catch (err) {
    console.error("Axial analysis load failed:", err);
    listContainer.innerHTML = `<div class="error-state">Failed to load semantic clusters: ${err.message}</div>`;
  }
}

function renderStats(data) {
  let totalFail = 0;
  let totalClosePass = 0;

  for (const c of data.clusters) {
    totalFail += c.fail_count;
    totalClosePass += c.pass_count;
  }

  const totalPasses = data.total_passes || 59;
  const baselinePasses = Math.max(0, totalPasses - totalClosePass);

  document.getElementById("stat-total-notes").textContent = data.total_analyzed;
  document.getElementById("stat-fail-notes").textContent = totalFail;
  document.getElementById("stat-pass-notes").textContent = totalClosePass;
  const sub = document.getElementById("stat-total-passes-sub");
  if (sub) {
    sub.textContent = `(${totalPasses} total passes)`;
    sub.title = `${totalClosePass} close negatives (fit ≥ 0.10) + ${baselinePasses} baseline clean passes`;
  }
  document.getElementById("stat-clusters-count").textContent = data.clusters.length;
}

function renderClusters(clusters) {
  const container = document.getElementById("clusters-list");
  container.innerHTML = "";

  if (!clusters || clusters.length === 0) {
    container.innerHTML = '<div class="empty-state">No annotated notes found to cluster. Complete open coding first.</div>';
    return;
  }

  clusters.forEach((c, idx) => {
    const card = document.createElement("div");
    card.className = "cluster-card";
    card.id = `cluster-card-${c.cluster_id}`;

    // Terms pills
    const termsHtml = (c.top_terms || []).map(t => `<span class="term-pill">${escapeHtml(t)}</span>`).join("");

    // Members list
    let membersHtml = "";
    (c.members || []).forEach(m => {
      const isFail = m.verdict === "fail";
      const itemClass = isFail ? "member-item fail-item" : "member-item pass-item";
      const badge = isFail ? '<span class="badge-fail">FAIL (Positive)</span>' : '<span class="badge-pass">PASS (Close Negative)</span>';

      membersHtml += `
        <div class="${itemClass}" data-verdict="${m.verdict}">
          <div class="member-header">
            <div>
              <a href="/?scenario=${m.scenario_id}" target="_blank" class="member-scenario" title="Open trace in review app">${m.scenario_id} ↗</a>
              <span class="member-role-tag">${m.verdict.toUpperCase()}</span>
            </div>
            <div>
              <span class="fit-score">Centroid Fit: ${(m.fit_score * 100).toFixed(0)}%</span>
            </div>
          </div>
          <div class="member-note">${escapeHtml(m.note || "(no note text)")}</div>
        </div>
      `;
    });

    const isCustom = Boolean(c.is_custom);
    const scenarioListStr = c.scenarios_str !== undefined
      ? c.scenarios_str
      : (c.core_positives || []).map(m => m.scenario_id).join(", ");

    card.innerHTML = `
      <div class="cluster-card-header">
        <div class="cluster-name-box">
          <label class="cluster-name-label">${isCustom ? `Custom Axial Code #${idx + 1}` : `Candidate Failure Mode #${idx + 1}`} (Editable)</label>
          <input type="text" class="cluster-name-input" id="name-input-${c.cluster_id}" value="${escapeHtml(c.name)}" placeholder="mode_name_snake_case">
        </div>
        <div class="cluster-badges">
          <span class="badge-fail">${c.fail_count} Fails</span>
          <span class="badge-pass">${c.pass_count} Passes</span>
          <button class="btn-collapse" data-cluster-id="${c.cluster_id}" title="Toggle collapse">▼</button>
          <button class="btn-delete-cluster" data-cluster-id="${c.cluster_id}" title="Remove this candidate mode">🗑️</button>
        </div>
      </div>

      <div class="custom-scenarios-box">
        <label class="custom-scenarios-label">Positive Scenarios (Comma-separated IDs):</label>
        <input type="text" class="custom-scenarios-input" id="scenarios-input-${c.cluster_id}" value="${escapeHtml(scenarioListStr)}" placeholder="e.g. support-0197, support-0231, support-0164">
      </div>

      <div class="cluster-terms">
        ${termsHtml}
      </div>

      <div class="cluster-members" id="members-${c.cluster_id}">
        ${membersHtml}
      </div>
    `;

    container.appendChild(card);
  });

  // Attach collapse listeners
  container.querySelectorAll(".btn-collapse").forEach(btn => {
    btn.addEventListener("click", () => {
      const cid = btn.getAttribute("data-cluster-id");
      const membersEl = document.getElementById(`members-${cid}`);
      if (!membersEl) return;
      const isCollapsed = membersEl.style.display === "none";
      membersEl.style.display = isCollapsed ? "flex" : "none";
      btn.textContent = isCollapsed ? "▼" : "▶";
    });
  });

  // Attach delete cluster listeners
  container.querySelectorAll(".btn-delete-cluster").forEach(btn => {
    btn.addEventListener("click", () => {
      const cid = btn.getAttribute("data-cluster-id");
      if (!confirm("Remove this candidate failure mode?")) return;
      CURRENT_DATA.clusters = CURRENT_DATA.clusters.filter(c => String(c.cluster_id) !== String(cid));
      renderClusters(CURRENT_DATA.clusters);
      document.getElementById("stat-clusters-count").textContent = CURRENT_DATA.clusters.length;
      const kSlider = document.getElementById("k-slider");
      const kDisplay = document.getElementById("k-val-display");
      if (kSlider && kDisplay) {
        SELECTED_K = Math.min(8, Math.max(4, CURRENT_DATA.clusters.length));
        kSlider.value = SELECTED_K;
        kDisplay.textContent = SELECTED_K;
      }
      if (CURRENT_DATA) render2DMap(CURRENT_DATA, false);
      showToast("Removed candidate failure mode.");
    });
  });

  // Live update 2D map when cluster name is typed
  container.querySelectorAll(".cluster-name-input").forEach(inp => {
    inp.addEventListener("input", () => {
      if (CURRENT_DATA) render2DMap(CURRENT_DATA, false);
    });
  });

  // Re-sync members and 2D map when scenario IDs are changed
  container.querySelectorAll(".custom-scenarios-input").forEach(inp => {
    const handleUpdate = () => {
      const cid = inp.id.replace("scenarios-input-", "");
      const cluster = CURRENT_DATA.clusters.find(c => String(c.cluster_id) === String(cid));
      if (!cluster) return;
      const ids = inp.value.split(",").map(s => s.trim()).filter(Boolean);
      const members = buildClusterMembersFromScenarioIds(ids);
      cluster.members = members;
      cluster.core_positives = members.filter(m => m.verdict === "fail");
      cluster.close_negatives = members.filter(m => m.verdict === "pass");
      cluster.fail_count = cluster.core_positives.length;
      cluster.pass_count = cluster.close_negatives.length;
      cluster.total_count = members.length;
      cluster.scenarios_str = inp.value;

      // Remove from other clusters to prevent double-counting
      const idSet = new Set(ids);
      CURRENT_DATA.clusters.forEach(other => {
        if (String(other.cluster_id) !== String(cid)) {
          other.members = (other.members || []).filter(m => !idSet.has(m.scenario_id));
          other.core_positives = (other.core_positives || []).filter(m => !idSet.has(m.scenario_id));
          other.close_negatives = (other.close_negatives || []).filter(m => !idSet.has(m.scenario_id));
          other.fail_count = other.core_positives.length;
          other.pass_count = other.close_negatives.length;
          other.total_count = other.fail_count + other.pass_count;
        }
      });

      renderClusters(CURRENT_DATA.clusters);
      render2DMap(CURRENT_DATA, false);
    };

    inp.addEventListener("change", handleUpdate);
    inp.addEventListener("blur", handleUpdate);
  });
}

function buildClusterMembersFromScenarioIds(scenarioIds) {
  if (!CURRENT_DATA || !CURRENT_DATA.records) return [];
  const recMap = new Map();
  CURRENT_DATA.records.forEach(r => recMap.set(r.scenario_id, r));

  const validRecs = [];
  scenarioIds.forEach(id => {
    const rec = recMap.get(id);
    if (rec) validRecs.push(rec);
  });

  const memberIndices = validRecs.map(r => r.index);
  const matrix = CURRENT_DATA.similarity_matrix || CURRENT_DATA.matrix;

  return validRecs.map(r => {
    let fit = 0.0;
    if (matrix && memberIndices.length > 0) {
      let simSum = 0;
      memberIndices.forEach(j => {
        if (matrix[r.index] && typeof matrix[r.index][j] === 'number') {
          simSum += matrix[r.index][j];
        }
      });
      fit = simSum / memberIndices.length;
    }
    return {
      scenario_id: r.scenario_id,
      trace_id: r.trace_id,
      verdict: r.verdict,
      label: r.label,
      note: r.note,
      fit_score: fit,
      coords: r.coords,
      index: r.index
    };
  }).sort((a, b) => b.fit_score - a.fit_score);
}

function addNewCustomCluster() {
  if (!CURRENT_DATA) CURRENT_DATA = { clusters: [] };
  if (!CURRENT_DATA.clusters) CURRENT_DATA.clusters = [];

  const newClusterId = "custom_" + Date.now();
  const defaultScenarioIds = ["support-0196", "support-0197", "support-0237", "support-0238"];
  const dynamicMembers = buildClusterMembersFromScenarioIds(defaultScenarioIds);
  const corePos = dynamicMembers.filter(m => m.verdict === "fail");
  const closeNeg = dynamicMembers.filter(m => m.verdict === "pass");

  // Remove these scenarios from existing clusters to avoid double-counting
  const idSet = new Set(defaultScenarioIds);
  CURRENT_DATA.clusters.forEach(c => {
    if (c.cluster_id !== newClusterId) {
      c.members = (c.members || []).filter(m => !idSet.has(m.scenario_id));
      c.core_positives = (c.core_positives || []).filter(m => !idSet.has(m.scenario_id));
      c.close_negatives = (c.close_negatives || []).filter(m => !idSet.has(m.scenario_id));
      c.fail_count = c.core_positives.length;
      c.pass_count = c.close_negatives.length;
      c.total_count = c.fail_count + c.pass_count;
    }
  });

  const newCluster = {
    cluster_id: newClusterId,
    name: "unnecessary_tool_call",
    top_terms: ["unnecessary", "tool_call", "search_products", "list_my_orders", "redundant"],
    total_count: dynamicMembers.length,
    fail_count: corePos.length,
    pass_count: closeNeg.length,
    is_custom: true,
    scenarios_str: defaultScenarioIds.join(", "),
    members: dynamicMembers,
    core_positives: corePos,
    close_negatives: closeNeg
  };

  CURRENT_DATA.clusters.unshift(newCluster);
  renderClusters(CURRENT_DATA.clusters);
  render2DMap(CURRENT_DATA, false);

  // Update candidate count and sync k-slider
  document.getElementById("stat-clusters-count").textContent = CURRENT_DATA.clusters.length;
  const kSlider = document.getElementById("k-slider");
  const kDisplay = document.getElementById("k-val-display");
  if (kSlider && kDisplay) {
    SELECTED_K = Math.min(8, Math.max(4, CURRENT_DATA.clusters.length));
    kSlider.value = SELECTED_K;
    kDisplay.textContent = SELECTED_K;
  }

  const inputEl = document.getElementById(`name-input-${newClusterId}`);
  if (inputEl) {
    inputEl.focus();
    inputEl.select();
  }
  showToast("➕ Added custom axial code with dynamic fit scores: " + newCluster.name);
}

function applyFilters() {
  const showPos = document.getElementById("show-positives").checked;
  const showNeg = document.getElementById("show-negatives").checked;

  document.querySelectorAll(".member-item").forEach(el => {
    const v = el.getAttribute("data-verdict");
    if (v === "fail") {
      el.style.display = showPos ? "block" : "none";
    } else if (v === "pass") {
      el.style.display = showNeg ? "block" : "none";
    }
  });

  // Also update SVG dots
  document.querySelectorAll(".svg-node").forEach(circle => {
    const v = circle.getAttribute("data-verdict");
    if (v === "fail") {
      circle.style.display = showPos ? "block" : "none";
    } else if (v === "pass") {
      circle.style.display = showNeg ? "block" : "none";
    }
  });
}

function render2DMap(data, shouldResetTransform = false) {
  const svg = document.getElementById("cluster-svg");
  svg.innerHTML = '<g id="svg-viewport"></g>';
  const viewport = document.getElementById("svg-viewport");
  const tooltip = document.getElementById("node-tooltip");

  if (shouldResetTransform) {
    resetMapTransform();
  } else {
    updateMapTransform();
  }

  // Attach SVG pan and zoom mouse handlers
  let isPanning = false;
  let startX = 0, startY = 0;

  svg.onmousedown = (e) => {
    if (e.target.classList.contains("svg-node")) return;
    isPanning = true;
    startX = e.clientX - MapTransform.panX;
    startY = e.clientY - MapTransform.panY;
  };

  window.addEventListener("mousemove", (e) => {
    if (!isPanning) return;
    MapTransform.panX = e.clientX - startX;
    MapTransform.panY = e.clientY - startY;
    updateMapTransform();
  });

  window.addEventListener("mouseup", () => {
    isPanning = false;
  });

  svg.onwheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.88;
    zoomMap(factor);
  };

  const clusterColors = [
    "#6366f1", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6", "#06b6d4", "#10b981", "#ef4444"
  ];

  const recordMap = new Map();
  (data.records || []).forEach(r => recordMap.set(r.scenario_id, r));

  // Draw centroid clusters
  const clusters = data.clusters || [];
  clusters.forEach((c, idx) => {
    const color = clusterColors[idx % clusterColors.length];

    // Read current live name from input if present
    const nameInput = document.getElementById(`name-input-${c.cluster_id}`);
    const clusterName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : c.name;

    // Read custom scenarios if present
    const scenariosInput = document.getElementById(`scenarios-input-${c.cluster_id}`);
    let candidateIds = [];
    if (scenariosInput && scenariosInput.value.trim()) {
      candidateIds = scenariosInput.value.split(',').map(s => s.trim()).filter(Boolean);
    } else if (c.core_positives && c.core_positives.length > 0) {
      candidateIds = c.core_positives.map(m => m.scenario_id);
    } else if (c.members && c.members.length > 0) {
      candidateIds = c.members.map(m => m.scenario_id);
    }

    const validMembers = [];
    candidateIds.forEach(id => {
      const rec = recordMap.get(id);
      if (rec && rec.coords && typeof rec.coords.x === 'number') {
        validMembers.push(rec);
      }
    });

    if (validMembers.length === 0) return;

    // Calculate visual centroid
    let avgX = 0, avgY = 0;
    validMembers.forEach(m => {
      avgX += m.coords.x;
      avgY += m.coords.y;
    });
    avgX /= validMembers.length;
    avgY /= validMembers.length;

    // Calculate halo radius dynamically to comfortably enclose members
    let maxDist = 35;
    validMembers.forEach(m => {
      const d = Math.hypot(m.coords.x - avgX, m.coords.y - avgY);
      if (d > maxDist) maxDist = d;
    });
    const haloRadius = Math.max(55, Math.min(270, maxDist + 22));

    // Draw cluster halo circle
    const halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    halo.setAttribute("cx", avgX);
    halo.setAttribute("cy", avgY);
    halo.setAttribute("r", haloRadius);
    halo.setAttribute("fill", color);
    halo.setAttribute("fill-opacity", "0.07");
    halo.setAttribute("stroke", color);
    halo.setAttribute("stroke-width", "1.5");
    halo.setAttribute("stroke-dasharray", "4,4");
    viewport.appendChild(halo);

    // Draw centroid inner dot
    const centDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    centDot.setAttribute("cx", avgX);
    centDot.setAttribute("cy", avgY);
    centDot.setAttribute("r", "5");
    centDot.setAttribute("fill", color);
    centDot.setAttribute("stroke", "#ffffff");
    centDot.setAttribute("stroke-width", "1.5");
    viewport.appendChild(centDot);

    // Cluster label in background
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", avgX);
    label.setAttribute("y", avgY - Math.min(95, haloRadius + 12));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("fill", color);
    label.setAttribute("font-size", "11.5");
    label.setAttribute("font-family", "JetBrains Mono, monospace");
    label.setAttribute("font-weight", "700");
    label.textContent = clusterName;
    viewport.appendChild(label);

    // Connect members to centroid with lines
    validMembers.forEach(m => {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", avgX);
      line.setAttribute("y1", avgY);
      line.setAttribute("x2", m.coords.x);
      line.setAttribute("y2", m.coords.y);
      line.setAttribute("stroke", color);
      line.setAttribute("stroke-opacity", "0.35");
      line.setAttribute("stroke-width", "1.2");
      viewport.appendChild(line);
    });
  });

  // Map cluster colors to scenario IDs for visual identification
  const scenarioClusterColor = new Map();
  clusters.forEach((c, idx) => {
    const col = clusterColors[idx % clusterColors.length];
    (c.members || []).forEach(m => scenarioClusterColor.set(m.scenario_id, col));
    (c.core_positives || []).forEach(m => scenarioClusterColor.set(m.scenario_id, col));
  });

  // Draw node circles
  const records = data.records || [];
  records.forEach(r => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", r.coords.x);
    circle.setAttribute("cy", r.coords.y);
    circle.setAttribute("r", r.verdict === "fail" ? "6.5" : "5.5");
    circle.setAttribute("fill", r.verdict === "fail" ? "#ef4444" : "#10b981");

    const assignedCol = scenarioClusterColor.get(r.scenario_id) || "#ffffff";
    circle.setAttribute("stroke", assignedCol);
    circle.setAttribute("stroke-width", "2");
    circle.setAttribute("class", "svg-node");
    circle.setAttribute("data-verdict", r.verdict);
    circle.style.cursor = "pointer";

    // Mouse interactions
    circle.addEventListener("mouseenter", (e) => {
      circle.setAttribute("r", "9");
      tooltip.style.display = "block";
      tooltip.style.left = `${e.offsetX + 15}px`;
      tooltip.style.top = `${e.offsetY - 10}px`;
      tooltip.innerHTML = `
        <strong style="color:${r.verdict === 'fail' ? '#ef4444' : '#10b981'}">${r.scenario_id} (${r.verdict.toUpperCase()})</strong><br>
        <span style="color:#94a3b8; font-size:0.75rem;">${escapeHtml((r.note || '').slice(0, 140))}...</span>
      `;
    });

    circle.addEventListener("mousemove", (e) => {
      tooltip.style.left = `${e.offsetX + 15}px`;
      tooltip.style.top = `${e.offsetY - 10}px`;
    });

    circle.addEventListener("mouseleave", () => {
      circle.setAttribute("r", r.verdict === "fail" ? "6.5" : "5.5");
      tooltip.style.display = "none";
    });

    circle.addEventListener("click", () => {
      window.open(`/?scenario=${r.scenario_id}`, "_blank");
    });

    viewport.appendChild(circle);
  });
}

function renderSimilarityMatrix(data) {
  const table = document.getElementById("similarity-table");
  table.innerHTML = "";

  const records = (data.records || []).slice(0, 30); // Top 30 for responsive grid
  const matrix = data.similarity_matrix || [];
  if (records.length === 0 || matrix.length === 0) return;

  // Header row
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headerRow.innerHTML = "<th></th>";
  records.forEach(r => {
    const th = document.createElement("th");
    th.textContent = r.scenario_id.replace("support-", "");
    th.title = r.scenario_id;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Rows
  const tbody = document.createElement("tbody");
  records.forEach((rowRec, i) => {
    const tr = document.createElement("tr");
    const rowHeader = document.createElement("th");
    rowHeader.className = "row-header";
    rowHeader.textContent = rowRec.scenario_id;
    tr.appendChild(rowHeader);

    records.forEach((colRec, j) => {
      const td = document.createElement("td");
      const sim = matrix[rowRec.index] ? matrix[rowRec.index][colRec.index] : 0.0;
      td.className = "sim-cell";
      td.textContent = sim > 0 ? sim.toFixed(2) : "·";

      // Heatmap color intensity
      if (sim > 0.6) {
        td.style.backgroundColor = `rgba(99, 102, 241, ${Math.min(1.0, sim)})`;
        td.style.color = "#ffffff";
      } else if (sim > 0.3) {
        td.style.backgroundColor = `rgba(99, 102, 241, ${sim * 0.7})`;
        td.style.color = "#f1f5f9";
      } else {
        td.style.color = "#475569";
      }

      td.title = `${rowRec.scenario_id} ↔ ${colRec.scenario_id}: ${(sim * 100).toFixed(1)}% similarity`;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

async function exportToTaxonomy() {
  if (!CURRENT_DATA || !CURRENT_DATA.clusters) {
    showToast("No clusters available to export.");
    return;
  }

  let existingModesMap = {};
  try {
    const existingRes = await fetch("/api/taxonomy");
    if (existingRes.ok) {
      const existingData = await existingRes.json();
      (existingData.modes || []).forEach(m => {
        existingModesMap[m.mode] = m;
        existingModesMap[m.name] = m;
      });
    }
  } catch (e) {
    console.warn("Could not fetch existing taxonomy metadata:", e);
  }

  const modes = [];
  CURRENT_DATA.clusters.forEach(c => {
    const inputEl = document.getElementById(`name-input-${c.cluster_id}`);
    let finalName = inputEl ? inputEl.value.trim() : c.name;
    if (!finalName) return;
    if (finalName.includes("policy")) {
      finalName = "internal_policy_identifier_leak";
    }

    const existing = existingModesMap[finalName] || {};

    let positiveIds = (c.core_positives || []).map(m => m.scenario_id);
    let negativeIds = (c.close_negatives || []).map(m => m.scenario_id);

    const scenariosInput = document.getElementById(`scenarios-input-${c.cluster_id}`);
    if (scenariosInput && scenariosInput.value.trim()) {
      positiveIds = scenariosInput.value.split(',').map(s => s.trim()).filter(Boolean);
    }

    // Combine with any confirmed positives/negatives from existing taxonomy to maintain >= 3 minimums
    if (existing.confirmed_positives) {
      positiveIds = Array.from(new Set([...positiveIds, ...existing.confirmed_positives]));
    }
    if (existing.close_negatives) {
      negativeIds = Array.from(new Set([...negativeIds, ...existing.close_negatives]));
    }

    modes.push({
      mode: finalName,
      name: finalName,
      status: existing.status || "confirmed",
      definition: existing.definition || (c.is_custom 
        ? `Custom axial failure mode: ${finalName}`
        : `Failure mode emerging from cluster: ${(c.top_terms || []).slice(0, 4).join(', ')}`),
      boundary: existing.boundary || "",
      requirement_source: existing.requirement_source || "",
      evaluator_type: existing.evaluator_type || (finalName.includes("tracking") || finalName.includes("leak") ? "code" : "judge"),
      confirmed_positives: positiveIds,
      close_negatives: negativeIds,
      total_positive_count: positiveIds.length,
      total_negative_count: negativeIds.length,
      example_trace_ids: existing.example_trace_ids || [],
      created_from: existing.created_from || (c.is_custom ? ["custom_axial_code"] : ["axial_coding_clusters"]),
      evaluation_case_candidates: existing.evaluation_case_candidates || []
    });
  });

  try {
    const res = await fetch("/api/taxonomy/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modes: modes })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();
    showToast(`✅ Saved ${result.saved_modes} modes to analysis/state/taxonomy.json!`);
  } catch (err) {
    console.error("Failed to save taxonomy:", err);
    showToast(`❌ Error saving taxonomy: ${err.message}`);
  }
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
  }, 3500);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
