const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function pct(rate) {
  if (rate == null || Number.isNaN(rate)) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

function fmt(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

function showToast(msg, isError = false) {
  const el = $("#toast");
  el.hidden = false;
  el.textContent = msg;
  el.classList.toggle("is-error", isError);
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    el.hidden = true;
  }, 3200);
}

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts?.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ---------- Navigation ---------- */
function showView(name) {
  $$(".view").forEach((v) => {
    const on = v.id === `view-${name}`;
    v.hidden = !on;
    v.classList.toggle("is-visible", on);
  });
  $$(".nav-btn").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.view === name);
  });
  const loaders = {
    overview: loadOverview,
    log: ensureLogReady,
    results: loadResults,
    stations: loadStations,
    doubles: loadDoubles,
    readiness: loadReadiness,
  };
  loaders[name]?.();
}

$$(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});
$("#btn-goto-log")?.addEventListener("click", () => showView("log"));
$$("[data-goto]").forEach((b) => {
  b.addEventListener("click", () => showView(b.dataset.goto));
});

/* ---------- Overview ---------- */
function renderCompTimeline(el, points, opts = {}) {
  if (!el) return;
  const list = points || [];
  if (!list.length) {
    el.innerHTML = `<p class="empty-inline">No competition meets yet — open Results to seed or add one.</p>`;
    return;
  }
  const max = Math.max(...list.map((p) => p.score), 1);
  const showN = opts.limit ? list.slice(-opts.limit) : list;
  el.innerHTML = `
    <div class="comp-bars">
      ${showN
        .map((p) => {
          const h = Math.max(8, Math.round((p.score / max) * 100));
          const medal = p.medal ? ` medal-${p.medal}` : "";
          const title = `${p.year} · ${p.name}: ${p.score}${p.medal ? ` · ${p.medal}` : ""}`;
          return `<div class="comp-bar-col${medal}" title="${title.replace(/"/g, "&quot;")}">
            <div class="comp-bar" style="height:${h}%"></div>
            <span class="comp-bar-score">${p.score}</span>
            <span class="comp-bar-year">${p.year}</span>
          </div>`;
        })
        .join("")}
    </div>`;
}

async function loadOverview() {
  const data = await api("/api/dashboard");
  const empty = $("#overview-empty");
  const content = $("#overview-content");
  const timeline = data.competition_timeline || [];

  // Always show competition timeline even with no logged sessions
  if (data.empty) {
    empty.hidden = false;
    content.hidden = true;
    // Still paint timeline into empty state if we have meets
    if (timeline.length) {
      empty.hidden = true;
      content.hidden = false;
      $("#m-overall").textContent = "—";
      $("#m-overall-hint").textContent = "No training sessions logged yet";
      $("#m-recent").textContent = "—";
      $("#m-prs").textContent = "—";
      $("#m-prs-hint").textContent = "";
      $("#event-list").innerHTML = "";
      $("#drill-note").textContent = "";
      $("#diag-list").innerHTML = "";
      $("#rounds-table tbody").innerHTML = "";
      renderCompTimeline($("#comp-timeline"), timeline);
    }
    return;
  }
  empty.hidden = true;
  content.hidden = false;

  $("#m-overall").textContent = pct(data.overall);
  $("#m-overall-hint").textContent = `${data.overall_hits}/${data.overall_shots} · ${data.competition_sessions} sessions`;
  $("#m-recent").textContent = pct(data.recent_form);
  $("#m-prs").textContent = data.readiness?.prs != null ? Math.round(data.readiness.prs) : "—";
  const zone = data.readiness?.acwr_zone;
  $("#m-prs-hint").textContent = zone ? `ACWR ${zone.replace("_", " ")}` : "Add training loads for ACWR";

  const eventList = $("#event-list");
  eventList.innerHTML = "";
  const order = ["practice", "qualification", "final", "drill"];
  for (const et of order) {
    const b = data.by_event?.[et];
    if (!b) continue;
    const li = document.createElement("li");
    li.innerHTML = `<span>${et}</span><span class="val">${pct(b.rate)} <small>(${b.n})</small></span>`;
    eventList.appendChild(li);
  }
  const note = $("#drill-note");
  if (data.drill_sessions) {
    note.textContent = `Drills: ${data.drill_hits}/${data.drill_shots} (${pct(data.drill_rate)}) — excluded from competition form.`;
  } else {
    note.textContent = "";
  }

  const d = data.diagnostics || {};
  $("#diag-list").innerHTML = [
    ["Δ pressure (practice − qual)", fmt(d.delta_p, 3)],
    ["Δ fatigue (early − late)", fmt(d.delta_fatigue, 3)],
    ["Δ wind (calm − windy)", fmt(d.delta_wind, 3)],
  ]
    .map(([label, val]) => `<li><span>${label}</span><span class="val">${val}</span></li>`)
    .join("");

  renderCompTimeline($("#comp-timeline"), timeline);

  const tbody = $("#rounds-table tbody");
  tbody.innerHTML = "";
  for (const r of data.recent_rounds || []) {
    const tr = document.createElement("tr");
    const when = (r.timestamp || "").toString().slice(0, 16).replace("T", " ");
    let typeLabel = r.event_type;
    if (r.event_type === "drill" && r.drill_name) typeLabel = `drill · ${r.drill_name}`;
    else if (r.format === "issf_final_36") typeLabel = `${r.event_type} · final`;
    tr.innerHTML = `
      <td>${when || "—"}</td>
      <td>${typeLabel}</td>
      <td><strong>${r.hits}/${r.shots}</strong></td>
      <td>${r.wind_speed_mph ?? "—"}</td>
      <td>${r.location || "—"}</td>`;
    tbody.appendChild(tr);
  }
}

/* ---------- Competition Results ---------- */
let editingMeetId = "";

function medalBadge(medal) {
  if (!medal) return "";
  return `<span class="medal-badge medal-${medal}">${medal}</span>`;
}

function roundsChip(rounds) {
  if (!rounds?.length) return "—";
  return rounds.join(" ");
}

function meetFormHtml(meet = null) {
  const m = meet || {};
  return `
    <section class="panel meet-form-panel" id="meet-form-panel">
      <h2 class="panel-title">${meet ? "Edit meet" : "Add meet"}</h2>
      <form id="meet-form" class="meet-form">
        <div class="meta-grid">
          <label class="full-label">
            <span>Name</span>
            <input type="text" id="mf-name" required value="${(m.name || "").replace(/"/g, "&quot;")}" />
          </label>
          <label>
            <span>Year</span>
            <input type="number" id="mf-year" required min="1990" max="2100" value="${m.year || new Date().getFullYear()}" />
          </label>
          <label>
            <span>Date (optional)</span>
            <input type="date" id="mf-date" value="${m.date_precision === "day" ? m.event_date || "" : ""}" />
          </label>
          <label>
            <span>Category</span>
            <input type="text" id="mf-category" value="${(m.category || "").replace(/"/g, "&quot;")}" placeholder="Skeet · M21" />
          </label>
          <label>
            <span>Level</span>
            <select id="mf-level">
              <option value="domestic" ${m.level !== "international" ? "selected" : ""}>Domestic</option>
              <option value="international" ${m.level === "international" ? "selected" : ""}>International</option>
            </select>
          </label>
          <label>
            <span>Qualification</span>
            <input type="number" id="mf-qual" min="0" max="500" value="${m.qualification_score ?? ""}" />
          </label>
          <label>
            <span>Final</span>
            <input type="number" id="mf-final" min="0" max="200" value="${m.final_score ?? ""}" />
          </label>
          <label>
            <span>Selection aggregate</span>
            <input type="number" id="mf-agg" min="0" max="999" value="${m.selection_aggregate ?? ""}" />
          </label>
          <label>
            <span>Placing</span>
            <input type="number" id="mf-placing" min="1" max="999" value="${m.placing ?? ""}" />
          </label>
          <label>
            <span>Medal</span>
            <select id="mf-medal">
              <option value="">—</option>
              <option value="gold" ${m.medal === "gold" ? "selected" : ""}>Gold</option>
              <option value="silver" ${m.medal === "silver" ? "selected" : ""}>Silver</option>
              <option value="bronze" ${m.medal === "bronze" ? "selected" : ""}>Bronze</option>
            </select>
          </label>
          <label class="full-label">
            <span>Rounds (paste e.g. 24 22 23 23 23)</span>
            <input type="text" id="mf-rounds" value="${roundsChip(m.rounds) === "—" ? "" : roundsChip(m.rounds)}" />
          </label>
          <label class="full-label">
            <span>Source URL</span>
            <input type="url" id="mf-source" value="${(m.source_url || "").replace(/"/g, "&quot;")}" />
          </label>
          <label class="full-label">
            <span>Notes</span>
            <input type="text" id="mf-notes" value="${(m.notes || "").replace(/"/g, "&quot;")}" />
          </label>
        </div>
        <div class="form-actions">
          <button type="button" class="btn btn-ghost" id="mf-cancel">Cancel</button>
          <button type="submit" class="btn btn-primary">Save meet</button>
        </div>
      </form>
    </section>`;
}

async function loadResults() {
  const data = await api("/api/competitions");
  const root = $("#results-body");
  const seasons = data.seasons || [];
  const meets = data.meets || [];
  const totals = data.totals || {};

  const seasonStrip = seasons.length
    ? `<div class="season-strip">${seasons
        .map((s) => {
          const medals = [];
          if (s.medals.gold) medals.push(`${s.medals.gold}G`);
          if (s.medals.silver) medals.push(`${s.medals.silver}S`);
          if (s.medals.bronze) medals.push(`${s.medals.bronze}B`);
          return `<article class="season-card">
            <p class="season-year">${s.year}</p>
            <p class="season-best">${s.best_qual != null ? s.best_qual : "—"}</p>
            <p class="season-meta">${s.meet_count} meet${s.meet_count === 1 ? "" : "s"}${
              medals.length ? " · " + medals.join(" ") : ""
            }</p>
          </article>`;
        })
        .join("")}</div>`
    : "";

  const meetRows = meets
    .map((m) => {
      const place =
        m.placing != null ? `#${m.placing}` : m.medal ? "" : "—";
      const src = m.source_url
        ? `<a href="${m.source_url}" target="_blank" rel="noopener">source</a>`
        : "";
      return `<article class="meet-card" data-meet-id="${m.meet_id}">
        <div class="meet-top">
          <div>
            <h3 class="meet-name">${m.name}</h3>
            <p class="meet-cat">${m.year} · ${m.category || m.level}${
              m.level === "international" ? " · intl" : ""
            }</p>
          </div>
          <div class="meet-score">
            <strong>${m.qualification_score ?? "—"}</strong>
            ${medalBadge(m.medal)}
            <span class="meet-place">${place}</span>
          </div>
        </div>
        <p class="meet-rounds">${roundsChip(m.rounds)}</p>
        <div class="meet-actions">
          ${src}
          ${m.final_score != null ? `<span>Final ${m.final_score}</span>` : ""}
          ${m.selection_aggregate != null ? `<span>Agg ${m.selection_aggregate}</span>` : ""}
          <button type="button" class="btn btn-ghost btn-sm btn-edit-meet" data-id="${m.meet_id}">Edit</button>
          <button type="button" class="btn btn-ghost btn-sm btn-del-meet" data-id="${m.meet_id}">Delete</button>
        </div>
      </article>`;
    })
    .join("");

  root.innerHTML = `
    <div class="metric-row">
      <article class="metric">
        <p class="metric-label">Meets</p>
        <p class="metric-value">${totals.meets || 0}</p>
        <p class="metric-hint">Domestic + international</p>
      </article>
      <article class="metric metric-accent">
        <p class="metric-label">Medals</p>
        <p class="metric-value">${(totals.gold || 0) + (totals.silver || 0) + (totals.bronze || 0)}</p>
        <p class="metric-hint">${totals.gold || 0}G · ${totals.silver || 0}S · ${totals.bronze || 0}B</p>
      </article>
    </div>
    ${seasonStrip}
    <section class="panel">
      <h2 class="panel-title">Qualification timeline</h2>
      <div id="results-timeline" class="comp-timeline"></div>
    </section>
    <div id="meet-form-slot"></div>
    <section class="panel">
      <h2 class="panel-title">Meets</h2>
      <div class="meet-list">${meetRows || `<p class="empty-inline">No meets yet.</p>`}</div>
    </section>`;

  renderCompTimeline($("#results-timeline"), data.timeline || []);

  $$(".btn-edit-meet").forEach((btn) => {
    btn.addEventListener("click", () => {
      const meet = meets.find((x) => x.meet_id === btn.dataset.id);
      if (!meet) return;
      editingMeetId = meet.meet_id;
      $("#meet-form-slot").innerHTML = meetFormHtml(meet);
      wireMeetForm();
      $("#meet-form-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  $$(".btn-del-meet").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this meet?")) return;
      try {
        await api(`/api/competitions/${encodeURIComponent(btn.dataset.id)}`, {
          method: "DELETE",
        });
        showToast("Meet deleted");
        await loadResults();
      } catch (err) {
        showToast(err.message || "Delete failed", true);
      }
    });
  });
}

function openNewMeetForm() {
  editingMeetId = "";
  const slot = $("#meet-form-slot");
  if (!slot) return;
  slot.innerHTML = meetFormHtml();
  wireMeetForm();
  $("#meet-form-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function wireMeetForm() {
  $("#mf-cancel")?.addEventListener("click", () => {
    editingMeetId = "";
    const slot = $("#meet-form-slot");
    if (slot) slot.innerHTML = "";
  });
  $("#meet-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const dateVal = $("#mf-date").value;
    const year = Number($("#mf-year").value);
    const body = {
      meet_id: editingMeetId || null,
      name: $("#mf-name").value.trim(),
      year,
      event_date: dateVal || `${year}-01-01`,
      date_precision: dateVal ? "day" : "year",
      category: $("#mf-category").value.trim() || null,
      level: $("#mf-level").value,
      qualification_score: $("#mf-qual").value === "" ? null : Number($("#mf-qual").value),
      final_score: $("#mf-final").value === "" ? null : Number($("#mf-final").value),
      selection_aggregate: $("#mf-agg").value === "" ? null : Number($("#mf-agg").value),
      placing: $("#mf-placing").value === "" ? null : Number($("#mf-placing").value),
      medal: $("#mf-medal").value || null,
      rounds_text: $("#mf-rounds").value.trim() || null,
      source_url: $("#mf-source").value.trim() || null,
      notes: $("#mf-notes").value.trim() || null,
    };
    try {
      await api("/api/competitions", { method: "POST", body: JSON.stringify(body) });
      showToast("Meet saved");
      editingMeetId = "";
      await loadResults();
    } catch (err) {
      showToast(err.message || "Save failed", true);
    }
  });
}

$("#btn-new-meet")?.addEventListener("click", async () => {
  // Reveal Results without the fire-and-forget loader race
  $$(".view").forEach((v) => {
    const on = v.id === "view-results";
    v.hidden = !on;
    v.classList.toggle("is-visible", on);
  });
  $$(".nav-btn").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.view === "results");
  });
  await loadResults();
  openNewMeetForm();
});

/* ---------- Log modes ---------- */
let mode = "round"; // round | final | drill
let activeSlots = [];
let drillMeta = { templates: [], block_kinds: [] };
let drillBlocks = []; // {station, kind, reps}
let activeTemplateId = "";
let drillScoring = false;
let drillCursor = 0;
let drillAttempt = 1;
let cleanRunMode = true;
let cleanNeeded = 1; // consecutive clean passes required
let cleanStreak = 0; // completed clean passes in a row
const shotState = new Map();

const MODE_COPY = {
  round: "Official ISSF 25-target sequence. Tap green = hit, slate = miss.",
  final:
    "ISSF 2026 Final sequence (stations 3–4–5). Pick how many targets you completed.",
  drill: "Pick a saved drill (or build one). Clean run = miss restarts the drill.",
};

$$(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

function setLogActionBars() {
  const isDrill = mode === "drill";
  $("#board-actions").hidden = isDrill;
  $("#drill-start-actions").hidden = !(isDrill && !drillScoring);
  $("#drill-save-actions").hidden = !(isDrill && drillScoring);
  $("#shot-board").hidden = isDrill;
}

function kindName(kind) {
  return (drillMeta.block_kinds || []).find((k) => k.id === kind)?.name || kind;
}

function targetsForBlock(b) {
  const per =
    (drillMeta.block_kinds || []).find((k) => k.id === b.kind)?.targets_per_rep || 1;
  return b.reps * per;
}

function totalDrillTargets() {
  return drillBlocks.reduce((n, b) => n + targetsForBlock(b), 0);
}

function renderBlockList() {
  const list = $("#block-list");
  list.innerHTML = "";
  if (!drillBlocks.length) {
    $("#drill-desc").textContent =
      "Add blocks in order — e.g. Station 1: High single, Low single, 2× High pair.";
    $("#live-den").textContent = "/ 0";
    return;
  }
  drillBlocks.forEach((b, idx) => {
    const li = document.createElement("li");
    const t = targetsForBlock(b);
    li.innerHTML = `
      <div>
        <strong>Station ${b.station}</strong> · ${b.reps}× ${kindName(b.kind)}
        <div class="block-meta">${t} target${t === 1 ? "" : "s"}</div>
      </div>
      <button type="button" class="block-remove" data-idx="${idx}">Remove</button>`;
    list.appendChild(li);
  });
  $$(".block-remove", list).forEach((btn) => {
    btn.addEventListener("click", () => {
      drillBlocks.splice(Number(btn.dataset.idx), 1);
      renderBlockList();
    });
  });
  const total = totalDrillTargets();
  $("#drill-desc").textContent = `${drillBlocks.length} blocks · ${total} targets in one clean run`;
  $("#live-den").textContent = `/ ${total}`;
}

function renderDrillCards() {
  const root = $("#drill-cards");
  root.innerHTML = "";
  for (const t of drillMeta.templates || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "drill-card" + (t.template_id === activeTemplateId ? " is-active" : "");
    btn.dataset.id = t.template_id;
    btn.innerHTML = `<strong>${t.name}</strong><span>${t.target_count} targets · tap to load</span>`;
    btn.addEventListener("click", () => {
      $("#f-drill-template").value = t.template_id;
      loadBlocksFromTemplate(t.template_id);
      renderDrillCards();
    });
    root.appendChild(btn);
  }
}

function fillTemplateSelect() {
  const sel = $("#f-drill-template");
  const current = sel.value;
  sel.innerHTML = `<option value="">Custom</option>`;
  for (const t of drillMeta.templates || []) {
    const opt = document.createElement("option");
    opt.value = t.template_id;
    opt.textContent = t.name;
    sel.appendChild(opt);
  }
  if ([...sel.options].some((o) => o.value === current)) sel.value = current;
  renderDrillCards();
}

function loadBlocksFromTemplate(templateId) {
  activeTemplateId = templateId || "";
  $("#btn-delete-template").hidden = !activeTemplateId;
  if (!templateId) {
    $("#drill-template-desc").textContent = "Building a custom drill.";
    renderBlockList();
    renderDrillCards();
    return;
  }
  const t = (drillMeta.templates || []).find((x) => x.template_id === templateId);
  if (!t) return;
  drillBlocks = t.blocks.map((b) => ({
    station: b.station,
    kind: b.kind,
    reps: b.reps,
  }));
  $("#f-drill-name").value = t.name;
  $("#f-drill-name").dataset.auto = "1";
  $("#drill-template-desc").textContent = t.description || "";
  $("#f-drill-template").value = templateId;
  renderBlockList();
  renderDrillCards();
}

async function ensureLogReady() {
  if (!drillMeta.block_kinds?.length) {
    const data = await api("/api/drills");
    drillMeta = data;
    const kindSel = $("#f-block-kind");
    kindSel.innerHTML = (data.block_kinds || [])
      .map((k) => `<option value="${k.id}">${k.name}</option>`)
      .join("");
    // Prefer high pair as a common default
    if ([...kindSel.options].some((o) => o.value === "high_pair")) {
      kindSel.value = "high_pair";
    }
    fillTemplateSelect();
  }
  await setMode(mode);
}

async function setMode(next) {
  mode = next;
  drillScoring = false;
  $$(".mode-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.mode === mode));
  $("#log-lede").textContent = MODE_COPY[mode];

  const isDrill = mode === "drill";
  const isFinal = mode === "final";
  $("#final-controls").hidden = !isFinal;
  $("#drill-controls").hidden = !isDrill;
  $("#label-round-num").hidden = isDrill || isFinal;
  $("#drill-scorer").hidden = true;
  if ($("#drill-setup")) $("#drill-setup").hidden = !isDrill;
  setLogActionBars();

  const eventSel = $("#f-event");
  if (isFinal) {
    eventSel.innerHTML = `
      <option value="final">Final</option>
      <option value="practice">Practice final</option>`;
  } else if (isDrill) {
    eventSel.innerHTML = `<option value="drill">Drill</option>`;
  } else {
    eventSel.innerHTML = `
      <option value="practice">Practice</option>
      <option value="qualification">Qualification</option>`;
  }

  if (isDrill) {
    await prepareDrillSetup();
  } else if (isFinal) {
    await loadFinalBoard(Number($("#f-final-n").value) || 36);
  } else {
    await loadFixedBoard("issf_25");
  }
}

$("#f-final-n")?.addEventListener("change", () => {
  if (mode === "final") loadFinalBoard(Number($("#f-final-n").value));
});

async function prepareDrillSetup() {
  drillScoring = false;
  shotState.clear();
  activeSlots = [];
  drillAttempt = 1;
  cleanStreak = 0;
  cleanRunMode = true;
  cleanNeeded = 1;
  $("#drill-scorer").hidden = true;
  $("#drill-setup").hidden = false;
  setLogActionBars();
  try {
    const data = await api("/api/drills");
    drillMeta.templates = data.templates || [];
    drillMeta.block_kinds = data.block_kinds || drillMeta.block_kinds;
    const kindSel = $("#f-block-kind");
    if (kindSel && !kindSel.options.length) {
      kindSel.innerHTML = (drillMeta.block_kinds || [])
        .map((k) => `<option value="${k.id}">${k.name}</option>`)
        .join("");
    }
    fillTemplateSelect();
  } catch {
    /* ignore */
  }
  loadBlocksFromTemplate(activeTemplateId || $("#f-drill-template").value || "");
  $("#live-score").textContent = "0";
}

$("#btn-new-custom")?.addEventListener("click", () => {
  activeTemplateId = "";
  $("#f-drill-template").value = "";
  drillBlocks = [];
  $("#f-drill-name").value = "";
  $("#f-drill-name").dataset.auto = "1";
  $("#drill-template-desc").textContent = "Building a custom drill.";
  $("#btn-delete-template").hidden = true;
  renderBlockList();
  renderDrillCards();
});

$("#btn-add-block")?.addEventListener("click", () => {
  const station = Number($("#f-block-station").value);
  const kind = $("#f-block-kind").value;
  let reps = Number($("#f-block-reps").value);
  if (!Number.isFinite(reps) || reps < 1) reps = 1;
  if (reps > 40) reps = 40;
  drillBlocks.push({ station, kind, reps });
  if ($("#f-drill-name").dataset.auto === "1" || !$("#f-drill-name").value) {
    $("#f-drill-name").value = "Custom drill";
    $("#f-drill-name").dataset.auto = "1";
  }
  renderBlockList();
});

$("#f-drill-name")?.addEventListener("input", () => {
  $("#f-drill-name").dataset.auto = "0";
});

$("#btn-save-template")?.addEventListener("click", async () => {
  if (!drillBlocks.length) {
    showToast("Add at least one block", true);
    return;
  }
  const name = $("#f-drill-name").value.trim() || "Custom drill";
  try {
    const saved = await api("/api/drill-templates", {
      method: "POST",
      body: JSON.stringify({
        name,
        blocks: drillBlocks,
        template_id: activeTemplateId || null,
        description: $("#drill-template-desc").textContent || null,
      }),
    });
    showToast(`Saved “${saved.name}”`);
    const data = await api("/api/drills");
    drillMeta.templates = data.templates || [];
    fillTemplateSelect();
    loadBlocksFromTemplate(saved.template_id);
  } catch (err) {
    showToast(err.message || "Could not save", true);
  }
});

$("#btn-delete-template")?.addEventListener("click", async () => {
  if (!activeTemplateId) return;
  if (!confirm("Delete this saved drill?")) return;
  try {
    await api(`/api/drill-templates/${encodeURIComponent(activeTemplateId)}`, {
      method: "DELETE",
    });
    showToast("Deleted");
    activeTemplateId = "";
    drillBlocks = [];
    $("#f-drill-template").value = "";
    const data = await api("/api/drills");
    drillMeta.templates = data.templates || [];
    fillTemplateSelect();
    renderBlockList();
    $("#btn-delete-template").hidden = true;
    $("#drill-template-desc").textContent = "";
  } catch (err) {
    showToast(err.message || "Delete failed", true);
  }
});

async function loadDrillSlots() {
  if (!drillBlocks.length) throw new Error("Add at least one block first");
  const composed = await api("/api/drills/compose", {
    method: "POST",
    body: JSON.stringify({
      name: $("#f-drill-name").value || "Custom drill",
      blocks: drillBlocks,
    }),
  });
  $("#drill-desc").textContent = composed.description;
  return composed.slots.map((s) => ({ ...s }));
}

$("#f-clean-run")?.addEventListener("change", () => {
  $("#clean-streak-wrap").hidden = !$("#f-clean-run").checked;
});

async function startDrillScoring() {
  try {
    activeSlots = await loadDrillSlots();
  } catch (err) {
    showToast(err.message || "Could not build drill", true);
    return;
  }
  if (!activeSlots.length) {
    showToast("No targets in drill", true);
    return;
  }
  shotState.clear();
  drillCursor = 0;
  drillAttempt = 1;
  cleanStreak = 0;
  cleanRunMode = !!$("#f-clean-run")?.checked;
  cleanNeeded = cleanRunMode
    ? Math.max(1, Number($("#f-clean-needed")?.value || 1))
    : 1;
  drillScoring = true;
  $("#drill-setup").hidden = true;
  $("#drill-scorer").hidden = false;
  $("#scorer-attempt").hidden = !cleanRunMode;
  setLogActionBars();
  renderScorer();
}

function restartAttempt(bumpAttempt) {
  shotState.clear();
  drillCursor = 0;
  if (bumpAttempt) {
    drillAttempt += 1;
    cleanStreak = 0; // miss breaks the streak
  }
  renderScorer();
}

function beginNextCleanLap() {
  shotState.clear();
  drillCursor = 0;
  renderScorer();
  showToast(`Clean ${cleanStreak}/${cleanNeeded} — go again`);
}

function renderScorer() {
  const total = activeSlots.length;
  const done = shotState.size;
  const hits = [...shotState.values()].filter(Boolean).length;
  const finished = cleanRunMode
    ? cleanStreak >= cleanNeeded
    : done >= total;

  $("#scorer-total").textContent = String(total);
  if (cleanRunMode) {
    $("#scorer-hits").textContent = `${cleanStreak}/${cleanNeeded} clean`;
    $("#scorer-attempt").hidden = false;
    $("#scorer-attempt").textContent =
      cleanStreak >= cleanNeeded
        ? `Done · ${cleanNeeded} in a row`
        : `Attempt ${drillAttempt} · need ${cleanNeeded} in a row`;
  } else {
    $("#scorer-hits").textContent = `${hits} hit${hits === 1 ? "" : "s"}`;
    $("#scorer-attempt").hidden = true;
  }

  $("#live-score").textContent = String(hits);
  $("#live-den").textContent = `/ ${total}`;

  const slot = activeSlots[Math.min(drillCursor, Math.max(total - 1, 0))];
  $("#scorer-idx").textContent = String(
    finished ? total : Math.min(drillCursor + 1, total)
  );
  $("#scorer-station").textContent = finished
    ? "Complete"
    : `Station ${slot?.station ?? "—"}`;

  if (finished) {
    $("#scorer-label").textContent = cleanRunMode
      ? `${cleanNeeded} clean in a row — save when ready.`
      : `Done — ${hits}/${total}. Save when ready.`;
  } else {
    $("#scorer-label").textContent = (slot?.label || "").replace(
      /^Station \d+ · /,
      ""
    );
  }

  $("#btn-score-hit").disabled = finished;
  $("#btn-score-miss").disabled = finished;
  const saveBtn = $("#btn-save-drill");
  if (saveBtn) saveBtn.disabled = !finished;

  const root = $("#scorer-by-station");
  root.innerHTML = "";
  const byStation = [];
  for (let i = 0; i < total; i++) {
    const st = activeSlots[i].station;
    if (!byStation.length || byStation[byStation.length - 1].station !== st) {
      byStation.push({ station: st, indices: [] });
    }
    byStation[byStation.length - 1].indices.push(i);
  }
  for (const group of byStation) {
    const wrap = document.createElement("div");
    wrap.className = "station-strip";
    wrap.innerHTML = `<h4>Station ${group.station}</h4>`;
    const dots = document.createElement("div");
    dots.className = "scorer-dots";
    for (const i of group.indices) {
      const order = activeSlots[i].sequence_order;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "scorer-dot";
      btn.title = activeSlots[i].label || `#${order}`;
      if (shotState.has(order)) {
        btn.classList.add(shotState.get(order) ? "is-hit" : "is-miss");
      } else {
        btn.classList.add("is-pending");
      }
      if (!finished && i === drillCursor) btn.classList.add("is-current");
      btn.addEventListener("click", () => {
        if (cleanRunMode) return;
        drillCursor = i;
        for (let j = i; j < total; j++) {
          shotState.delete(activeSlots[j].sequence_order);
        }
        renderScorer();
      });
      dots.appendChild(btn);
    }
    wrap.appendChild(dots);
    root.appendChild(wrap);
  }
}

function scoreCurrent(isHit) {
  if (!drillScoring || !activeSlots.length) return;
  if (cleanRunMode && cleanStreak >= cleanNeeded) return;
  if (!cleanRunMode && drillCursor >= activeSlots.length) return;

  if (!isHit && cleanRunMode) {
    showToast(`Miss — streak reset · back to Station ${activeSlots[0].station}`);
    restartAttempt(true);
    return;
  }

  const order = activeSlots[drillCursor].sequence_order;
  shotState.set(order, isHit);
  drillCursor += 1;

  if (drillCursor >= activeSlots.length) {
    if (cleanRunMode) {
      cleanStreak += 1;
      if (cleanStreak >= cleanNeeded) {
        renderScorer();
        showToast(`${cleanNeeded} clean in a row — ready to save`);
        return;
      }
      beginNextCleanLap();
      return;
    }
  }
  renderScorer();
}

function undoScore() {
  if (!drillScoring) return;
  if (cleanRunMode) {
    // Undo only within current attempt
    if (drillCursor <= 0) return;
    drillCursor -= 1;
    shotState.delete(activeSlots[drillCursor].sequence_order);
    renderScorer();
    return;
  }
  if (drillCursor <= 0) return;
  drillCursor -= 1;
  shotState.delete(activeSlots[drillCursor].sequence_order);
  renderScorer();
}

$("#btn-start-drill")?.addEventListener("click", () => startDrillScoring());
$("#btn-score-hit")?.addEventListener("click", () => scoreCurrent(true));
$("#btn-score-miss")?.addEventListener("click", () => scoreCurrent(false));
$("#btn-score-undo")?.addEventListener("click", () => undoScore());
$("#btn-score-restart")?.addEventListener("click", () => {
  if (!drillScoring) return;
  restartAttempt(cleanRunMode);
  showToast("Attempt restarted");
});
$("#btn-score-back")?.addEventListener("click", () => prepareDrillSetup());

document.addEventListener("keydown", (e) => {
  if (mode !== "drill" || !drillScoring) return;
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
  const key = e.key.toLowerCase();
  if (key === "h") {
    e.preventDefault();
    scoreCurrent(true);
  } else if (key === "m") {
    e.preventDefault();
    scoreCurrent(false);
  } else if (key === "u" || key === "backspace") {
    e.preventDefault();
    undoScore();
  }
});

async function loadFixedBoard(formatId) {
  const data = await api(`/api/sequence?format=${formatId}`);
  activeSlots = data.slots;
  $("#shot-board").hidden = false;
  renderShotBoard(activeSlots, {
    groupByStation: formatId === "issf_25",
    groupByStage: formatId === "issf_final_36",
  });
}

async function loadFinalBoard(n) {
  const data = await api("/api/sequence?format=issf_final_36");
  activeSlots = data.slots.slice(0, n);
  $("#shot-board").hidden = false;
  renderShotBoard(activeSlots, { groupByStage: true });
}

function renderShotBoard(slots, { groupByStation = false, groupByStage = false } = {}) {
  const board = $("#shot-board");
  board.innerHTML = "";
  shotState.clear();

  let groups;
  if (groupByStage) {
    const map = new Map();
    for (const s of slots) {
      const key = s.stage || 1;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(s);
    }
    groups = [...map.entries()].map(([stage, items]) => ({
      title: `Stage ${stage}`,
      subtitle: stageSubtitle(stage, items.length),
      items,
    }));
  } else if (groupByStation) {
    const map = new Map();
    for (const s of slots) {
      if (!map.has(s.station)) map.set(s.station, []);
      map.get(s.station).push(s);
    }
    groups = [...map.entries()].map(([station, items]) => ({
      title: `Station ${station}`,
      subtitle: `${items.length} target${items.length > 1 ? "s" : ""}`,
      items,
    }));
  } else {
    groups = [{ title: "Targets", subtitle: `${slots.length} targets`, items: slots }];
  }

  for (const g of groups) {
    const block = document.createElement("div");
    block.className = "station-block";
    block.innerHTML = `
      <div class="station-head">
        <h3>${g.title}</h3>
        <span>${g.subtitle}</span>
      </div>
      <div class="shot-row"></div>`;
    const row = $(".shot-row", block);
    for (const s of g.items) {
      shotState.set(s.sequence_order, true);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "shot-btn is-hit";
      btn.dataset.order = String(s.sequence_order);
      const meta = (s.label || "").replace(/^St \d+ · /, "").replace(/ · stage \d+$/, "");
      btn.innerHTML = `<span class="ord">#${s.sequence_order}</span><span class="meta">${meta}</span>`;
      btn.addEventListener("click", () => toggleShot(btn, s.sequence_order));
      row.appendChild(btn);
    }
    board.appendChild(block);
  }
  updateLiveScore();
}

function stageSubtitle(stage, count) {
  const hints = {
    1: "8 athletes · then eliminate 7–8",
    2: "6 athletes · then eliminate 5–6",
    3: "4 athletes · eliminate 4th",
    4: "3 athletes · bronze",
    5: "2 athletes · gold / silver",
  };
  return `${count} targets · ${hints[stage] || ""}`;
}

function toggleShot(btn, order) {
  const next = !shotState.get(order);
  shotState.set(order, next);
  btn.classList.toggle("is-hit", next);
  btn.classList.toggle("is-miss", !next);
  updateLiveScore();
}

function updateLiveScore() {
  let hits = 0;
  for (const v of shotState.values()) if (v) hits += 1;
  $("#live-score").textContent = String(hits);
  $("#live-den").textContent = `/ ${shotState.size}`;
}

$("#btn-all-hit")?.addEventListener("click", () => {
  $$(".shot-btn").forEach((btn) => {
    const order = Number(btn.dataset.order);
    shotState.set(order, true);
    btn.classList.add("is-hit");
    btn.classList.remove("is-miss");
  });
  updateLiveScore();
});

$("#btn-reset-shots")?.addEventListener("click", () => {
  setMode(mode);
});

$("#round-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (mode === "drill") {
    if (!drillScoring) {
      showToast("Tap Start scoring first", true);
      return;
    }
    const cleanDone = cleanRunMode && cleanStreak >= cleanNeeded;
    const normalDone = !cleanRunMode && shotState.size === activeSlots.length;
    if (!cleanDone && !normalDone) {
      if (cleanRunMode) {
        showToast(
          `Need ${cleanNeeded} clean in a row (have ${cleanStreak})`,
          true
        );
      } else {
        showToast(
          `Score all ${activeSlots.length} targets first (${shotState.size} done)`,
          true
        );
      }
      return;
    }
  }
  if (mode !== "drill" && !shotState.size) {
    showToast("No targets to save", true);
    return;
  }

  const windRaw = $("#f-wind").value;
  const rnRaw = $("#f-round-num").value;

  let format = "issf_25";
  let event_type = $("#f-event").value;
  let drill_name = null;

  if (mode === "final") {
    format = "issf_final_36";
  } else if (mode === "drill") {
    format = "drill";
    event_type = "drill";
  }

  let shots;
  if (mode === "drill" && cleanRunMode && cleanStreak >= cleanNeeded) {
    // Save one clean copy of the drill; notes record the streak requirement
    shots = activeSlots.map((s) => ({
      sequence_order: s.sequence_order,
      is_hit: true,
      miss_direction: null,
      station: s.station,
      target_house: s.target_house,
      is_double: s.is_double,
      pair_position: s.pair_position,
    }));
    drill_name = $("#f-drill-name").value || "Drill";
  } else {
    const slotByOrder = new Map(activeSlots.map((s) => [s.sequence_order, s]));
    shots = [...shotState.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([sequence_order, is_hit]) => {
        const slot = slotByOrder.get(sequence_order);
        const base = {
          sequence_order,
          is_hit,
          miss_direction: is_hit ? null : "unknown",
        };
        if (format === "drill" && slot) {
          return {
            ...base,
            station: slot.station,
            target_house: slot.target_house,
            is_double: slot.is_double,
            pair_position: slot.pair_position,
          };
        }
        return base;
      });
    if (mode === "drill") {
      drill_name = $("#f-drill-name").value || `Station drill (${shots.length})`;
    }
  }

  if (!shots.length) {
    showToast("No targets to save", true);
    return;
  }

  const body = {
    event_type,
    format,
    drill_name,
    location: $("#f-location").value || null,
    round_number: mode === "round" && rnRaw ? Number(rnRaw) : null,
    wind_speed_mph: windRaw === "" ? null : Number(windRaw),
    notes:
      mode === "drill" && cleanRunMode
        ? `${cleanNeeded} clean in a row (${drillAttempt} attempts)`
        : null,
    shots,
  };

  try {
    const result = await api("/api/rounds", {
      method: "POST",
      body: JSON.stringify(body),
    });
    showToast(`Saved ${result.hits}/${result.shots}`);
    await setMode(mode);
  } catch (err) {
    showToast(err.message || "Save failed", true);
  }
});

/* ---------- Stations ---------- */
async function loadStations() {
  const data = await api("/api/stations");
  const root = $("#stations-body");
  if (!data.total_shots) {
    root.innerHTML = `<div class="empty-state"><h2>No station data</h2><p>Log rounds, finals, or drills to see volume by station.</p></div>`;
    return;
  }

  const maxN = Math.max(...(data.by_volume || []).map((s) => s.n), 1);
  const most = data.most_shot;
  const least = data.least_shot;

  const volumeRows = (data.by_volume || [])
    .map((s) => {
      const share = data.total_shots ? (s.n / data.total_shots) * 100 : 0;
      const width = (s.n / maxN) * 100;
      return `
      <div class="vol-row">
        <div class="vol-label">Station ${s.station}</div>
        <div class="vol-bar-wrap">
          <div class="vol-bar" style="width:${width}%"></div>
        </div>
        <div class="vol-stats">
          <strong>${s.n}</strong>
          <span>${share.toFixed(0)}%</span>
          <span>${pct(s.hit_rate)}</span>
        </div>
      </div>`;
    })
    .join("");

  const sdiCards = (data.stations || [])
    .map(
      (s) => `
    <article class="station-card">
      <div class="st-num">Station ${s.station}</div>
      <div class="sdi">${fmt(s.sdi, 3)}</div>
      <ul class="rates">
        <li><span>Hit rate</span><span>${pct(s.hit_rate)}</span></li>
        <li><span>Volume</span><span>${s.n} shots</span></li>
        <li><span>Single</span><span>${pct(s.hit_rate_single)}</span></li>
        <li><span>1st / 2nd</span><span>${pct(s.hit_rate_double_1)} / ${pct(s.hit_rate_double_2)}</span></li>
      </ul>
    </article>`
    )
    .join("");

  root.innerHTML = `
    <div class="metric-row">
      <article class="metric metric-accent">
        <p class="metric-label">Most shot</p>
        <p class="metric-value">St ${most?.station ?? "—"}</p>
        <p class="metric-hint">${most ? `${most.n} shots · ${pct(most.hit_rate)}` : "—"}</p>
      </article>
      <article class="metric">
        <p class="metric-label">Least shot</p>
        <p class="metric-value">St ${least?.station ?? "—"}</p>
        <p class="metric-hint">${
          least
            ? least.never_shot
              ? "Not shot yet"
              : `${least.n} shots · ${pct(least.hit_rate)}`
            : "—"
        }</p>
      </article>
      <article class="metric">
        <p class="metric-label">Total volume</p>
        <p class="metric-value">${data.total_shots}</p>
        <p class="metric-hint">All sessions · rounds, finals, drills</p>
      </article>
    </div>

    <section class="panel">
      <h2 class="panel-title">Volume by station</h2>
      <p class="vol-legend"><span>Shots</span><span>% of total</span><span>Hit rate</span></p>
      <div class="vol-list">${volumeRows}</div>
    </section>

    <section class="panel">
      <h2 class="panel-title">Difficulty (SDI)</h2>
      <p class="final-explain" style="margin-top:0">Higher SDI = tougher relative to your mix.</p>
      <div class="stations-grid" style="margin-top:0.75rem">${sdiCards}</div>
    </section>`;
}

/* ---------- Doubles ---------- */
async function loadDoubles() {
  const data = await api("/api/doubles");
  const root = $("#doubles-body");
  if (data.empty) {
    root.innerHTML = `<div class="empty-state"><h2>No doubles yet</h2><p>Doubles appear after you log sessions with pairs.</p></div>`;
    return;
  }
  const spill =
    data.d_f > 0.05
      ? "Miss on T1 raises T2 miss likelihood"
      : Math.abs(data.d_f) < 0.05
        ? "Near-independent execution"
        : "Hit on T1 associated with tougher T2";
  root.innerHTML = `
    <section class="panel">
      <h2 class="panel-title">Transition matrix · ${data.total_doubles} doubles</h2>
      <div class="matrix">
        <div class="cell head"></div>
        <div class="cell head">T2 Hit</div>
        <div class="cell head">T2 Miss</div>
        <div class="cell head">T1 Hit</div>
        <div class="cell">${fmt(data.p_h_given_h, 3)}</div>
        <div class="cell">${fmt(data.p_m_given_h, 3)}</div>
        <div class="cell head">T1 Miss</div>
        <div class="cell">${fmt(data.p_h_given_m, 3)}</div>
        <div class="cell">${fmt(data.p_m_given_m, 3)}</div>
      </div>
      <div class="stat-chips">
        <div class="chip">E<sub>t</sub><strong>${fmt(data.e_t, 3)}</strong></div>
        <div class="chip">D<sub>f</sub><strong>${fmt(data.d_f, 3)}</strong></div>
        <div class="chip">OR<strong>${data.or_double == null ? "—" : fmt(data.or_double, 2)}</strong></div>
      </div>
      <p style="margin:1rem 0 0;color:var(--ink-soft)">${spill}</p>
    </section>`;
}

/* ---------- Readiness ---------- */
async function loadReadiness() {
  const data = await api("/api/readiness");
  const root = $("#readiness-body");
  const zoneClass =
    data.acwr_zone === "sweet_spot"
      ? "zone-sweet"
      : data.acwr_zone === "danger"
        ? "zone-danger"
        : "zone-moderate";

  let spark = "";
  if (data.series?.length) {
    const loads = data.series.map((s) => s.workload);
    const max = Math.max(...loads, 1);
    spark = `<div class="spark" title="Daily workload">${loads
      .map((w) => `<span style="height:${Math.max(8, (w / max) * 100)}%"></span>`)
      .join("")}</div>`;
  }

  root.innerHTML = `
    <div class="metric-row">
      <article class="metric metric-accent">
        <p class="metric-label">PRS</p>
        <p class="metric-value">${data.prs != null ? Math.round(data.prs) : "—"}</p>
        <p class="metric-hint">Peak readiness / 100</p>
      </article>
      <article class="metric">
        <p class="metric-label">ACWR</p>
        <p class="metric-value ${zoneClass}">${fmt(data.acwr, 2)}</p>
        <p class="metric-hint">${(data.acwr_zone || "—").replace("_", " ")}</p>
      </article>
      <article class="metric">
        <p class="metric-label">Banister p(t)</p>
        <p class="metric-value">${fmt(data.banister_p, 1)}</p>
        <p class="metric-hint">Fitness − fatigue</p>
      </article>
    </div>
    <section class="panel">
      <h2 class="panel-title">Form & taper</h2>
      <ul class="diag-list">
        <li><span>Rolling form ratio (RFR)</span><span class="val">${fmt(data.rfr, 3)}</span></li>
        <li><span>Form slope (last 10)</span><span class="val">${fmt(data.slope_form, 4)}</span></li>
        <li><span>Φ taper</span><span class="val">${fmt(data.phi_taper, 3)}</span></li>
        <li><span>Short-term (5)</span><span class="val">${pct(data.short_term_rate)}</span></li>
        <li><span>Long-term (25)</span><span class="val">${pct(data.long_term_rate)}</span></li>
      </ul>
      ${spark || `<p style="color:var(--muted);margin:0.75rem 0 0">No training loads yet — add one below.</p>`}
    </section>`;

  if (!$("#load-date").value) {
    $("#load-date").value = new Date().toISOString().slice(0, 10);
  }
}

$("#load-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/loads", {
      method: "POST",
      body: JSON.stringify({
        load_date: $("#load-date").value,
        workload: Number($("#load-workload").value),
        notes: $("#load-notes").value || null,
      }),
    });
    showToast("Training load saved");
    $("#load-workload").value = "";
    $("#load-notes").value = "";
    loadReadiness();
  } catch (err) {
    showToast(err.message || "Save failed", true);
  }
});

loadOverview().catch((err) => showToast(err.message, true));
