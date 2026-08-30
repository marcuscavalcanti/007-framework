"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const state = { snapshot: null, selectedProject: null, timer: null, loading: false };

const byId = (id) => document.getElementById(id);
const percent = (value, digits = 0) => value == null ? "N/D" : `${(value * 100).toFixed(digits)}%`;
const percentNumber = (value, digits = 0) => value == null ? "N/D" : `${value.toFixed(digits)}%`;
const decimal = (value, digits = 1) => value == null ? "N/D" : Number(value).toFixed(digits);
const money = (value) => value == null ? "N/D" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", minimumFractionDigits: value < 1 ? 3 : 2 }).format(value);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

function svgElement(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function selectedProject() {
  if (!state.snapshot || !state.selectedProject) return null;
  return state.snapshot.projects.find((project) => project.project_id === state.selectedProject) || null;
}

function viewMetrics() {
  const project = selectedProject();
  return project ? { ...project.metrics, touch: project.touch, evidence: project.evidence } : state.snapshot.aggregate;
}

function setText(id, value) {
  byId(id).textContent = value == null ? "N/D" : String(value);
}

function setTrack(id, value, max = 1) {
  const bounded = value == null ? 0 : Math.max(0, Math.min(1, value / max));
  byId(id).style.width = `${bounded * 100}%`;
}

function statusLabel(status) {
  return ({ "on-target": "No alvo", "needs-attention": "Atenção necessária", collecting: "Coletando evidência" })[status] || "Coletando evidência";
}

function renderHeader(metrics, project) {
  setText("breadcrumb-view", project ? project.name : "Visão geral");
  setText("view-title", project ? project.name : "Visão geral do sistema");
  setText("view-subtitle", project
    ? "Resultados observados neste projeto com as mesmas definições do agregado."
    : "O framework está produzindo mudanças aceitas que sobrevivem sem reparo?");
  setText("scope-sample", `${metrics.tasks || 0} tarefas · ${metrics.accepted || 0} aceitas`);

  const verdict = metrics.evidence || { status: "collecting", reasons: ["sem evidência"] };
  const card = byId("verdict-card");
  card.classList.remove("on-target", "needs-attention", "collecting");
  card.classList.add(verdict.status || "collecting");
  setText("verdict-label", statusLabel(verdict.status));
  setText("verdict-reason", verdict.reasons && verdict.reasons.length ? verdict.reasons[0] : "Todos os sinais maduros estão dentro dos alvos declarados.");
}

function renderMetrics(metrics) {
  setText("metric-first-pass", percent(metrics.first_pass_rate));
  setText("metric-first-pass-detail", `${metrics.first_pass_yes || 0}/${metrics.first_pass_known || 0} observações conhecidas`);
  setTrack("track-first-pass", metrics.first_pass_rate);

  setText("metric-cost", money(metrics.cost_usd_per_accepted));
  const costStatus = metrics.cost_accounting_status ? ` · ${metrics.cost_accounting_status}` : "";
  setText("metric-cost-detail", `Cobertura ${percent(metrics.cost_coverage)}${costStatus}`);
  setTrack("track-cost", metrics.cost_coverage);

  setText("metric-repairs", decimal(metrics.repair_rounds_mean, 2));
  setText("metric-repairs-detail", `${metrics.repair_rounds_known_tasks || 0} tarefas com medição`);
  setTrack("track-repairs", metrics.repair_rounds_mean, 2);

  const touch = metrics.touch && metrics.touch["30"];
  setText("metric-touch", percentNumber(touch && touch.rate));
  setText("metric-touch-detail", touch && touch.rate != null
    ? `${touch.agent_lines_added || 0} linhas atribuídas`
    : (touch && touch.reason) || "Atribuição Git não disponível");
  setTrack("track-touch", touch && touch.rate, 100);

  setText("metric-escape", percent(metrics.escape_7d_rate));
  setText("metric-escape-detail", `${metrics.escape_7d_pending_tasks || 0} janelas pendentes`);
  setTrack("track-escape", metrics.escape_7d_rate);

  setText("metric-telemetry", percent(metrics.telemetry_completeness));
  setText("metric-telemetry-detail", `${metrics.telemetry_known || 0}/${metrics.telemetry_possible || 0} campos medidos`);
  setTrack("track-telemetry", metrics.telemetry_completeness);
}

function renderNavigation() {
  const snapshot = state.snapshot;
  setText("overview-count", snapshot.aggregate.projects_total || 0);
  setText("available-count", `${snapshot.aggregate.projects_available || 0} ativos`);
  byId("overview-nav").classList.toggle("is-active", !state.selectedProject);

  const list = byId("project-nav");
  list.replaceChildren();
  snapshot.projects.forEach((project) => {
    const button = element("button", `project-button${project.project_id === state.selectedProject ? " is-active" : ""}`);
    button.type = "button";
    button.setAttribute("aria-label", `Abrir projeto ${project.name}`);
    button.addEventListener("click", () => {
      state.selectedProject = project.project_id;
      render();
    });
    const dotStatus = project.available ? project.evidence.status : "unavailable";
    button.append(
      element("span", `project-dot ${dotStatus}`),
      element("span", "project-name", project.name),
      element("span", "project-tasks", project.metrics.tasks || 0),
    );
    list.append(button);
  });
}

function projectStatus(project) {
  return project.available ? project.evidence.status : "unavailable";
}

function renderProjects() {
  const body = byId("project-table-body");
  body.replaceChildren();
  state.snapshot.projects.forEach((project) => {
    const row = document.createElement("tr");
    const status = projectStatus(project);
    const touch = project.touch && project.touch["30"];
    const cells = [
      project.name,
      statusLabel(status === "unavailable" ? "collecting" : status),
      project.metrics.tasks || 0,
      percent(project.metrics.first_pass_rate),
      money(project.metrics.cost_usd_per_accepted),
      percentNumber(touch && touch.rate),
    ];
    cells.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 1) {
        const badge = element("span", "table-status");
        badge.append(element("i", `project-dot ${status}`), document.createTextNode(value));
        cell.append(badge);
      } else {
        cell.textContent = value;
      }
      row.append(cell);
    });
    row.tabIndex = 0;
    row.addEventListener("click", () => { state.selectedProject = project.project_id; render(); });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        state.selectedProject = project.project_id;
        render();
      }
    });
    body.append(row);
  });
  setText("projects-summary", `${state.snapshot.aggregate.projects_total || 0} registrados`);
}

function renderOutcome(metrics) {
  const chart = byId("outcome-chart");
  chart.replaceChildren();
  const total = metrics.tasks || 0;
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const centerX = 360;
  const centerY = 102;
  chart.append(svgElement("circle", { cx: centerX, cy: centerY, r: radius, fill: "none", stroke: "rgba(255,255,255,.055)", "stroke-width": 18 }));
  let offset = 0;
  const values = [
    [metrics.accepted || 0, "#62e6a7"],
    [metrics.blocked || 0, "#ff7185"],
    [metrics.no_op || 0, "#78a7ff"],
    [Math.max(0, total - (metrics.accepted || 0) - (metrics.blocked || 0) - (metrics.no_op || 0)), "#425a72"],
  ];
  if (total) {
    values.forEach(([count, color]) => {
      if (!count) return;
      const length = circumference * count / total;
      const gap = Math.min(5, length * .18);
      chart.append(svgElement("circle", {
        cx: centerX, cy: centerY, r: radius, fill: "none", stroke: color,
        "stroke-width": 18, "stroke-linecap": "round",
        "stroke-dasharray": `${Math.max(0, length - gap)} ${circumference}`,
        "stroke-dashoffset": -offset, transform: `rotate(-90 ${centerX} ${centerY})`,
      }));
      offset += length;
    });
  }
  setText("outcome-total", total);
}

function recentTasks() {
  const project = selectedProject();
  const rows = project
    ? project.recent_tasks.map((task) => ({ ...task, project_name: project.name }))
    : state.snapshot.projects.flatMap((item) => item.recent_tasks.map((task) => ({ ...task, project_name: item.name })));
  return rows.sort((a, b) => String(b.completed_at || "").localeCompare(String(a.completed_at || ""))).slice(0, 20);
}

function renderTrend(tasks) {
  const chart = byId("trend-chart");
  chart.replaceChildren();
  const known = tasks.filter((task) => task.first_pass === "yes" || task.first_pass === "no").reverse();
  setText("trend-sample", `${known.length} observações`);
  const left = 44, right = 696, top = 22, bottom = 205;
  [0, .5, .7, 1].forEach((value) => {
    const y = bottom - value * (bottom - top);
    chart.append(svgElement("line", { x1: left, y1: y, x2: right, y2: y, stroke: value === .7 ? "rgba(98,230,167,.25)" : "rgba(151,181,216,.08)", "stroke-dasharray": value === .7 ? "5 6" : "0" }));
    const label = svgElement("text", { x: 4, y: y + 4, fill: value === .7 ? "#62e6a7" : "#60758a", "font-size": 10 });
    label.textContent = `${Math.round(value * 100)}%`;
    chart.append(label);
  });
  if (!known.length) {
    const label = svgElement("text", { x: 360, y: 120, fill: "#60758a", "font-size": 12, "text-anchor": "middle" });
    label.textContent = "Aguardando first-pass conhecido";
    chart.append(label);
    return;
  }
  let yes = 0;
  const points = known.map((task, index) => {
    yes += int(task.first_pass === "yes");
    const x = known.length === 1 ? left : left + index * (right - left) / (known.length - 1);
    const y = bottom - (yes / (index + 1)) * (bottom - top);
    return [x, y];
  });
  const area = svgElement("path", {
    d: `M ${points[0][0]} ${bottom} L ${points.map((point) => point.join(" ")).join(" L ")} L ${points[points.length - 1][0]} ${bottom} Z`,
    fill: "rgba(85,216,255,.07)", stroke: "none",
  });
  chart.append(area);
  chart.append(svgElement("polyline", {
    points: points.map((point) => point.join(",")).join(" "), fill: "none",
    stroke: "#55d8ff", "stroke-width": 3, "stroke-linecap": "round", "stroke-linejoin": "round",
  }));
  points.forEach(([x, y], index) => {
    if (index === points.length - 1 || index % 3 === 0) {
      chart.append(svgElement("circle", { cx: x, cy: y, r: 4, fill: "#07101c", stroke: "#55d8ff", "stroke-width": 2 }));
    }
  });
}

function int(value) { return value ? 1 : 0; }

function taskRoute(task) {
  const provider = task.served_provider || task.provider || task.requested_provider || "provider N/D";
  const model = task.served_model || task.model || task.requested_model || "model N/D";
  return `${provider}/${model}`;
}

function renderActivity(tasks) {
  const list = byId("activity-list");
  list.replaceChildren();
  if (!tasks.length) {
    list.append(element("p", "empty-copy", "Nenhum receipt terminal disponível."));
    return;
  }
  tasks.slice(0, 8).forEach((task) => {
    const row = element("div", "activity-row");
    const main = element("div", "activity-main");
    main.append(
      element("strong", null, task.task_id || "task sem id"),
      element("span", null, `${task.project_name} · ${taskRoute(task)}`),
    );
    const cost = task.cost_usd != null && task.cost_source && task.cost_status
      ? `${money(task.cost_usd)} · ${task.cost_status}` : "custo N/D";
    row.append(element("i", `activity-status ${task.status || "unknown"}`), main, element("span", "activity-meta", cost));
    list.append(row);
  });
}

function renderRoutes(metrics) {
  const list = byId("route-list");
  list.replaceChildren();
  const routes = metrics.routes || [];
  if (!routes.length) {
    list.append(element("p", "empty-copy", "Nenhuma rota de modelo observada."));
    return;
  }
  routes.slice().sort((a, b) => b.tasks - a.tasks).slice(0, 8).forEach((route) => {
    const row = element("div", "route-row");
    const main = element("div", "route-main");
    main.append(
      element("strong", null, route.key),
      element("span", null, `${route.binding} · ${route.accepted}/${route.tasks} aceitas`),
    );
    const metricsNode = element("div", "route-metrics");
    metricsNode.append(
      element("strong", null, route.cost_usd_known_tasks ? money(route.cost_usd_known_sum / route.cost_usd_known_tasks) : "N/D"),
      element("strong", null, percent(route.tasks ? route.accepted / route.tasks : null)),
      element("span", null, "custo / medição"),
      element("span", null, "aceite"),
    );
    row.append(main, metricsNode);
    list.append(row);
  });
}

function diagnostics(metrics, project) {
  const values = [];
  const projects = project ? [project] : state.snapshot.projects;
  projects.forEach((item) => {
    if (!item.available) values.push(`${item.name}: ${item.error}`);
    item.invalid_receipts.forEach((error) => values.push(`${item.name}/${error.file}: receipt inválido`));
  });
  state.snapshot.registry_errors.forEach((error) => values.push(`Registro: ${error.error}`));
  if (metrics.cost_coverage !== 1) values.push(`Cobertura de custo em ${percent(metrics.cost_coverage)}; alvo obrigatório é 100%`);
  if (metrics.cost_provisional_tasks) values.push(`${metrics.cost_provisional_tasks} custo(s) provisório(s) aguardando reconciliação`);
  if (metrics.tokens_missing_tasks) values.push(`${metrics.tokens_missing_tasks} tarefa(s) sem tokens medidos`);
  if (metrics.first_pass_unknown_tasks) values.push(`${metrics.first_pass_unknown_tasks} tarefa(s) sem first-pass conhecido`);
  const touch = metrics.touch && metrics.touch["30"];
  if (touch && touch.rate == null && touch.reason) values.push(`Touch 30d: ${touch.reason}`);
  return [...new Set(values)];
}

function renderDiagnostics(metrics, project) {
  const values = diagnostics(metrics, project);
  setText("diagnostic-count", values.length);
  const list = byId("diagnostic-list");
  list.replaceChildren();
  if (!values.length) {
    list.append(element("li", null, "Nenhuma incerteza material nos dados maduros."));
    return;
  }
  values.slice(0, 8).forEach((value) => list.append(element("li", null, value)));
}

function renderEvidence() {
  const evidence = state.snapshot.causal_evidence;
  setText("causal-claim", evidence.claim);
  setText("causal-boundary", evidence.boundary);
}

function render() {
  if (!state.snapshot) return;
  const project = selectedProject();
  const metrics = viewMetrics();
  const tasks = recentTasks();
  renderNavigation();
  renderHeader(metrics, project);
  renderMetrics(metrics);
  renderOutcome(metrics);
  renderTrend(tasks);
  renderProjects();
  renderActivity(tasks);
  renderRoutes(metrics);
  renderDiagnostics(metrics, project);
  renderEvidence();
  setText("framework-version", `v${state.snapshot.framework_version}`);
  setText("last-updated", new Date(state.snapshot.generated_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  setText("server-status", "Conectado · atualização a cada 2s");
  byId("empty-state").hidden = state.snapshot.aggregate.projects_total !== 0;
  byId("dashboard-content").setAttribute("aria-busy", "false");
}

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  byId("refresh-button").classList.add("is-loading");
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error(`snapshot HTTP ${response.status}`);
    state.snapshot = await response.json();
    byId("error-banner").hidden = true;
    render();
  } catch (error) {
    byId("error-banner").textContent = `Não foi possível atualizar: ${error.message}`;
    byId("error-banner").hidden = false;
    setText("server-status", "Conexão interrompida");
  } finally {
    state.loading = false;
    byId("refresh-button").classList.remove("is-loading");
  }
}

function startPolling() {
  window.clearInterval(state.timer);
  state.timer = document.hidden ? null : window.setInterval(refresh, 2000);
}

byId("overview-nav").addEventListener("click", () => {
  state.selectedProject = null;
  render();
});
byId("refresh-button").addEventListener("click", refresh);
document.addEventListener("visibilitychange", () => {
  startPolling();
  if (!document.hidden) refresh();
});

refresh();
startPolling();
