"use strict";

const state = { snapshot: null, selectedProject: null, timer: null, loading: false, transportError: false };
const byId = (id) => document.getElementById(id);
const percent = (value, digits = 0) => value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
const decimal = (value, digits = 1) => value == null ? "N/A" : Number(value).toFixed(digits);
const money = (value) => value == null ? "N/A" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: value < 1 ? 3 : 2 }).format(value);
const integer = (value) => new Intl.NumberFormat("en-US", { notation: value >= 1_000_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value || 0);
const equivalentMoney = (activity = {}) => activity.cost_usd_estimate != null ? money(activity.cost_usd_estimate) : activity.cost_usd_known_sum > 0 ? `≥ ${money(activity.cost_usd_known_sum)}` : "N/A";
const terminalMoney = (activity = {}) => activity.reported_cost_sessions ? `${activity.reported_cost_coverage < 1 ? "≥ " : ""}${money(activity.cost_usd_reported_sum)} · ${percent(activity.reported_cost_coverage)}` : "N/A";
const activityTokens = (activity = {}) => `${integer(activity.tokens_total)}${activity.usage_incomplete_sessions > 0 ? " · partial" : ""}`;
function localDateTime(value, asOf = state.transportError ? Date.now() : state.snapshot?.generated_at) {
  const date = typeof value === "string" ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "N/A";
  const format = new Intl.DateTimeFormat("en-US", {dateStyle: "medium", timeStyle: "medium", hourCycle: "h23"});
  const offset = new Intl.DateTimeFormat("en-US", {timeZoneName: "shortOffset"}).formatToParts(date).find(part => part.type === "timeZoneName").value;
  const seconds = (date - new Date(asOf || Date.now())) / 1000;
  const [unit, divisor] = Math.abs(seconds) >= 86400 ? ["day", 86400] : Math.abs(seconds) >= 3600 ? ["hour", 3600] : Math.abs(seconds) >= 60 ? ["minute", 60] : ["second", 1];
  const age = Number.isFinite(seconds) ? new Intl.RelativeTimeFormat("en-US", {numeric: "auto"}).format(Math.trunc(seconds / divisor), unit) : "age N/A";
  return `${format.format(date)} · ${format.resolvedOptions().timeZone} (${offset}) · ${age}`;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function selectedProject() {
  return state.snapshot?.projects.find((project) => project.project_id === state.selectedProject) || null;
}

function viewMetrics() {
  const project = selectedProject();
  const metrics = project ? {
    ...project.metrics,
    touch: project.touch,
    evidence: project.evidence,
    objective: project.objective,
    authority_confidence: project.authority_confidence,
    trend_30d: project.trend_30d,
    activity: project.activity,
    dataset: project.dataset,
    events_30d: project.events_30d,
    dataset_history: project.dataset_history,
    ingested_at: project.ingested_at,
    stale: project.stale,
    available: project.available,
  } : state.snapshot.aggregate;
  return state.transportError || metrics.stale === true || metrics.available === false ? {...metrics, stale:true, available:false,
    objective:{...metrics.objective, status:"not-measurable", headline:"STALE DATA",
      primary_action:"Restore the read; last data preserved, no current approval.",
      gates:(metrics.objective?.gates || []).map(gate => ({...gate,status:"wait"}))},
    economics:metrics.economics ? {...metrics.economics,cohort_complete:false,
      cost_usd_per_declared_accepted:null,cost_usd_per_reliable_declared:null,
      cost_scope_complete:false,cost_usd_per_declared_accepted_with_overhead:null,
      cost_usd_per_reliable_with_overhead_declared:null,
      reasons:[...(metrics.economics.reasons || []),"current read unavailable"]} : undefined} : metrics;
}

function setText(id, value) {
  const node = byId(id);
  if (node) node.textContent = value;
}

function setTrack(id, value, max = 1) {
  const node = byId(id);
  if (!node) return;
  const bounded = value == null ? 0 : Math.max(0, Math.min(1, value / max));
  node.style.width = `${bounded * 100}%`;
}

function statusLabel(status) {
  return ({
    "instrumentation-inactive": "Instrumentation inactive",
    "collecting": "Collecting evidence",
    "on-target": "On target",
    "off-target": "Off target",
    "not-measurable": "Not yet measurable",
    "needs-attention": "Needs attention",
    "unavailable": "Unavailable",
  })[status] || "Unknown status";
}

function reasonLabel(reason) {
  const exact = {
    "no observed task starts": "No task started with 007 begin.",
    "fewer than 5 matured accepted tasks": "Fewer than five acceptances have a declared D7 follow-up so far.",
    "reliable first-pass rate is N/A": "First-pass with declared D7 cannot be calculated yet.",
    "mean repair rounds is N/A": "Repair rounds have not been measured yet.",
    "7-day escape rate is N/A": "D7 follow-up declarations are missing; absence does not prove survival.",
    "telemetry completeness is N/A": "Telemetry has not been recorded yet.",
    "cost coverage is N/A": "Cost has not been accounted for yet.",
    "reliable first-pass rate below 70%": "First-pass with declared D7 is below 70%.",
  };
  return exact[reason] || reason || "No reason recorded.";
}

function renderHeader(metrics, project) {
  setText("breadcrumb-view", project ? project.name : "Overview");
  setText("view-title", project ? `${project.name}: delivery, rework and cost` : "Delivery, rework and cost: what the evidence shows");
  setText("view-subtitle", project
    ? "Results for the selected project. Acceptance observed by the controller and agent declarations are separate kinds of evidence."
    : "007 steers toward the smallest safe change, verifies acceptance, and makes cost and gaps visible. A causal gain requires a controlled comparison.");
  setText("scope-sample", `${metrics.started_tasks || 0} started · ${metrics.tasks || 0} completed · ${metrics.accepted || 0} accepted`);
  setText("scope-boundary", "Local observations ≠ causal gain. Declared D7 follow-up ≠ verified survival.");

  const verdict = metrics.objective || { status: "not-measurable", headline: "NOT YET MEASURABLE", primary_action: "Enable instrumentation." };
  const card = byId("verdict-card");
  card.className = `verdict-card ${verdict.status}`;
  setText("verdict-label", verdict.headline);
  setText("verdict-reason", statusLabel(verdict.status));
  setText("primary-action", verdict.primary_action);
}

function renderInstrumentation(metrics) {
  const started = metrics.started_tasks || 0;
  const terminal = metrics.tasks || 0;
  const active = metrics.active_tasks || 0;
  setText("instrumentation-started", started);
  setText("instrumentation-terminal", terminal);
  setText("instrumentation-active", active);
  setText("instrumentation-coverage", percent(metrics.observation_coverage));
  setText("instrumentation-title", started
    ? `${started} task${started === 1 ? "" : "s"} observed; ${active} still active`
    : "Projects connected; capture not started yet");
  setText("instrumentation-copy", started
    ? "Coverage compares starts with terminal receipts. Tasks without begin stay outside the denominator and show up as legacy."
    : "The dashboard only measures tasks that start with 007 begin and end with a valid receipt.");
  byId("instrumentation-panel").classList.toggle("is-active", started > 0);
}

function renderRuntimeActivity(activity = {}) {
  setText("activity-sessions", activity.sessions || 0);
  setText("activity-active", activity.active_sessions || 0);
  setText("activity-tokens", activityTokens(activity));
  setText("activity-cost", terminalMoney(activity));
  setText("activity-equivalent-cost", `Optional estimate: ${equivalentMoney(activity)}`);
  byId("runtime-activity-panel").classList.toggle("is-active", (activity.sessions || 0) > 0);
}

function renderMetrics(metrics) {
  const economics = metrics.economics;
  const reliableCost = economics?.cohort_complete === true && economics?.cost_scope_complete === true
    ? economics.cost_usd_per_reliable_with_overhead_declared ?? null : null;
  const perUsd = reliableCost > 0 ? 1 / reliableCost : null;
  setText("metric-reliable", percent(metrics.reliable_first_pass_rate));
  setText("metric-reliable-detail", `${metrics.reliable_first_pass_yes || 0}/${metrics.reliable_first_pass_known || 0} accepted with declared follow-up; not verified`);
  setTrack("track-reliable", metrics.reliable_first_pass_rate);

  setText("metric-escape", percent(metrics.escape_7d_rate));
  setText("metric-escape-detail", `${metrics.escape_7d_yes || 0}/${metrics.escape_7d_known || 0} declared · ${metrics.escape_7d_pending_tasks || 0} without follow-up`);
  setTrack("track-escape", metrics.escape_7d_rate, .1);

  setText("metric-repairs", decimal(metrics.repair_rounds_mean));
  setText("metric-repairs-detail", `${metrics.repair_rounds_known_tasks || 0} tasks measured`);
  setTrack("track-repairs", metrics.repair_rounds_mean, 2);

  setText("metric-roi", perUsd == null ? "N/A" : decimal(perUsd, 2));
  setText("metric-roi-detail", `Observational, not causal savings · cost ${metrics.cost_accounting_status || "N/A"}`);
  setTrack("track-roi", perUsd, 2);

  setText("metric-reliable-cost", money(reliableCost));
  setText("metric-accepted-cost", money(economics?.cost_usd_per_declared_accepted));
  const sources = Object.keys(metrics.cost_sources || {}).sort().join(", ") || "source N/A";
  const costScope = economics?.cost_scope_complete === true ? "overhead included in the declared total" : "overhead N/A; complete total not demonstrated";
  const costDetail = `${economics?.cost_usd_known_tasks || 0}/${economics?.cohort_tasks || 0} in the cohort · ${economics?.cost_basis || "basis N/A"} · ${metrics.cost_accounting_status || "N/A"} · ${sources} · ${economics?.open_tasks ?? metrics.active_tasks ?? 0} open · ${costScope}`;
  setText("metric-reliable-cost-detail", costDetail);
  setText("metric-accepted-cost-detail", `${costDetail} · includes failures; declared acceptances`);
  setTrack("track-cost", economics?.cost_coverage);

  setText("metric-reliable-time", metrics.wall_s_per_reliable == null ? "N/A" : `${decimal(metrics.wall_s_per_reliable, 0)}s`);
  setText("metric-reliable-time-detail", `${metrics.wall_s_known_tasks || 0}/${metrics.tasks || 0} outcomes with timing`);
  setTrack("track-time", metrics.wall_s_per_reliable == null ? null : 1, 1);
  setText("value-accepted", metrics.accepted || 0);
  setText("value-acceptance", `${metrics.accepted || 0} declared · authorship not authenticated`);
  setText("value-rework", decimal(metrics.repair_rounds_mean));
  setText("value-rework-detail", `${metrics.repair_rounds_known_tasks || 0}/${metrics.tasks || 0} terminal tasks measured`);
  setText("value-cost", economics?.cost_usd_known_tasks && economics.cost_usd_known_sum != null ? `${economics.cost_coverage < 1 || !economics.cohort_complete ? "≥ " : ""}${money(economics.cost_usd_known_sum)}` : "N/A");
  setText("value-cost-detail", economics ? `${costDetail} · ${economics.reasons.join("; ") || "complete cohort"}` : "No single economic cohort; check each project.");
  setText("value-open", metrics.active_tasks || 0);
  setText("value-open-detail", `${metrics.blocked || 0} blocked · ${metrics.no_op || 0} no change · open tasks without terminal cost`);
}

function gateActual(gate) {
  if (gate.actual == null) return "N/A";
  if (gate.key === "mature") return integer(gate.actual);
  if (gate.key === "repairs") return decimal(gate.actual);
  if (gate.key === "touch") return `${decimal(gate.actual)}%`;
  return percent(gate.actual);
}

function renderGates(objective = {}) {
  const body = byId("gate-matrix-body");
  body.replaceChildren();
  (objective.gates || []).forEach((gate) => {
    const row = document.createElement("tr");
    [
      gate.label,
      gateActual(gate),
      gate.target,
      `n=${integer(gate.denominator)}`,
      ({ pass: "PASS", fail: "FAIL", wait: "WAIT" })[gate.status] || "N/A",
    ].forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 4) cell.append(element("span", `gate-status ${gate.status}`, value));
      else cell.textContent = value;
      row.append(cell);
    });
    body.append(row);
  });
}

function svgNode(tag, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function renderTrend(rows = []) {
  const host = byId("outcome-trend");
  host.replaceChildren();
  const total = rows.reduce((sum, row) => sum + row.reliable + row.accepted_other + row.not_accepted, 0);
  if (!total) {
    host.append(element("p", "empty-copy", "No completed outcomes in the last 30 days yet."));
    return;
  }
  const svg = svgNode("svg", { viewBox: "0 0 900 240", role: "img", "aria-label": "Daily share of first-pass with declared D7, other accepted and not accepted" });
  const left = 34, top = 20, height = 170, width = 840;
  const step = width / rows.length;
  const lineY = top + height * .3;
  svg.append(svgNode("line", { x1: left, y1: lineY, x2: left + width, y2: lineY, class: "trend-target" }));
  const target = svgNode("text", { x: left + 4, y: lineY - 6, class: "trend-label" });
  target.textContent = "target 70% first-pass + declared D7";
  svg.append(target);
  rows.forEach((row, index) => {
    const daily = row.reliable + row.accepted_other + row.not_accepted;
    if (!daily) return;
    const x = left + index * step + 2;
    const barWidth = Math.max(step - 4, 2);
    let y = top + height;
    [
      ["not_accepted", "trend-not-accepted"],
      ["accepted_other", "trend-repaired"],
      ["reliable", "trend-reliable"],
    ].forEach(([key, className]) => {
      const segment = height * row[key] / daily;
      y -= segment;
      const rect = svgNode("rect", { x, y, width: barWidth, height: segment, rx: 2, class: className });
      const title = svgNode("title");
      title.textContent = `${row.date}: ${row.reliable} first-pass + declared D7, ${row.accepted_other} accepted/other, ${row.not_accepted} not accepted`;
      rect.append(title);
      svg.append(rect);
    });
  });
  const first = svgNode("text", { x: left, y: 218, class: "trend-label" });
  first.textContent = rows[0]?.date.slice(5) || "";
  const last = svgNode("text", { x: left + width, y: 218, class: "trend-label", "text-anchor": "end" });
  last.textContent = rows.at(-1)?.date.slice(5) || "";
  svg.append(first, last);
  host.append(svg);
}

function renderAuthority(metrics, confidence = {}) {
  setText("authority-confidence-label", metrics.authority_bound_tasks ? "bound declarations" : "not observed");
  setText("authority-controlled", 0);
  setText("authority-controlled-detail", "Authorship not authenticated by local records");
  setText("authority-declared", metrics.authority_bound_tasks || 0);
  setText("authority-unobserved", confidence.unobserved || 0);
  setText("authority-coverage", percent(metrics.authority_coverage));
  setText("authority-coverage-detail", `${metrics.authority_bound_tasks || 0}/${metrics.tasks || 0} bound outcomes`);
  setText("authority-protected", metrics.protected_blocks || 0);
  setText("authority-friction", percent(metrics.boundary_friction_rate));
  setText("authority-friction-detail", `${metrics.friction_blocks || 0}/${(metrics.allowed_executions || 0) + (metrics.friction_blocks || 0)} allowed attempts`);
  setText("authority-unclassified", metrics.unclassified_blocks || 0);
}

function renderCountSeries(id, rows, series, title) {
  const host = byId(id); host.replaceChildren();
  const points = rows.map(row => ({at:row.at,time:Date.parse(row.at),data:row.counts === null ? null : row.counts || row})).filter(point => Number.isFinite(point.time));
  const values = points.flatMap(point => series.map(item => point.data?.[item.key])).filter(value => Number.isInteger(value) && value >= 0);
  if (!points.length || !values.length) { host.append(element("p", "empty-copy", "Data unavailable; not zero.")); return; }
  const first = Math.min(...points.map(point => point.time)), last = Math.max(...points.map(point => point.time)), maximum = Math.max(1,...values);
  const x = time => first === last ? 450 : 40 + 820 * (time-first)/(last-first);
  const y = value => 190 - 160 * value/maximum;
  const svg = svgNode("svg", {viewBox:"0 0 900 235",role:"img","aria-label":title});
  for (const value of [0,maximum]) {
    const label = svgNode("text", {x:4,y:y(value),class:"count-label"}); label.textContent = integer(value); svg.append(label);
  }
  series.forEach(item => {
    let prior = null;
    points.forEach(point => {
      const value = point.data?.[item.key];
      if (!Number.isInteger(value) || value < 0) { prior = null; return; }
      if (prior) svg.append(svgNode("path", {d:`M${x(prior.time)},${y(prior.value)}H${x(point.time)}V${y(value)}`,fill:"none",stroke:item.color,"stroke-width":2}));
      const dot = svgNode("circle", {cx:x(point.time),cy:y(value),r:3,fill:item.color});
      const text = svgNode("title"); text.textContent = `${point.at}: ${value} ${item.label}`;
      dot.append(text); svg.append(dot); prior = {time:point.time,value};
    });
  });
  for (const [at,position] of [[first,40],[last,860]]) {
    const label = svgNode("text", {x:position,y:222,class:"count-label","text-anchor":position === 40 ? "start" : "end"});
    label.textContent = new Date(at).toISOString().replace("T"," ").slice(5,16) + " UTC"; svg.append(label);
  }
  host.append(svg);
  host.append(element("p", "measurement-note", `Latest observation: ${series.map(item => `${item.label}: ${points.at(-1).data?.[item.key] ?? "N/A"}`).join(" · ")}`));
}

function renderTemporalCharts(metrics, project) {
  const events = metrics.events_30d;
  renderCountSeries("events-chart", events?.rows || [], [
    {key:"started",label:"declared starts",color:"var(--cyan)"},
    {key:"terminal",label:"declared terminals",color:"var(--amber)"}], "Declared events per UTC day, last 30 days");
  setText("events-chart-note", `${metrics.stale ? "Stale data · " : ""}30 days · UTC buckets · starts (cyan) / terminals (amber), absolute counts; not independent samples. ${events ? `${events.excluded} event(s) excluded; ${events.complete ? "complete read" : "partial data"}.` : "Inconclusive read."}`);
  if (!project) byId("dataset-history-chart").replaceChildren(element("p", "empty-copy", "Select a project to see its evolution."));
  else renderCountSeries("dataset-history-chart", metrics.dataset_history || [], [
    {key:"observational",label:"identified tasks",color:"var(--muted-bright)"},
    {key:"inputs-retained",label:"preserved inputs",color:"var(--cyan)"},
    {key:"case-retained",label:"preserved candidates",color:"var(--amber)"},
    {key:"replay-ready",label:"independent replays",color:"var(--green)"},
    {key:"qualified-comparison",label:"qualified comparisons",color:"var(--violet)"}], "Counts per stage across the observations of this server session");
  const rows = metrics.dataset_history || [];
  setText("dataset-history-note", project ? `${metrics.stale ? "Stale data · " : ""}${rows.length} observation(s) in this server session (max 60); the first is the window baseline, and an empty poll adds no point. ${rows.some(row => row.counts === null) ? "Inconclusive gap; no zero or interpolation." : "Stages overlap; no ROI claim."}` : "Select a project; series with different clocks are not aggregated. History of this session, not training or new ROI.");
}

function renderFunnel(metrics) {
  setText("funnel-started", metrics.started_tasks || 0);
  setText("funnel-terminal", metrics.tasks || 0);
  setText("funnel-accepted", metrics.accepted || 0);
  setText("funnel-first-pass", metrics.accepted_first_pass_yes || 0);
  setText("funnel-reliable", metrics.reliable_first_pass_yes || 0);
  setText("funnel-maturity", `${metrics.reliable_first_pass_known || 0} declared follow-ups · ${metrics.escape_7d_pending_tasks || 0} pending`);
}

function renderDataset(dataset = {}, stale = false) {
  const counts = dataset?.counts;
  for (const stage of ["observational", "inputs-retained", "case-retained", "replay-ready", "qualified-comparison"]) {
    setText(`dataset-${stage}`, counts?.[stage] == null || (!dataset.complete && counts[stage] === 0) ? "N/A" : `${dataset.complete ? "" : "≥ "}${integer(counts[stage])}`);
    setTrack(`dataset-track-${stage}`, counts?.[stage], counts?.observational || 1);
  }
  setText("dataset-boundary", `${stale ? "Last data preserved, no current check" : dataset?.complete ? "Complete read coverage" : "Partial or incomplete read"} · Results of the latest byte checks, not current integrity. Oldest check: ${localDateTime(dataset?.oldest_checked_at)}; latest: ${localDateTime(dataset?.latest_checked_at)} (date N/A when not checked). The cache does not refresh these dates; admission/replay revalidate the bytes. Not dependency closure, independent replay, holdout or ROI; projection capped at 100 cases per project.`);
}

function renderFreshness(metrics, readAt) {
  setText("last-updated", localDateTime(readAt));
  setText("last-ingested", localDateTime(metrics.ingested_at));
  setText("source-status", metrics.stale ? "STALE DATA · last data preserved"
    : metrics.available === false || metrics.projects_unavailable ? "READ UNAVAILABLE OR PARTIAL"
    : "Current read; ingestion changes only when the data does");
}

function renderCuration(curation = {}, stale = false) {
  const preserved = stale || curation.stale || curation.available === false;
  setText("curation-status", !curation.configured ? "Curation not configured"
    : preserved ? "Checkpoint stale or unavailable; last data preserved"
    : "Declared checkpoint · file integrity checked");
  setText("curation-completed", localDateTime(curation.completed_at));
  setText("curation-summary", curation.in_scope === false ? "Project outside the scope of this checkpoint; coverage N/A."
    : curation.counts ? `${integer(curation.counts.retained)} retained case(s) · ${integer(curation.counts.observational)} observational · ${integer(curation.counts.excluded)} excluded · ${integer(curation.counts.followup_sources)} follow-up source(s) · ${integer(curation.counts.corrected_cases_declared)} case(s) with a declared correction · ${integer(curation.counts.escaped_cases_declared)} case(s) with a declared escape · ${integer(curation.counts.gate_hypotheses_declared)} declared gate proposal(s) · ${integer(curation.counts.routing_hypotheses_declared)} declared routing proposal(s) · configured manifest scope`
    : "Counts N/A; no curation or progress is assumed.");
  setText("curation-boundary", "Declared checkpoint; authorship not authenticated. Linked corrections/escapes are declarations, not authenticated incidents or D7 maturity. Polling does not rerun admission/oracle. Not training, policy promotion or proof of ROI.");
  const proposals = curation.in_scope === false || !Array.isArray(curation.proposals) ? [] : curation.proposals.slice(0, 2)
    .filter(entry => entry && ["gate", "routing"].includes(entry.kind) && typeof entry.source_sha256 === "string" && /^[a-f0-9]{64}$/.test(entry.source_sha256))
    .map(entry => `${entry.kind} ${entry.source_sha256.slice(0, 8)} (review pending)`);
  if (proposals.length) byId("curation-boundary").textContent += ` Proposals from the last${preserved ? " preserved" : ""} cycle: ${proposals.join("; ")}.`;
}

function renderTrial(trial) {
  const box = byId("observatory-trial");
  box.replaceChildren();
  if (!trial) { box.append(element("p", "measurement-note", "Effort trial not configured (observatory.effort_trial).")); return; }
  const pct = (v) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "N/A");
  const pp = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(v * 100))}`;
  const band = (b) => (Array.isArray(b) ? `${pp(b[0])} to ${pp(b[1])} pp` : "N/A");
  const arms = (by) => `medium ${pct(by?.medium)}, xhigh ${pct(by?.xhigh)}`;
  const e = trial.enrollment || {};
  box.append(element("h3", null, `Effort trial · ${trial.trial_id} · ${trial.enabled ? "running" : "off"} · verdict: ${trial.verdict}`));
  const gates = Object.entries(trial.gates || {}).map(([k, v]) => `${k} ${v ? "ok" : "not yet"}`).join(" · ");
  box.append(element("p", "observatory-answer", `Enrollment ${e.open ? "open" : `closed ${String(e.closed_at || "").slice(0, 10)}`}: sessions with an integrated commit by drawn arm: medium ${integer(e.per_arm?.medium)}, xhigh ${integer(e.per_arm?.xhigh)} (target ${integer(e.target)} per arm or until ${e.deadline || "N/A"}) · all drawn sessions: medium ${integer(trial.sessions?.medium)}, xhigh ${integer(trial.sessions?.xhigh)} · compliance ${pct(trial.compliance)} (needs ${pct(trial.min_compliance)}) · gates: ${gates}.`));
  const primary = trial.primary, secondary = trial.secondary || {};
  if (primary === "blinded" || primary == null) {
    box.append(element("p", "observatory-answer", `Effort trial outcomes blinded until ${String(trial.blinded_until?.["30"] || "N/A").slice(0, 10)} (7-day secondaries: ${String(trial.blinded_until?.["7"] || "N/A").slice(0, 10)}); pre-registered readout if enrollment runs to its deadline, earlier once both arms reach the target. No rates, curves or differences before then.`));
  } else if (primary === "not-computed") {
    box.append(element("p", "observatory-answer", "Readout open: line survival is not computed by the dashboard; run python3 scripts/effort_trial_analysis.py."));
  } else {
    const s7 = secondary.survival_7d, s14 = secondary.survival_14d, corr = secondary.corrective_share;
    box.append(element("p", "observatory-answer", `30-day line survival: ${arms(primary.survival_30d)} · medium − xhigh CI 90/95/99%: ${band(primary.intervals?.["90"])} / ${band(primary.intervals?.["95"])} / ${band(primary.intervals?.["99"])} · non-inferiority margin ${pp(trial.margin || 0)} pp on the lower 95% limit.`));
    box.append(element("p", "observatory-answer", `Line survival at 7 days: ${arms(s7?.by_arm)} · at 14 days: ${arms(s14?.by_arm)} · corrective share of later commits: medium ${pct(corr?.medium?.share)}, xhigh ${pct(corr?.xhigh?.share)}.`));
  }
  box.append(element("p", "measurement-note", "Intention to treat: sessions count under the effort drawn before they began, not the effort used. No verdict before the gates pass."));
}

function renderObservatory(project) {
  const status = byId("observatory-status"), calibrations = byId("observatory-calibrations"), sessions = byId("observatory-sessions");
  calibrations.replaceChildren();
  sessions.replaceChildren();
  const view = project?.observatory;
  if (!project) { status.textContent = "Select a repository to see the three questions: what did you run, did it last, could you have spent less."; return; }
  if (!view) { status.textContent = "No observatory read for this repository."; return; }
  if (!view.opted_in) { status.textContent = view.answer || "Repository not in the observatory (observatory.projects)."; return; }
  if (!view.available) { status.textContent = `Observatory unavailable: ${view.error || "N/A"}`; return; }
  status.textContent = `${integer(view.sessions.length)} recorded session(s) · levels built: ${(view.parameters?.levels_built || []).join(", ")} · each answer carries its badge; no badge = no evidence to judge.`;
  for (const c of view.calibrations || []) {
    const box = element("div", "observatory-block");
    box.append(element("h3", null, `Calibrated on your repository · ${c.cli} · ${c.model}`));
    if (c.error) box.append(element("p", "measurement-note", `Unreadable analysis: ${c.error}`));
    for (const [effort, v] of Object.entries(c.by_effort || {})) box.append(element("p", "observatory-answer", `At ${effort}: [${v.badge || "no badge"}] ${v.answer}`));
    if (c.limits) box.append(element("p", "measurement-note", c.limits));
    calibrations.append(box);
  }
  for (const s of (view.sessions || []).slice(-10).reverse()) {
    const box = element("div", "observatory-block");
    box.append(element("h3", null, `Session ${String(s.session_id).slice(0, 8)} · ${s.source || "CLI N/A"} · started ${s.started_at ?? "N/A"}`));
    for (const q of s.questions || []) {
      box.append(element("p", "observatory-answer", `${q.question} [${q.badge || "no badge"}] ${q.answer}`));
      if (q.limits) box.append(element("p", "measurement-note", q.limits));
    }
    sessions.append(box);
  }
}

function renderNavigation() {
  const snapshot = state.snapshot;
  const focused = document.activeElement?.id;
  setText("overview-count", snapshot.projects.length);
  setText("available-count", state.transportError ? "Stale read" : `${snapshot.aggregate.projects_available} readable`);
  byId("overview-nav").classList.toggle("is-active", !state.selectedProject);
  const list = byId("project-nav");
  list.replaceChildren();
  snapshot.projects.forEach((project) => {
    const button = element("button", `project-button${project.project_id === state.selectedProject ? " is-active" : ""}`);
    button.type = "button";
    button.id = `project-nav-${project.project_id}`;
    button.setAttribute("aria-label", `Open project ${project.name}`);
    const status = projectStatus(project);
    button.append(element("span", `project-dot ${status}`), element("span", "project-name", project.name), element("span", "project-tasks", `${project.activity?.sessions || 0} sessions`));
    button.addEventListener("click", () => { state.selectedProject = project.project_id; render(); });
    list.append(button);
    if (button.id === focused) button.focus({preventScroll:true});
  });
}

function projectStatus(project) {
  return !state.transportError && project.available ? project.objective.status : "unavailable";
}

function renderProjects() {
  const body = byId("project-table-body");
  body.replaceChildren();
  state.snapshot.projects.forEach((project) => {
    const metrics = project.metrics;
    const activity = project.activity || {};
    const row = document.createElement("tr");
    const cells = [
      project.name,
      statusLabel(projectStatus(project)),
      activity.sessions || 0,
      activityTokens(activity),
      terminalMoney(activity),
      percent(metrics.reliable_first_pass_rate),
      money(metrics.cost_usd_per_reliable),
      percent(metrics.observation_coverage),
    ];
    cells.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 1) cell.append(element("span", `table-status ${projectStatus(project)}`, value));
      else cell.textContent = value;
      row.append(cell);
    });
    row.addEventListener("click", () => { state.selectedProject = project.project_id; render(); });
    body.append(row);
  });
  setText("projects-summary", `${state.snapshot.projects.length} registered`);
}

function recentTasks() {
  const project = selectedProject();
  const rows = project ? project.recent_tasks.map((task) => ({...task, stale: state.transportError || project.stale})) : state.snapshot.projects.flatMap((item) => item.recent_tasks.map((task) => ({ ...task, project_name: item.name, stale: state.transportError || item.stale })));
  return rows.sort((a, b) => String(b.completed_at || "").localeCompare(String(a.completed_at || ""))).slice(0, 20);
}

function taskRoute(task) {
  const provider = task.served_provider || task.provider || task.requested_provider || "provider N/A";
  const model = task.served_model || task.model || task.requested_model || "model N/A";
  return `${provider}/${model}`;
}

function renderActivity(tasks) {
  const list = byId("activity-list");
  list.replaceChildren();
  if (!tasks.length) { list.append(element("p", "empty-copy", "No terminal receipt. The funnel will start as soon as an instrumented task finishes.")); return; }
  tasks.forEach((task) => {
    const row = element("div", "activity-row");
    row.append(element("span", `activity-status ${task.status || ""}`));
    const main = element("div", "activity-main");
    main.append(element("strong", "", task.task_id || "task without ID"), element("span", "", `${task.project_name || ""} · ${task.status || "N/A"} · ${taskRoute(task)}`));
    const cost = task.cost_usd != null && task.cost_source && task.cost_status ? `${money(task.cost_usd)} · ${task.cost_status} · ${task.cost_source}` : "cost N/A";
    main.append(element("span", "", task.acceptance_summary && /^[a-f0-9]{64}$/.test(task.acceptance_sha256 || "") ? `declared acceptance · ${task.acceptance_summary.passed} PASS / ${task.acceptance_summary.failed} FAIL · authorship not authenticated` : "declared acceptance / not observed by the controller"));
    const retained = task.retention;
    main.append(element("span", "", `${localDateTime(task.completed_at)} · ${task.stale ? "stale data · " : ""}contribution: declared terminal${task.matched_start ? " · closed a recorded start" : ""}${task.cost_usd != null ? " · cost reported" : ""}${retained?.inputs_recoverable === true ? " · input preserved at last check" : task.input_sha256 ? " · input reference" : ""}${retained?.candidate_recoverable === true ? " · candidate preserved at last check" : ""}${retained?.inputs_recoverable === true ? ` (${localDateTime(retained.checked_at)}; not current integrity)` : ""} · replay not qualified · causal gain not attributed`));
    row.append(main, element("span", "activity-meta", cost));
    list.append(row);
  });
}

function renderRoutes(metrics) {
  const list = byId("route-list");
  list.replaceChildren();
  const verified = metrics.routes || [];
  const routes = verified.length ? verified : (metrics.activity?.routes || []);
  if (!routes.length) { list.append(element("p", "empty-copy", "No route observed. Provider and model appear after the first log or receipt.")); return; }
  routes.forEach((route) => {
    const row = element("div", "route-row");
    const main = element("div", "route-main");
    main.append(element("strong", "", `${route.provider}/${route.model}`), element("span", "", verified.length ? `${route.task_class || "unclassified"} · ${route.effort || "effort N/A"} · ${route.binding}` : "observed local activity"));
    const values = element("div", "route-metrics");
    const provenance = `${route.cost_accounting_status || "N/A"} · ${Object.keys(route.cost_sources || {}).sort().join(", ") || "source N/A"}`;
    values.append(
      element("strong", "", verified.length ? `${route.reliable}/${route.reliable_known}` : `${route.sessions}`),
      element("strong", "", money(verified.length ? route.cost_usd_per_reliable : route.cost_usd_estimate)),
      element("span", "", verified.length ? "accepted with declared D7" : `${integer(route.tokens)} tokens`),
      element("span", "", verified.length ? `USD / declared first-pass · ${provenance}` : "optional API-equiv.")
    );
    row.append(main, values);
    list.append(row);
  });
}

function diagnostics(metrics, project) {
  const values = [];
  if (metrics.objective?.status !== "on-target" && metrics.objective?.primary_action) values.push(metrics.objective.primary_action);
  if (!metrics.started_tasks) values.push("Instrumentation inactive: no task started with 007 begin.");
  if (metrics.active_tasks) values.push(`${metrics.active_tasks} started task(s) still without a terminal receipt.`);
  if (metrics.unstarted_terminal_tasks) values.push(`${metrics.unstarted_terminal_tasks} historical receipt(s) have no matching start; new records are rejected.`);
  if (metrics.cost_coverage !== 1) values.push(`Cost coverage ${percent(metrics.cost_coverage)}; the KPI requires 100% of receipts.`);
  if (metrics.activity?.sessions && metrics.activity.reported_cost_coverage !== 1) values.push(`Terminal cost covers ${percent(metrics.activity.reported_cost_coverage)} of local sessions; external estimates do not close this gate.`);
  if (metrics.escape_7d_pending_tasks) values.push(`${metrics.escape_7d_pending_tasks} task(s) without a D7 follow-up; the passage of time does not prove there was no escape.`);
  if (metrics.tasks && metrics.authority_coverage !== 1) values.push(`Envelope present in ${percent(metrics.authority_coverage)} of outcomes; absence stays not observed.`);
  if (metrics.friction_blocks) values.push(`${metrics.friction_blocks} allowed action(s) were blocked: fence friction to investigate.`);
  if (metrics.unclassified_blocks) values.push(`${metrics.unclassified_blocks} block(s) fell outside the declared envelope.`);
  const touch = metrics.touch?.["30"];
  if (!touch || touch.rate == null) values.push(`Touch 30d: ${touch?.reason || "N/A"}.`);
  const projects = project ? [project] : state.snapshot.projects;
  const invalidReceipts = projects.reduce((total, item) => total + (item.invalid_receipts?.length || 0), 0);
  const invalidStarts = projects.reduce((total, item) => total + (item.invalid_task_starts?.length || 0), 0);
  if (invalidReceipts) values.push(`${invalidReceipts} invalid receipt(s) were excluded from the metrics.`);
  if (invalidStarts) values.push(`${invalidStarts} invalid start(s) were excluded from the metrics.`);
  return values;
}

function renderDiagnostics(metrics, project) {
  const values = diagnostics(metrics, project);
  setText("diagnostic-count", values.length);
  const list = byId("diagnostic-list");
  list.replaceChildren();
  if (!values.length) values.push("No known data gaps in this scope.");
  values.forEach((value) => list.append(element("li", "", value)));
}

function renderComparisonChart(evidence) {
  const host = byId("comparison-chart"); host.replaceChildren();
  const arms = [evidence?.old,evidence?.new];
  const valid = evidence?.status === "supported-task-local" && typeof evidence?.experiment_id === "string"
    && Number.isInteger(evidence?.sample?.cells) && evidence.sample.cells > 0
    && evidence?.served_identity?.total_cells === evidence.sample.cells
    && evidence?.served_identity?.verified_cells === evidence.sample.cells
    && evidence?.pricing?.source?.startsWith("rate-card-estimate:")
    && arms.every(arm => Number.isInteger(arm?.accepted) && arm.accepted > 0
      && Number.isInteger(arm.cells) && arm.cells >= arm.accepted
      && Number.isFinite(arm.cost_usd_total) && arm.cost_usd_total >= 0
      && Number.isFinite(arm.cost_usd_per_accepted) && arm.cost_usd_per_accepted >= 0
      && Math.abs(arm.cost_usd_total/arm.accepted-arm.cost_usd_per_accepted) < 1e-9);
  setText("comparison-chart-note", valid ? `${evidence.experiment_id} · global history, not the project's current result · estimated API-equivalent USD per acceptance, ${arms[0].accepted}/${arms[1].accepted} acceptances; source ${evidence.pricing.source}. Not billing, and not a new v2 ROI.` : "Comparison/cost/basis unavailable or inconsistent; N/A, never zero.");
  if (!valid) { host.append(element("p", "empty-copy", "USD comparison N/A.")); return; }
  const maximum = Math.max(1,...arms.map(arm => arm.cost_usd_per_accepted));
  const svg = svgNode("svg", {viewBox:"0 0 900 190",role:"img","aria-label":"OLD and NEW from the historical experiment, estimated API-equivalent USD per acceptance"});
  arms.forEach((arm,index) => {
    const label = svgNode("text", {x:8,y:40+index*70,class:"count-label"});
    label.textContent = `${index ? "NEW" : "OLD"} · ${money(arm.cost_usd_per_accepted)}`;
    const bar = svgNode("rect", {x:180,y:20+index*70,width:660*arm.cost_usd_per_accepted/maximum,height:30,fill:index ? "var(--cyan)" : "var(--amber)"});
    const title = svgNode("title"); title.textContent = `${arm.policy}: ${money(arm.cost_usd_total)} / ${arm.accepted} acceptances per the artifact`;
    bar.append(title); svg.append(label,bar);
  });
  host.append(svg);
  host.append(element("p", "measurement-note", `OLD ${money(arms[0].cost_usd_per_accepted)} / acceptance · NEW ${money(arms[1].cost_usd_per_accepted)} / acceptance · estimated API-equivalent USD.`));
}

function renderEvidence() {
  const evidence = state.snapshot.causal_evidence;
  renderComparisonChart(evidence);
  const sample = evidence?.sample || {};
  const oldCosts = evidence?.old?.cell_cost_usd || [];
  const newCosts = evidence?.new?.cell_cost_usd || [];
  const oldWall = evidence?.old?.cell_wall_s || [];
  const newWall = evidence?.new?.cell_wall_s || [];
  const identity = evidence?.served_identity || {};
  const verifiedIdentity = Number.isInteger(sample.cells) && sample.cells > 0 && identity.total_cells === sample.cells && identity.verified_cells === sample.cells;
  setText("causal-strength", evidence?.status === "supported-task-local" ? "Local support" : "Not proven");
  setText("causal-sample", sample.tasks == null ? "Sample N/A" : `${sample.tasks} real task(s) · ${sample.accepted}/${sample.cells} accepted cells · ${verifiedIdentity ? "served identity verified" : `identity ${identity.verified_cells ?? "N/A"}/${identity.total_cells ?? "N/A"}; verification incomplete`}`);
  setText("causal-scope", "Global historical experiment · does not measure the selected project's current gain.");
  setText("causal-old-route", `${evidence?.old?.policy || "Route N/A"} · ${evidence?.old?.accepted ?? "N/A"}/${evidence?.old?.cells ?? "N/A"} accepted`);
  setText("causal-new-route", `${evidence?.new?.policy || "Route N/A"} · ${evidence?.new?.accepted ?? "N/A"}/${evidence?.new?.cells ?? "N/A"} accepted`);
  setText("causal-pricing", evidence?.pricing?.status?.includes("estimate") ? "USD estimated from a rate card; not provider billing." : "Cost as per the artifact's provenance.");
  setText("causal-claim", evidence?.claim || "No causal experiment published.");
  setText("causal-boundary", evidence?.boundary || "Operational use does not prove causality.");
  setText("causal-old-cost", money(evidence?.old?.cost_usd_per_accepted));
  setText("causal-new-cost", money(evidence?.new?.cost_usd_per_accepted));
  setText("causal-cost-delta", evidence?.delta?.cost_pct == null ? "N/A" : `${decimal(evidence.delta.cost_pct, 1)}%`);
  setText("causal-latency-delta", evidence?.delta?.wall_per_accepted_pct == null ? "N/A" : `${decimal(evidence.delta.wall_per_accepted_pct, 1)}%`);
  setText("causal-spread", oldCosts.length && newCosts.length && oldWall.length && newWall.length
    ? `Range across the 3 replicas · cost/cell CONTROL ${money(Math.min(...oldCosts))}–${money(Math.max(...oldCosts))} · TREATMENT ${money(Math.min(...newCosts))}–${money(Math.max(...newCosts))} · time CONTROL ${integer(Math.min(...oldWall))}–${integer(Math.max(...oldWall))}s · TREATMENT ${integer(Math.min(...newWall))}–${integer(Math.max(...newWall))}s`
    : "Spread N/A");
}

// ---- verdict home: what the evidence supports for the selected scope, never more
const JUDGED = ["above-necessary", "good-choice", "no-cheaper-proven", "cannot-spend-less"];
const SAYS = {
  "above-necessary": (entry) => [`Above what was needed: ${entry.gain?.effort || "less"} is enough`, "warn"],
  "good-choice": () => ["Good choice", "good"],
  "no-cheaper-proven": () => ["Nothing cheaper proven", "plain"],
  "cannot-spend-less": () => ["Lower effort not proven", "plain"],
};
const scopeProjects = () => { const project = selectedProject(); return project ? [project] : state.snapshot.projects; };
const calibrationsOf = (projects) => projects.flatMap((project) => (project.observatory?.calibrations || []).filter((item) => !item.error).map((item) => ({ ...item, repository: project.name })));
const signedPercent = (value) => value == null ? "N/A" : `${value > 0 ? "−" : "+"}${Math.abs(value * 100).toFixed(0)}%`;

function sessionJudgement(session, project) {
  const calibration = (project.observatory?.calibrations || []).find((item) => item.cli === session.source && item.model === session.model);
  const entry = calibration?.by_effort?.[session.effort];
  const [says, tone] = SAYS[entry?.verdict]?.(entry) || ["No evidence to change it", "plain"];
  return { says, tone, level: entry?.badge || "Observed" };
}

function liveSessions(projects, now) {
  return projects.flatMap((project) => (project.activity?.recent_sessions || []).filter((session) => session.status === "active").map((session) => {
    const started = Date.parse(session.started_at);
    return { repo: project.name, model: session.model, effort: session.effort, tokens: session.usage?.total_tokens,
             minutes: Number.isFinite(started) ? Math.max(0, Math.round((now - started) / 60000)) : null, ...sessionJudgement(session, project) };
  }));
}

function effortScores(projects, now) {
  const sessions = projects.flatMap((project) => (project.observatory?.sessions || [])).filter((session) => now - Date.parse(session.started_at) <= 30 * 86400000);
  const judged = sessions.filter((session) => JUDGED.includes(session.questions?.[2]?.verdict));
  const enough = judged.filter((session) => session.questions[2].verdict !== "above-necessary");
  const tokens = (rows) => rows.reduce((sum, session) => sum + (session.total_tokens || 0), 0);
  const every = projects.flatMap((project) => project.observatory?.sessions || []);  // a 30-day window only matures on older sessions
  const mature = every.map((session) => session.durability?.["30"]).filter((window) => window?.status === "mature" && window.lines_added);
  const added = mature.reduce((sum, window) => sum + window.lines_added, 0);
  const calibrated = projects.filter((project) => calibrationsOf([project]).length).length;
  return { quota: tokens(judged) ? tokens(enough) / tokens(judged) : null, enough: enough.length, judged: judged.length, sessions: sessions.length,
           lines: added ? mature.reduce((sum, window) => sum + window.lines_surviving, 0) / added : null, calibrated, repositories: projects.length,
           blinded: every.some((session) => typeof session.durability === "string") };
}

function bestVerdict(calibrations) {
  for (const calibration of calibrations) {
    const efforts = Object.keys(calibration.by_effort || {});
    const effort = efforts.find((name) => calibration.by_effort[name].verdict === "good-choice");
    if (effort) return { calibration, effort, entry: calibration.by_effort[effort] };
  }
  return null;
}

function thesisClaims(best, report) {
  const measured = Boolean(best);
  const durable = report?.durability === "PROVEN" ? ["PROVEN", "good"] : report?.durability === "KILL" ? ["FAILED", "bad"] : measured ? ["NOT PROVEN", "warn"] : ["NO EVIDENCE", "plain"];
  const supported = measured ? ["SUPPORTED", "good"] : ["NO EVIDENCE", "plain"];
  // same_change_reachable is the interval rule; the older point-estimate same_change called one null run in three a loss
  const sameVerdict = report?.same_change_reachable;
  const same = sameVerdict === "PROVEN" ? ["PROVEN", "good"] : sameVerdict === "KILL" ? ["FAILED", "bad"] : measured ? ["NOT PROVEN", "warn"] : ["NO EVIDENCE", "plain"];
  return [
    { id: "claim-reasoning", claim: "Less reasoning", state: supported, evidence: measured ? "Effort changed what the model actually did." : "Run a replay on this repository." },
    { id: "claim-waiting", claim: "Less waiting", state: supported, evidence: measured ? `${percent(best.entry.gain?.time_reduction)} less agent time per accepted change.` : "Run a replay on this repository." },
    { id: "claim-quota", claim: "Less quota", state: measured ? ["ESTIMATED", "warn"] : ["NO EVIDENCE", "plain"], evidence: measured ? `${percent(best.entry.gain?.cost_reduction)} less estimated cost per accepted change: a price estimate, not a quota meter.` : "Run a replay on this repository." },
    { id: "claim-change", claim: "The same change", state: same, evidence: sameVerdict === "PROVEN" ? "Non-inferior on behaviour the agent never saw." : sameVerdict === "KILL" ? "Lost more than the margin on behaviour the agent never saw." : measured ? "No accepted change lost, but no lab report bounds the loss." : "Run a replay on this repository." },
    { id: "claim-durable", claim: "Durable", state: durable, evidence: report?.durability === "PROVEN" ? "Survived the next real change, within the margin." : report?.durability === "KILL" ? "Lost more than the margin at the next real change." : "No instrument has shown it can see the difference yet." },
  ];
}

function textBlock(className, parts) {
  const box = element("div", className);
  for (const [tag, cls, text] of parts) box.append(element(tag, cls, text));
  return box;
}

function renderLive(rows, generatedAt) {
  const body = byId("live-rows");
  body.replaceChildren();
  for (const row of rows) {
    const line = element("tr");
    const cells = [[row.repo], [row.model, "mono"], [row.effort, "mono"], [row.minutes == null ? "N/A" : `${row.minutes} min`, "mono num"], [row.tokens == null ? "N/A" : integer(row.tokens), "mono num"], [row.says, `tone-${row.tone}`], [row.level, "mono dim"]];
    for (const [text, cls] of cells) line.append(element("td", cls, text));
    body.append(line);
  }
  byId("live-table").hidden = !rows.length;
  byId("live-empty").hidden = rows.length > 0;
  setText("live-count", `${rows.length} session${rows.length === 1 ? "" : "s"} · read ${localDateTime(generatedAt)}`);
}

function renderScores(scores) {
  const items = [
    [scores.quota == null ? "N/A" : percent(scores.quota), "Quota at enough effort", scores.judged ? "Weighted by tokens, not sessions." : "No recent session in a calibrated repository.", scores.quota != null && scores.quota < .5 ? "warn" : "plain"],
    [scores.judged ? `${scores.enough}/${scores.judged}` : "N/A", "Sessions at enough effort", `Of ${scores.sessions} recorded in 30 days, ${scores.judged} can be judged.`, "plain"],
    [scores.lines == null ? "N/A" : percent(scores.lines), "Lines still alive at 30 days", scores.lines == null ? "Hidden or not mature yet." : `Linked to sessions, not proof of quality.${scores.blinded ? " Trial sessions stay hidden." : ""}`, "plain"],
    [`${scores.calibrated}/${scores.repositories}`, "Repositories calibrated", "The rest are only observed.", "plain"],
  ];
  byId("verdict-scores").replaceChildren(...items.map(([value, label, detail, tone]) => textBlock("verdict-score", [["strong", `tone-${tone}`, value], ["span", null, label], ["small", null, detail]])));
}

function renderLadder(best) {
  const box = byId("effort-ladder");
  box.replaceChildren();
  byId("ladder-band").hidden = !best;
  if (!best) return;
  const rows = Object.entries(best.calibration.arms || {});
  const slowest = Math.max(...rows.map(([, arm]) => arm.wall_per_accepted_s || 0));
  const top = rows.at(-1)?.[1].accepted;
  for (const [effort, arm] of rows) {
    const line = element("div", `ladder-row${effort === best.effort ? " is-enough" : ""}`);
    const track = element("div", "ladder-track");
    const bar = element("div", "ladder-bar");
    bar.style.width = `${slowest ? (arm.wall_per_accepted_s || 0) / slowest * 100 : 0}%`;
    track.append(bar);
    const note = effort === best.effort ? ["enough", "good"] : effort === rows.at(-1)[0] ? ["reference", "plain"] : arm.accepted < top ? [`loses ${top - arm.accepted}`, "warn"] : ["", "plain"];
    line.append(element("span", "mono", effort), track, element("span", "mono num", arm.wall_per_accepted_s == null ? "N/A" : `${arm.wall_per_accepted_s.toFixed(0)} s`), element("span", "mono num", `${arm.accepted}/${arm.units}`), element("span", `num tone-${note[1]}`, note[0]));
    box.append(line);
  }
}

function renderVerdict(project) {
  const projects = scopeProjects();
  const now = Date.parse(state.snapshot.generated_at);
  const calibrations = calibrationsOf(projects);
  const best = bestVerdict(calibrations);
  const report = state.snapshot.lab_report;
  const scope = project?.name || "all repositories";
  const durable = report?.durability === "PROVEN";
  const reach = project ? "" : ` · calibrated in ${projects.filter((item) => calibrationsOf([item]).length).length} of ${projects.length}`;
  setText("verdict-kicker", best ? `${best.calibration.model} · ${best.calibration.repository}${reach}` : `${scope} · no calibration yet`);
  setText("verdict-title", best ? `${best.effort} is enough.` : "No verdict yet.");
  setText("verdict-lede", best ? `Tests accept the same changes with ${percent(best.entry.gain?.time_reduction)} less agent time. ${durable ? "They also survived the next real change." : "Whether those changes last is not shown yet."}`
    : "007 will not guess which effort is enough for your code. It replays your own commits at two efforts and tells you what the evidence supports.");
  const gain = best?.entry.gain;
  const arm = best?.calibration.arms?.[best.effort], reference = gain && best.calibration.arms?.[gain.against];
  byId("verdict-gains").replaceChildren(...(best ? [
    [signedPercent(gain?.time_reduction), "agent time", "per accepted change"],
    [signedPercent(gain?.cost_reduction), "cost", "per accepted change"],
    [arm && reference ? `${arm.accepted} = ${reference.accepted}` : "N/A", "accepted", `${best.effort} and ${gain?.against}`],
  ] : []).map(([value, label, detail]) => textBlock("verdict-gain", [["strong", null, value], ["span", null, label], ["small", null, detail]])));
  renderLive(liveSessions(projects, now), state.snapshot.generated_at);
  renderScores(effortScores(projects, now));
  const claims = thesisClaims(best, report);
  for (const claim of claims) for (const id of [claim.id, claim.extra].filter(Boolean)) byId(id).className = `claim-word claim-${claim.state[1]}`;
  byId("verdict-claims").replaceChildren(...claims.map((claim) => textBlock("verdict-claim", [["span", `mono tone-${claim.state[1]}`, claim.state[0]], ["strong", null, claim.claim], ["small", null, claim.evidence]])));
  renderLadder(best);
  byId("verdict-advice").replaceChildren(...calibrations.map((calibration) => {
    const found = bestVerdict([calibration]);
    return textBlock("verdict-advice-row", [["div", "mono", `${calibration.cli} · ${calibration.model} · ${calibration.repository}`], ["strong", `tone-${found ? "good" : "warn"}`, found ? `use ${found.effort}` : "keep your effort"],
      ["small", null, found ? "No accepted change lost." : "No lower effort passed the gates."]]);
  }));
  if (!calibrations.length) byId("verdict-advice").replaceChildren(element("p", "verdict-note", "No model calibrated in this scope."));
}

function render() {
  if (!state.snapshot) return;
  const project = selectedProject();
  const metrics = viewMetrics();
  const hasProjects = state.snapshot.projects.length > 0;
  byId("empty-state").hidden = hasProjects;
  renderNavigation();
  renderVerdict(project);
  renderHeader(metrics, project);
  renderInstrumentation(metrics);
  renderRuntimeActivity(metrics.activity);
  renderMetrics(metrics);
  renderGates(metrics.objective);
  renderTrend(metrics.trend_30d);
  renderAuthority(metrics, metrics.authority_confidence);
  renderFunnel(metrics);
  renderDataset(metrics.dataset, metrics.stale || metrics.available === false || metrics.projects_unavailable > 0);
  renderCuration(project?.curation || state.snapshot.curation, state.transportError);
  renderObservatory(project);
  renderTrial(state.snapshot.effort_trial);
  renderTemporalCharts(metrics, project);
  renderProjects();
  renderActivity(recentTasks());
  renderRoutes(metrics);
  renderEvidence();
  renderDiagnostics(metrics, project);
  setText("framework-version", `v${state.snapshot.framework_version}`);
  renderFreshness(metrics, state.snapshot.generated_at);
  setText("last-event", localDateTime(metrics.latest_event_at));
  setText("server-status", state.transportError ? "No current read · last data preserved" : "Polling every 2 seconds · one read at a time");
  byId("dashboard-content").hidden = false;
  byId("dashboard-content").setAttribute("aria-busy", "false");
}

async function loadSnapshot() {
  if (state.loading) return;
  state.loading = true;
  const previous = state.snapshot;
  let selectedAtApply, focusedAtApply;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10000);
  byId("refresh-button").classList.add("is-loading");
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store", signal:controller.signal });
    if (response.status === 503 && !previous) {
      setText("verdict-kicker", "Reading your repositories for the first time. Large registries take a minute or two.");
      setText("server-status", "First read in progress");
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const next = await response.json();
    if (next?.schema !== "007-framework/dashboard-snapshot/v1" || !Array.isArray(next.projects)
        || !next.aggregate || typeof next.generated_at !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/.test(next.generated_at)
        || !Number.isFinite(Date.parse(next.generated_at)) || previous && Date.parse(next.generated_at) < Date.parse(previous.generated_at)) throw Error("Invalid snapshot, or older than the last valid read.");
    selectedAtApply = state.selectedProject;
    focusedAtApply = document.activeElement?.id;
    state.snapshot = next;
    state.transportError = false;
    if (state.selectedProject && !state.snapshot.projects.some((item) => item.project_id === state.selectedProject)) state.selectedProject = null;
    byId("error-banner").hidden = true;
    render();
  } catch (error) {
    if (state.snapshot !== previous) state.selectedProject = selectedAtApply;
    state.snapshot = previous;
    state.transportError = true;
    if (previous) render();
    else byId("dashboard-content").hidden = true;
    if (focusedAtApply) byId(focusedAtApply)?.focus({preventScroll:true});
    byId("error-banner").hidden = false;
    setText("error-banner", "Read unavailable or invalid; last data preserved, no current progress or approval.");
    setText("server-status", "No current valid read");
  } finally {
    window.clearTimeout(timeout);
    state.loading = false;
    byId("refresh-button").classList.remove("is-loading");
  }
}

byId("overview-nav").addEventListener("click", () => { state.selectedProject = null; render(); });
byId("refresh-button").addEventListener("click", loadSnapshot);
loadSnapshot();
state.timer = window.setInterval(loadSnapshot, 2000);
