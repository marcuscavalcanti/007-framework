"use strict";

const state = { snapshot: null, selectedProject: null, timer: null, loading: false };
const byId = (id) => document.getElementById(id);
const percent = (value, digits = 0) => value == null ? "N/D" : `${(value * 100).toFixed(digits)}%`;
const decimal = (value, digits = 1) => value == null ? "N/D" : Number(value).toFixed(digits);
const money = (value) => value == null ? "N/D" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", minimumFractionDigits: value < 1 ? 3 : 2 }).format(value);
const integer = (value) => new Intl.NumberFormat("pt-BR", { notation: value >= 1_000_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value || 0);
const equivalentMoney = (activity = {}) => activity.cost_usd_estimate != null ? money(activity.cost_usd_estimate) : activity.cost_usd_known_sum > 0 ? `≥ ${money(activity.cost_usd_known_sum)}` : "N/D";
const terminalMoney = (activity = {}) => activity.reported_cost_sessions ? `${activity.reported_cost_coverage < 1 ? "≥ " : ""}${money(activity.cost_usd_reported_sum)} · ${percent(activity.reported_cost_coverage)}` : "N/D";

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
  return project ? {
    ...project.metrics,
    touch: project.touch,
    evidence: project.evidence,
    objective: project.objective,
    authority_confidence: project.authority_confidence,
    trend_30d: project.trend_30d,
    activity: project.activity,
  } : state.snapshot.aggregate;
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
    "instrumentation-inactive": "Instrumentação inativa",
    "collecting": "Coletando evidência",
    "on-target": "Dentro do alvo",
    "off-target": "Fora do alvo",
    "not-measurable": "Ainda não mensurável",
    "needs-attention": "Requer atenção",
    "unavailable": "Indisponível",
  })[status] || "Estado desconhecido";
}

function reasonLabel(reason) {
  const exact = {
    "no observed task starts": "Nenhuma tarefa iniciou com 007 begin.",
    "fewer than 5 matured accepted tasks": "Ainda há menos de cinco resultados aceitos com janela de sete dias madura.",
    "reliable first-pass rate is N/D": "Reliable first-pass ainda não pode ser calculado.",
    "mean repair rounds is N/D": "Rodadas de reparo ainda não foram medidas.",
    "7-day escape rate is N/D": "A janela de sete dias ainda não amadureceu.",
    "telemetry completeness is N/D": "A telemetria ainda não foi registrada.",
    "cost coverage is N/D": "O custo ainda não foi contabilizado.",
    "reliable first-pass rate below 70%": "Reliable first-pass está abaixo de 70%.",
  };
  return exact[reason] || reason || "Sem razão registrada.";
}

function renderHeader(metrics, project) {
  setText("breadcrumb-view", project ? project.name : "Visão geral");
  setText("view-title", project ? `${project.name}: confiabilidade por dólar` : "O 007 está produzindo mais mudanças confiáveis por dólar?");
  setText("view-subtitle", project
    ? "Mesma definição do agregado: correto, first-pass e intacto após sete dias."
    : "Corretas, aceitas na primeira passagem e intactas após sete dias — sem esconder regressões ou retrabalho.");
  setText("scope-sample", `${metrics.started_tasks || 0} iniciadas · ${metrics.tasks || 0} concluídas · ${metrics.accepted || 0} aceitas`);
  setText("scope-boundary", "Uso real é evidência operacional; causalidade exige OLD×NEW.");

  const verdict = metrics.objective || { status: "not-measurable", headline: "NOT YET MEASURABLE", primary_action: "Ative a instrumentação." };
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
    ? `${started} tarefa${started === 1 ? "" : "s"} observada${started === 1 ? "" : "s"}; ${active} ainda ativa${active === 1 ? "" : "s"}`
    : "Projetos conectados; captura ainda não iniciada");
  setText("instrumentation-copy", started
    ? "Cobertura compara starts com receipts terminais. Tarefas sem begin continuam fora do denominador e aparecem como legado."
    : "O dashboard só mede tarefas que começam com 007 begin e terminam com um receipt válido.");
  byId("instrumentation-panel").classList.toggle("is-active", started > 0);
}

function renderRuntimeActivity(activity = {}) {
  setText("activity-sessions", activity.sessions || 0);
  setText("activity-active", activity.active_sessions || 0);
  setText("activity-tokens", integer(activity.tokens_total));
  setText("activity-cost", terminalMoney(activity));
  setText("activity-equivalent-cost", `Estimativa opcional: ${equivalentMoney(activity)}`);
  byId("runtime-activity-panel").classList.toggle("is-active", (activity.sessions || 0) > 0);
}

function renderMetrics(metrics) {
  setText("metric-reliable", percent(metrics.reliable_first_pass_rate));
  setText("metric-reliable-detail", `${metrics.reliable_first_pass_yes || 0}/${metrics.reliable_first_pass_known || 0} resultados maduros`);
  setTrack("track-reliable", metrics.reliable_first_pass_rate);

  setText("metric-escape", percent(metrics.escape_7d_rate));
  setText("metric-escape-detail", `${metrics.escape_7d_yes || 0} escapes · ${metrics.escape_7d_pending_tasks || 0} pendentes`);
  setTrack("track-escape", metrics.escape_7d_rate, .1);

  setText("metric-repairs", decimal(metrics.repair_rounds_mean));
  setText("metric-repairs-detail", `${metrics.repair_rounds_known_tasks || 0} tarefas com medição`);
  setTrack("track-repairs", metrics.repair_rounds_mean, 2);

  setText("metric-roi", metrics.reliable_outcomes_per_usd == null ? "N/D" : decimal(metrics.reliable_outcomes_per_usd, 2));
  setText("metric-roi-detail", `${metrics.reliable_first_pass_yes || 0} confiáveis · cobertura de custo ${percent(metrics.cost_coverage)}`);
  setTrack("track-roi", metrics.reliable_outcomes_per_usd, 2);

  setText("metric-reliable-cost", money(metrics.cost_usd_per_reliable));
  setText("metric-reliable-cost-detail", `Cobertura de custo ${percent(metrics.cost_coverage)} · inclui todas as tentativas`);
  setTrack("track-cost", metrics.cost_coverage);

  setText("metric-reliable-time", metrics.wall_s_per_reliable == null ? "N/D" : `${decimal(metrics.wall_s_per_reliable, 0)}s`);
  setText("metric-reliable-time-detail", `${metrics.wall_s_known_tasks || 0}/${metrics.tasks || 0} outcomes com tempo`);
  setTrack("track-time", metrics.wall_s_per_reliable == null ? null : 1, 1);
}

function gateActual(gate) {
  if (gate.actual == null) return "N/D";
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
      ({ pass: "PASS", fail: "FAIL", wait: "AGUARDA" })[gate.status] || "N/D",
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
    host.append(element("p", "empty-copy", "Ainda não há outcomes concluídos nos últimos 30 dias."));
    return;
  }
  const svg = svgNode("svg", { viewBox: "0 0 900 240", role: "img", "aria-label": "Proporção diária de resultados confiáveis, aceitos e não aceitos" });
  const left = 34, top = 20, height = 170, width = 840;
  const step = width / rows.length;
  const lineY = top + height * .3;
  svg.append(svgNode("line", { x1: left, y1: lineY, x2: left + width, y2: lineY, class: "trend-target" }));
  const target = svgNode("text", { x: left + 4, y: lineY - 6, class: "trend-label" });
  target.textContent = "alvo 70% confiável";
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
      title.textContent = `${row.date}: ${row.reliable} confiável, ${row.accepted_other} aceito/outro, ${row.not_accepted} não aceito`;
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
  setText("authority-confidence-label", confidence.label || "não observado");
  setText("authority-controlled", confidence.controlled || 0);
  setText("authority-controlled-detail", `${percent(confidence.controlled_coverage)} dos outcomes vinculados`);
  setText("authority-declared", confidence.declared || 0);
  setText("authority-unobserved", confidence.unobserved || 0);
  setText("authority-coverage", percent(metrics.authority_coverage));
  setText("authority-coverage-detail", `${metrics.authority_bound_tasks || 0}/${metrics.tasks || 0} outcomes vinculados`);
  setText("authority-protected", metrics.protected_blocks || 0);
  setText("authority-friction", percent(metrics.boundary_friction_rate));
  setText("authority-friction-detail", `${metrics.friction_blocks || 0}/${(metrics.allowed_executions || 0) + (metrics.friction_blocks || 0)} tentativas permitidas`);
  setText("authority-unclassified", metrics.unclassified_blocks || 0);
}

function renderFunnel(metrics) {
  setText("funnel-started", metrics.started_tasks || 0);
  setText("funnel-terminal", metrics.tasks || 0);
  setText("funnel-accepted", metrics.accepted || 0);
  setText("funnel-first-pass", metrics.accepted_first_pass_yes || 0);
  setText("funnel-reliable", metrics.reliable_first_pass_yes || 0);
  setText("funnel-maturity", `${metrics.reliable_first_pass_known || 0} maduras · ${metrics.escape_7d_pending_tasks || 0} pendentes`);
}

function renderNavigation() {
  const snapshot = state.snapshot;
  setText("overview-count", snapshot.projects.length);
  setText("available-count", `${snapshot.aggregate.projects_available} ativos`);
  byId("overview-nav").classList.toggle("is-active", !state.selectedProject);
  const list = byId("project-nav");
  list.replaceChildren();
  snapshot.projects.forEach((project) => {
    const button = element("button", `project-button${project.project_id === state.selectedProject ? " is-active" : ""}`);
    button.type = "button";
    button.setAttribute("aria-label", `Abrir projeto ${project.name}`);
    const status = project.available ? project.objective.status : "unavailable";
    button.append(element("span", `project-dot ${status}`), element("span", "project-name", project.name), element("span", "project-tasks", `${project.activity?.sessions || 0} sessões`));
    button.addEventListener("click", () => { state.selectedProject = project.project_id; render(); });
    list.append(button);
  });
}

function projectStatus(project) {
  return project.available ? project.objective.status : "unavailable";
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
      integer(activity.tokens_total),
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
  setText("projects-summary", `${state.snapshot.projects.length} registrados`);
}

function recentTasks() {
  const project = selectedProject();
  const rows = project ? project.recent_tasks : state.snapshot.projects.flatMap((item) => item.recent_tasks.map((task) => ({ ...task, project_name: item.name })));
  return rows.sort((a, b) => String(b.completed_at || "").localeCompare(String(a.completed_at || ""))).slice(0, 20);
}

function taskRoute(task) {
  const provider = task.served_provider || task.provider || task.requested_provider || "provider N/D";
  const model = task.served_model || task.model || task.requested_model || "model N/D";
  return `${provider}/${model}`;
}

function renderActivity(tasks) {
  const list = byId("activity-list");
  list.replaceChildren();
  if (!tasks.length) { list.append(element("p", "empty-copy", "Nenhum receipt terminal. O funil começará assim que uma tarefa instrumentada terminar.")); return; }
  tasks.forEach((task) => {
    const row = element("div", "activity-row");
    row.append(element("span", `activity-status ${task.status || ""}`));
    const main = element("div", "activity-main");
    main.append(element("strong", "", task.task_id || "tarefa sem ID"), element("span", "", `${task.project_name || ""} · ${task.status || "N/D"} · ${taskRoute(task)}`));
    const cost = task.cost_usd != null && task.cost_source && task.cost_status ? money(task.cost_usd) : "custo N/D";
    row.append(main, element("span", "activity-meta", cost));
    list.append(row);
  });
}

function renderRoutes(metrics) {
  const list = byId("route-list");
  list.replaceChildren();
  const verified = metrics.routes || [];
  const routes = verified.length ? verified : (metrics.activity?.routes || []);
  if (!routes.length) { list.append(element("p", "empty-copy", "Nenhuma rota observada. Provider e modelo aparecem após o primeiro log ou receipt.")); return; }
  routes.forEach((route) => {
    const row = element("div", "route-row");
    const main = element("div", "route-main");
    main.append(element("strong", "", `${route.provider}/${route.model}`), element("span", "", verified.length ? `${route.task_class || "unclassified"} · ${route.effort || "effort N/D"} · ${route.binding}` : "atividade local observada"));
    const values = element("div", "route-metrics");
    values.append(
      element("strong", "", verified.length ? `${route.reliable}/${route.reliable_known}` : `${route.sessions}`),
      element("strong", "", money(verified.length ? route.cost_usd_per_reliable : route.cost_usd_estimate)),
      element("span", "", verified.length ? "confiáveis 7d" : `${integer(route.tokens)} tokens`),
      element("span", "", verified.length ? "custo / confiável" : "API-equiv. opcional")
    );
    row.append(main, values);
    list.append(row);
  });
}

function diagnostics(metrics, project) {
  const values = [];
  if (metrics.objective?.status !== "on-target" && metrics.objective?.primary_action) values.push(metrics.objective.primary_action);
  if (!metrics.started_tasks) values.push("Instrumentação inativa: nenhuma tarefa começou com 007 begin.");
  if (metrics.active_tasks) values.push(`${metrics.active_tasks} tarefa(s) iniciada(s) ainda sem receipt terminal.`);
  if (metrics.unstarted_terminal_tasks) values.push(`${metrics.unstarted_terminal_tasks} receipt(s) histórico(s) não têm start correspondente; novos records são rejeitados.`);
  if (metrics.cost_coverage !== 1) values.push(`Cobertura de custo ${percent(metrics.cost_coverage)}; o KPI exige 100% dos receipts.`);
  if (metrics.activity?.sessions && metrics.activity.reported_cost_coverage !== 1) values.push(`Custo terminal cobre ${percent(metrics.activity.reported_cost_coverage)} das sessões locais; estimativas externas não fecham esse gate.`);
  if (metrics.escape_7d_pending_tasks) values.push(`${metrics.escape_7d_pending_tasks} tarefa(s) aguardam maturação de sete dias.`);
  if (metrics.tasks && metrics.authority_coverage !== 1) values.push(`Envelope presente em ${percent(metrics.authority_coverage)} dos outcomes; ausência permanece não observada.`);
  if (metrics.friction_blocks) values.push(`${metrics.friction_blocks} ação(ões) permitida(s) foram bloqueadas: atrito de fence a investigar.`);
  if (metrics.unclassified_blocks) values.push(`${metrics.unclassified_blocks} bloqueio(s) ficaram fora do envelope declarado.`);
  const touch = metrics.touch?.["30"];
  if (!touch || touch.rate == null) values.push(`Touch 30d: ${touch?.reason || "N/D"}.`);
  const projects = project ? [project] : state.snapshot.projects;
  const invalidReceipts = projects.reduce((total, item) => total + (item.invalid_receipts?.length || 0), 0);
  const invalidStarts = projects.reduce((total, item) => total + (item.invalid_task_starts?.length || 0), 0);
  if (invalidReceipts) values.push(`${invalidReceipts} receipt(s) inválido(s) foram excluídos das métricas.`);
  if (invalidStarts) values.push(`${invalidStarts} start(s) inválido(s) foram excluídos das métricas.`);
  return values;
}

function renderDiagnostics(metrics, project) {
  const values = diagnostics(metrics, project);
  setText("diagnostic-count", values.length);
  const list = byId("diagnostic-list");
  list.replaceChildren();
  if (!values.length) values.push("Nenhuma lacuna de dados conhecida neste escopo.");
  values.forEach((value) => list.append(element("li", "", value)));
}

function renderEvidence() {
  const evidence = state.snapshot.causal_evidence;
  setText("causal-claim", evidence?.claim_pt_br || evidence?.claim || "Nenhum experimento causal publicado.");
  setText("causal-boundary", evidence?.boundary_pt_br || evidence?.boundary || "Uso operacional não prova causalidade.");
  setText("causal-old-cost", money(evidence?.old?.cost_usd_per_accepted));
  setText("causal-new-cost", money(evidence?.new?.cost_usd_per_accepted));
  setText("causal-cost-delta", evidence?.delta?.cost_pct == null ? "N/D" : `${decimal(evidence.delta.cost_pct, 1)}%`);
  setText("causal-latency-delta", evidence?.delta?.median_wall_pct == null ? "N/D" : `${decimal(evidence.delta.median_wall_pct, 1)}%`);
}

function render() {
  if (!state.snapshot) return;
  const project = selectedProject();
  const metrics = viewMetrics();
  const hasProjects = state.snapshot.projects.length > 0;
  byId("empty-state").hidden = hasProjects;
  renderNavigation();
  renderHeader(metrics, project);
  renderInstrumentation(metrics);
  renderRuntimeActivity(metrics.activity);
  renderMetrics(metrics);
  renderGates(metrics.objective);
  renderTrend(metrics.trend_30d);
  renderAuthority(metrics, metrics.authority_confidence);
  renderFunnel(metrics);
  renderProjects();
  renderActivity(recentTasks());
  renderRoutes(metrics);
  renderEvidence();
  renderDiagnostics(metrics, project);
  setText("framework-version", `v${state.snapshot.framework_version}`);
  setText("last-updated", new Date(state.snapshot.generated_at).toLocaleTimeString("pt-BR"));
  setText("server-status", "Atualização a cada 2 segundos");
  byId("dashboard-content").setAttribute("aria-busy", "false");
}

async function loadSnapshot() {
  if (state.loading) return;
  state.loading = true;
  byId("refresh-button").classList.add("is-loading");
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.snapshot = await response.json();
    if (state.selectedProject && !state.snapshot.projects.some((item) => item.project_id === state.selectedProject)) state.selectedProject = null;
    byId("error-banner").hidden = true;
    render();
  } catch (error) {
    byId("error-banner").hidden = false;
    setText("error-banner", `Não foi possível atualizar o cockpit: ${error.message}`);
    setText("server-status", "Sem conexão");
  } finally {
    state.loading = false;
    byId("refresh-button").classList.remove("is-loading");
  }
}

byId("overview-nav").addEventListener("click", () => { state.selectedProject = null; render(); });
byId("refresh-button").addEventListener("click", loadSnapshot);
loadSnapshot();
state.timer = window.setInterval(loadSnapshot, 2000);
