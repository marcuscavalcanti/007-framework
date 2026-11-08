const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function renderer(timezone, fetcher = () => new Promise(() => {})) {
  const nodes = new Map();
  const timeouts = new Map();
  let nextTimeout = 0, clock = 0;
  const node = () => ({textContent: '', children: [], attributes:{}, style: {}, classList: {
    add() {}, remove() {}, toggle() {},
  }, addEventListener() {}, append(...items) { this.children.push(...items); },
  setAttribute(key,value) {this.attributes[key]=value;}, focus(options) { document.activeElement = this; this.focusOptions = options; },
  replaceChildren(...items) { if (this.children.includes(document.activeElement)) document.activeElement = {id:''}; this.children = items; }});
  const document = { getElementById(id) {
    for (const parent of nodes.values()) { const child = parent.children.find(item => item.id === id); if (child) return child; }
    if (!nodes.has(id)) nodes.set(id, node());
    return nodes.get(id);
  }, createElement: node, createElementNS: node};
  const intl = timezone ? {NumberFormat: Intl.NumberFormat, RelativeTimeFormat: Intl.RelativeTimeFormat, DateTimeFormat: function(locale, options) {
    return new Intl.DateTimeFormat(locale, {...options, timeZone: timezone});
  }} : Intl;
  const context = vm.createContext({ document, Intl: intl, window: { setInterval() {},
    setTimeout(callback, delay) { const id = ++nextTimeout; timeouts.set(id, {callback,at:clock+delay}); return id; },
    clearTimeout(id) { timeouts.delete(id); } }, AbortController,
    fetch: fetcher, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../dashboard/app.js'), 'utf8'), context);
  const text = item => [item.textContent, ...item.children.map(text)].join(' ');
  return { context, text: id => text(document.getElementById(id)), root: id => document.getElementById(id), timeouts,
    advance(ms) { clock += ms; for (const value of [...timeouts.values()]) if (value.at <= clock) value.callback(); } };
}

test('partial native consumption is labelled in the overview and each affected project only', () => {
  const r = renderer();
  vm.runInContext('renderRuntimeActivity({tokens_total:123,usage_incomplete_sessions:1});state.snapshot={projects:[{name:"A",available:true,objective:{status:"collecting"},metrics:{},activity:{tokens_total:123,usage_incomplete_sessions:1}},{name:"B",available:true,objective:{status:"collecting"},metrics:{},activity:{tokens_total:456,usage_incomplete_sessions:0}}]};renderProjects()', r.context);
  assert.match(r.text('activity-tokens'), /123.*partial/);
  const rows = r.root('project-table-body').children;
  assert.match(rows[0].children[3].textContent, /123.*partial/);
  assert.equal(rows[1].children[3].textContent, '456');
  vm.runInContext('renderRuntimeActivity({tokens_total:123,usage_incomplete_sessions:0})', r.context);
  assert.equal(r.text('activity-tokens'), '123');
});

test('economic totals come from the complete cohort, not accepted-only legacy sums', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({cost_usd_known_sum:2, cost_usd_known_tasks:1, tasks:2, economics:{cost_basis:"api-equivalent", cost_usd_known_sum:10, cost_usd_known_tasks:2, cost_coverage:1, cohort_tasks:2, accepted_declared:1, open_tasks:0, reasons:[], cost_usd_per_declared_accepted:10, cost_usd_per_reliable_declared:null}})', r.context);
  assert.match(r.text('value-cost'), /\$10\.00/);
  assert.match(r.text('value-cost-detail'), /api-equivalent/);
  assert.match(r.text('metric-accepted-cost'), /\$10\.00/);
  assert.equal(r.text('metric-roi'), 'N/A');
});

test('legacy quality flags and mixed project bases cannot fill economic ratios', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({reliable_outcomes_per_usd:50, cost_usd_per_reliable:0.02, cost_usd_known_sum:999, cost_usd_known_tasks:2, tasks:2, economics_by_project:[{project_id:"a"},{project_id:"b"}]})', r.context);
  assert.equal(r.text('metric-roi'), 'N/A');
  assert.equal(r.text('metric-reliable-cost'), 'N/A');
  assert.doesNotMatch(r.text('value-cost'), /999/);
  assert.match(r.text('value-cost-detail'), /project|cohort/i);
});

test('amount-only cost does not imply covered overhead or operational ROI', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({tasks:1, economics:{cohort_complete:true, cost_scope_complete:false, cost_basis:"api-equivalent", cost_usd_per_reliable_declared:2, cost_usd_per_declared_accepted:2, reasons:[]}})', r.context);
  assert.equal(r.text('metric-roi'), 'N/A');
  assert.match(r.text('metric-accepted-cost-detail'), /overhead.*N\/A/);
});

test('reconciled declared scope is visible but never causal savings', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({tasks:1, economics:{cohort_complete:true, cost_scope_complete:true, cost_basis:"api-equivalent", cost_usd_per_reliable_with_overhead_declared:5, cost_usd_per_declared_accepted:5, reasons:[]}})', r.context);
  assert.match(r.text('metric-reliable-cost'), /\$5\.00/);
  assert.match(r.text('metric-accepted-cost-detail'), /overhead.*declared/);
  assert.match(r.text('metric-roi-detail'), /not causal savings/);
});

test('truthy malformed cost scope cannot display qualified USD efficiency', () => {
  for (const scope of [1, 'true', {}]) {
    const r = renderer();
    r.context.invalidScope = scope;
    vm.runInContext('renderMetrics({economics:{cohort_complete:true, cost_scope_complete:invalidScope, cost_usd_per_reliable_with_overhead_declared:5, reasons:[]}})', r.context);
    assert.equal(r.text('metric-roi'), 'N/A');
    assert.match(r.text('metric-accepted-cost-detail'), /overhead.*N\/A/);
  }
});

test('recent receipt explains local datetime and bounded factual contribution', () => {
  const r = renderer('America/Sao_Paulo');
  vm.runInContext('renderActivity([{task_id:"case", status:"accepted", completed_at:"2026-10-13T01:30:00Z", input_sha256:"a".repeat(64), cost_basis:"api-equivalent", cost_usd:2,cost_source:"rate-card-estimate",cost_status:"provisional"}])', r.context);
  const text = r.text('activity-list');
  assert.match(text, /Oct 12, 2026.*22:30:00/);
  assert.match(text, /America\/Sao_Paulo/);
  assert.match(text, /input reference/i);
  assert.match(text, /replay not qualified/i);
  assert.doesNotMatch(text, /saved|trained|proven ROI/);
});

test('an unmeasured overview does not assert correctness or reduced rework', () => {
  const r = renderer();
  vm.runInContext('renderHeader({}, null)', r.context);
  assert.doesNotMatch(r.text('view-title'), /correct delivery|less rework/i);
  assert.match(r.text('view-title'), /evidence/i);
  assert.match(r.text('scope-sample'), /0 started.*0 completed.*0 accepted/);
  assert.match(r.text('verdict-label'), /NOT YET MEASURABLE/);
});

test('a just-completed declaration does not claim verified D7 survival', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({accepted: 1, tasks: 1, reliable_first_pass_yes: 1, reliable_first_pass_known: 1, reliable_first_pass_rate: 1})', r.context);
  assert.match(r.text('metric-reliable-detail'), /declared/i);
  assert.match(r.text('metric-reliable-detail'), /not verified/);
  assert.doesNotMatch(r.text('metric-reliable-detail'), /matur|verified survival|intact/i);
});

test('missing follow-up is not explained as verified time-window maturation', () => {
  const r = renderer();
  const labels = vm.runInContext('[reasonLabel("fewer than 5 matured accepted tasks"), reasonLabel("7-day escape rate is N/A")]', r.context);
  for (const label of labels) {
    assert.match(label, /declar/i);
    assert.doesNotMatch(label, /matur/i);
  }
});

test('provisional accounting and open attempts are visible next to USD', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({tasks: 2, active_tasks: 1, cost_usd_known_sum: 1, cost_usd_known_tasks: 2, cost_coverage: 1, cost_accounting_status: "provisional", cost_sources: {"rate-card-estimate": 2}})', r.context);
  assert.match(r.text('metric-reliable-cost-detail'), /provis/i);
  assert.match(r.text('metric-reliable-cost-detail'), /rate-card-estimate/);
  assert.match(r.text('metric-reliable-cost-detail'), /1 open/);
  vm.runInContext('renderMetrics({tasks: 2, cost_usd_known_sum: 1, cost_usd_known_tasks: 2, cost_coverage: 1, cost_accounting_status: "final", cost_sources: {"provider-reported": 2}})', r.context);
  assert.match(r.text('metric-reliable-cost-detail'), /final/);
  assert.match(r.text('metric-reliable-cost-detail'), /provider-reported/);
});

test('route costs retain the adjacent accounting source and state', () => {
  const r = renderer();
  vm.runInContext('renderRoutes({routes: [{provider:"example", model:"estimate", reliable:1, reliable_known:1, cost_usd_per_reliable:0.4, cost_sources:{"rate-card-estimate":1}, cost_accounting_status:"provisional"}, {provider:"example", model:"billed", reliable:1, reliable_known:1, cost_usd_per_reliable:0.6, cost_sources:{"provider-reported":1}, cost_accounting_status:"final"}]})', r.context);
  const rendered = r.text('route-list');
  assert.match(rendered, /provisional.*rate-card-estimate/);
  assert.match(rendered, /final.*provider-reported/);
});

test('causal identity with zero verified cells is not reported verified', () => {
  const r = renderer();
  vm.runInContext('state.snapshot = {causal_evidence: {sample: {tasks: 1, accepted: 6, cells: 6}, served_identity: {verified_cells: 0, total_cells: 6}}}; renderEvidence()', r.context);
  assert.doesNotMatch(r.text('causal-sample'), /served identity verified/);
  assert.match(r.text('causal-sample'), /0\/6/);
  vm.runInContext('state.snapshot.causal_evidence.served_identity = {verified_cells: 6, total_cells: 6}; renderEvidence()', r.context);
  assert.match(r.text('causal-sample'), /served identity verified/);
  assert.match(r.text('causal-scope'), /global|historical/i);
});

test('old acceptance counters do not authenticate the producer', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({accepted:2, accepted_controller_observed:2, accepted_declared:0})', r.context);
  assert.match(r.text('value-acceptance'), /2.*declared/i);
  assert.doesNotMatch(r.text('value-acceptance'), /controller-observed|proven/i);
});

test('old authority snapshots remain declarations', () => {
  const r = renderer();
  vm.runInContext('renderAuthority({tasks:2, authority_bound_tasks:2}, {label:"controller-observed", controlled:2, declared:0, controlled_coverage:1, unobserved:0})', r.context);
  assert.equal(r.text('authority-controlled'), '0');
  assert.equal(r.text('authority-declared'), '2');
  assert.doesNotMatch(r.text('authority-confidence-label'), /controller-observed|proven/i);
});

test('old recent-task stamps cannot authenticate acceptance', () => {
  const r = renderer();
  vm.runInContext('renderActivity([{task_id:"example", status:"accepted", acceptance_evidence:"controlled", acceptance_summary:{passed:1,failed:0}, acceptance_sha256:"a".repeat(64)}])', r.context);
  assert.doesNotMatch(r.text('activity-list'), /controller-observed|proven/i);
  assert.match(r.text('activity-list'), /declared|not authenticated/i);
});

test('static authority explanation does not authenticate writable receipts', () => {
  const html = fs.readFileSync(path.join(__dirname, '../dashboard/index.html'), 'utf8');
  assert.doesNotMatch(html, /“Controlled” means observed by/i);
  assert.match(html, /authorship.*not.*authenticated/i);
});

test('retention funnel does not turn preserved bytes into qualified replay', () => {
  const r = renderer();
  vm.runInContext('renderDataset({complete:true, scope:"retained-byte-integrity", counts:{observational:2,"inputs-retained":1,"case-retained":1,"replay-ready":0,"qualified-comparison":0}})', r.context);
  assert.equal(r.text('dataset-observational'), '2');
  assert.equal(r.text('dataset-case-retained'), '1');
  assert.equal(r.text('dataset-replay-ready'), '0');
  assert.match(r.text('dataset-boundary'), /integrity|bytes/i);
  vm.runInContext('renderDataset({complete:false, counts:null})', r.context);
  assert.equal(r.text('dataset-case-retained'), 'N/A');
  assert.match(r.text('dataset-boundary'), /incomplete|partial/i);
});

test('retention dates are historical, local and unknown rather than a polling clock', () => {
  const r = renderer('America/Sao_Paulo');
  vm.runInContext('renderDataset({complete:true,oldest_checked_at:"2026-10-13T11:00:00Z",latest_checked_at:"2026-10-13T12:00:00Z",counts:{observational:1,"case-retained":1}})', r.context);
  assert.match(r.text('dataset-boundary'), /latest.*check|check.*earlier/i);
  assert.match(r.text('dataset-boundary'), /America\/Sao_Paulo.*GMT-3/);
  assert.match(r.text('dataset-boundary'), /not current integrity/i);
  assert.match(r.text('dataset-boundary'), /oldest/i);
  vm.runInContext('renderDataset({complete:true,counts:{observational:1}})', r.context);
  assert.match(r.text('dataset-boundary'), /date.*N\/A|date.*unavailable/i);
});

test('curation checkpoint explains local time and never claims automatic training or ROI', () => {
  const r = renderer('America/Sao_Paulo');
  vm.runInContext('renderCuration({configured:true,available:true,stale:false,in_scope:true,completed_at:"2026-10-13T01:30:00Z",checkpoint_sha256:"a".repeat(64),counts:{retained:1,observational:1,excluded:0}})', r.context);
  assert.match(r.text('curation-completed'), /Oct 12, 2026.*22:30:00.*America\/Sao_Paulo/);
  assert.match(r.text('curation-summary'), /1 retained case/i);
  assert.match(r.text('curation-boundary'), /not.*train|not.*ROI/i);
  vm.runInContext('renderCuration({configured:true,available:true,in_scope:false,counts:null})', r.context);
  assert.match(r.text('curation-summary'), /outside.*scope/i);
});

test('failed curation reading and transport preserve the last dated observation as stale', () => {
  const r = renderer();
  vm.runInContext('renderCuration({configured:true,available:false,stale:true,completed_at:"2026-10-13T12:00:00Z",counts:{retained:1,observational:1,excluded:0}})', r.context);
  assert.match(r.text('curation-status'), /stale|preserved/i);
  assert.match(r.text('curation-summary'), /1 retained case/i);
  vm.runInContext('renderCuration({configured:false,counts:null})', r.context);
  assert.match(r.text('curation-status'), /not configured/i);
  assert.equal(r.text('curation-completed'), 'N/A');
});

test('curation shows bounded proposed kind and hash without claiming learning or approval', () => {
  const r = renderer();
  vm.runInContext('renderCuration({configured:true,available:true,counts:{retained:1,gate_hypotheses_declared:1,routing_hypotheses_declared:0},proposals:[{kind:"gate",source_sha256:"a".repeat(64)}]})', r.context);
  assert.match(r.text('curation-summary'), /1 declared gate proposal/i);
  assert.match(r.text('curation-boundary'), /gate.*aaaaaaaa.*review pending/i);
  assert.doesNotMatch(r.text('curation-boundary'), /promoted|trained|saved/i);
  vm.runInContext('renderCuration({configured:true,available:false,stale:true,proposals:[{kind:"gate",source_sha256:"a".repeat(64)}]})',r.context);
  assert.match(r.text('curation-status'),/stale/i);
  vm.runInContext('renderCuration({configured:true,available:true,in_scope:false,counts:null,proposals:[]})',r.context);
  assert.doesNotMatch(r.text('curation-boundary'),/aaaaaaaa/);
  vm.runInContext('renderCuration({configured:true,available:true,proposals:[{kind:"gate",source_sha256:["a".repeat(64)]}]})',r.context);
  assert.doesNotMatch(r.text('curation-boundary'),/aaaaaaaa/);
});

test('curation followups show sources and declared cases without authenticating incidents or maturity', () => {
  const r = renderer();
  vm.runInContext('renderCuration({configured:true,available:true,counts:{retained:1,observational:1,excluded:0,followup_sources:2,followup_cases:1,corrected_cases_declared:1,escaped_cases_declared:1}})', r.context);
  assert.match(r.text('curation-summary'), /2 follow-up source/i);
  assert.match(r.text('curation-summary'), /1 case\(s\) with a declared correction/i);
  assert.match(r.text('curation-summary'), /1 case\(s\) with a declared escape/i);
  assert.match(r.text('curation-boundary'), /not authenticated.*maturity/i);
  vm.runInContext('renderCuration({configured:true,available:false,stale:true,counts:{retained:1,followup_sources:2,corrected_cases_declared:1,escaped_cases_declared:1}})', r.context);
  assert.match(r.text('curation-status'), /stale/i);
  assert.match(r.text('curation-summary'), /2 follow-up source/i);
  vm.runInContext('renderCuration({configured:true,available:true,in_scope:false,counts:null})', r.context);
  assert.match(r.text('curation-summary'), /outside.*scope/i);
  assert.doesNotMatch(r.text('curation-summary'), /2 follow-up source/i);
});

test('stale data is marked beside stable ingestion and the new read clock', () => {
  const r = renderer('America/Sao_Paulo');
  vm.runInContext('renderFreshness({stale:true, ingested_at:"2026-10-12T12:00:00Z"}, "2026-10-12T12:00:04Z")', r.context);
  assert.match(r.text('source-status'), /stale/i);
  assert.match(r.text('last-ingested'), /09:00:00/);
  assert.match(r.text('last-updated'), /09:00:04/);
});

test('receipt contribution points to retained evidence without attributing USD benefit', () => {
  const r = renderer();
  vm.runInContext('renderActivity([{task_id:"case",status:"accepted",matched_start:true,retention:{state:"case-retained",inputs_recoverable:true,candidate_recoverable:true,replay_ready:false}}])', r.context);
  assert.match(r.text('activity-list'), /closed a recorded start/i);
  assert.match(r.text('activity-list'), /candidate preserved/i);
  assert.match(r.text('activity-list'), /causal gain not attributed/);
  assert.doesNotMatch(r.text('activity-list'), /replay qualified|saved/);
});

test('navigation refresh preserves the focused project button', () => {
  const r = renderer();
  vm.runInContext('document.activeElement = {id:"project-nav-case"}; state.snapshot = {projects:[{project_id:"case",name:"Fixture",available:true,objective:{status:"collecting"}}],aggregate:{projects_available:1}}; renderNavigation()', r.context);
  assert.equal(vm.runInContext('document.activeElement.id', r.context), 'project-nav-case');
  assert.equal(vm.runInContext('document.activeElement.children?.length', r.context), 3);
  assert.equal(vm.runInContext('document.activeElement.focusOptions?.preventScroll', r.context), true);
});

test('absolute dates include timezone offset and relative age in UTC and local time', () => {
  for (const zone of ['UTC', 'America/Sao_Paulo']) {
    const r = renderer(zone);
    const text = vm.runInContext('localDateTime("2026-10-13T01:30:00Z", "2026-10-13T01:32:00Z")', r.context);
    assert.match(text, /GMT/);
    assert.match(text, /2 minutes ago/);
    assert.match(text, zone === 'UTC' ? /Oct 13, 2026.*01:30:00/ : /Oct 12, 2026.*22:30:00/);
    assert.equal(vm.runInContext('localDateTime("invalid")', r.context), 'N/A');
  }
});

test('event chart uses absolute counts and identifies excluded source events', () => {
  const r = renderer();
  vm.runInContext('renderTemporalCharts({events_30d:{scope:"declared-events-utc-30d",complete:false,excluded:2,rows:[{at:"2026-10-12T00:00:00Z",started:1,terminal:0},{at:"2026-10-13T00:00:00Z",started:2,terminal:1}]}}, null)', r.context);
  assert.match(r.text('events-chart'), /2 declared start|declared starts.*2/i);
  assert.match(r.text('events-chart-note'), /UTC|30/);
  assert.match(r.text('events-chart-note'), /2.*exclu/i);
  assert.doesNotMatch(r.text('events-chart-note'), /saved|trained/);
});

test('one retained observation is a point, not an invented trend or zero for a gap', () => {
  const r = renderer();
  vm.runInContext('renderTemporalCharts({dataset_history:[{at:"2026-10-13T00:00:00Z",counts:{observational:1,"inputs-retained":1,"case-retained":0,"replay-ready":0,"qualified-comparison":0}}]}, {name:"Fixture"})', r.context);
  assert.match(r.text('dataset-history-note'), /1.*observa/i);
  assert.match(r.text('dataset-history-note'), /session|server/);
  const flatten = root => [root, ...root.children.flatMap(flatten)];
  assert.equal(flatten(r.root('dataset-history-chart')).filter(node => node.attributes.d).length, 0);
  vm.runInContext('renderTemporalCharts({dataset_history:[{at:"2026-10-13T00:00:00Z",counts:null}]}, {name:"Fixture"})', r.context);
  assert.match(r.text('dataset-history-chart'), /unavailable|N\/A|unknown/i);
  assert.match(r.text('dataset-history-note'), /inconclusive|gap|partial/i);
});

test('retention evolution is selected-project scope and stale data stays explicit', () => {
  const r = renderer();
  vm.runInContext('renderTemporalCharts({}, null)', r.context);
  assert.match(r.text('dataset-history-chart'), /select.*project/i);
  vm.runInContext('renderTemporalCharts({stale:true,dataset_history:[]}, {name:"Fixture"})', r.context);
  assert.match(r.text('dataset-history-note'), /stale/i);
});

test('OLD NEW plot identifies the historical experiment and does not fill missing USD', () => {
  const r = renderer();
  const evidence = JSON.parse(fs.readFileSync(path.join(__dirname, '../evidence/v1.4.0/causal-roi-result.json')));
  r.context.frozenEvidence = evidence;
  vm.runInContext('renderComparisonChart(frozenEvidence)', r.context);
  assert.match(r.text('comparison-chart-note'), /007-phase-zero-register-projects-paired-v12/);
  assert.match(r.text('comparison-chart-note'), /global history/i);
  assert.match(r.text('comparison-chart-note'), /API-equivalent/);
  assert.match(r.text('comparison-chart'), /OLD|CONTROL/);
  vm.runInContext('frozenEvidence.served_identity.verified_cells = 0; renderComparisonChart(frozenEvidence)', r.context);
  assert.match(r.text('comparison-chart'), /N\/A|unavailable/i);
  vm.runInContext('frozenEvidence.served_identity.verified_cells = 6', r.context);
  vm.runInContext('frozenEvidence.new.cost_usd_total = null; renderComparisonChart(frozenEvidence)', r.context);
  assert.match(r.text('comparison-chart'), /N\/A|unavailable/i);
  assert.doesNotMatch(r.text('comparison-chart'), /\$0\.00/);
});

function pollingSnapshot(tasks = 2, generated_at = '2026-10-13T12:00:00Z') {
  const objective = {status:'on-target',headline:'OPERATIONAL TARGETS MET',primary_action:'Fixture',
    gates:[{key:'mature',label:'Maturity',actual:5,target:'5',denominator:5,status:'pass'}]};
  return {schema:'007-framework/dashboard-snapshot/v1',generated_at,framework_version:'fixture',
    aggregate:{tasks,accepted:tasks,started_tasks:tasks,projects_available:1,objective},
    projects:[{project_id:'case',name:'Fixture',available:true,metrics:{tasks,accepted:tasks,started_tasks:tasks},
      objective,touch:{},recent_tasks:[],activity:{}}]};
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('HTTP-successful source loss disables qualified economics and gates until recovery', async () => {
  let response = pollingSnapshot();
  response.projects[0].metrics.economics = {cohort_complete:true, cost_scope_complete:true,
    cost_usd_per_reliable_with_overhead_declared:5, reasons:[]};
  const good = response;
  const r = renderer(undefined, async () => ({ok:true,json:async () => response}));
  await tick();
  vm.runInContext('state.selectedProject="case"; render()', r.context);
  assert.match(r.text('metric-reliable-cost'), /\$5\.00/);
  for (const flags of [{available:false,stale:true}, {available:false}, {stale:true}]) {
    response = {...good, generated_at:'2026-10-13T12:00:01Z',
      projects:[{...good.projects[0], ...flags}]};
    await vm.runInContext('loadSnapshot()', r.context);
    assert.equal(vm.runInContext('state.transportError', r.context), false);
    assert.equal(r.text('metric-roi'), 'N/A');
    assert.equal(r.text('metric-reliable-cost'), 'N/A');
    assert.doesNotMatch(r.text('gate-matrix-body'), /PASS/);
    assert.equal(vm.runInContext('state.snapshot.projects[0].metrics.economics.cost_scope_complete', r.context), true);
  }
  response = {...good, generated_at:'2026-10-13T12:00:02Z'};
  await vm.runInContext('loadSnapshot()', r.context);
  assert.match(r.text('metric-reliable-cost'), /\$5\.00/);
});

test('pending polling never overlaps manual or interval refresh', async () => {
  let calls = 0, resolve;
  const r = renderer(undefined, () => { calls++; return new Promise(done => { resolve = done; }); });
  await vm.runInContext('loadSnapshot(); loadSnapshot()', r.context);
  assert.equal(calls, 1);
  resolve({ok:true,json:async () => pollingSnapshot()});
  await tick();
  assert.equal(vm.runInContext('state.loading', r.context), false);
  assert.equal(r.text('value-accepted'), '2');
});

test('failed transport preserves data and disables current approval across filter changes', async () => {
  let fail = false;
  const good = pollingSnapshot();
  const r = renderer(undefined, async () => { if (fail) throw Error('offline'); return {ok:true,json:async () => good}; });
  await tick();
  const before = vm.runInContext('JSON.stringify(state.snapshot)', r.context);
  fail = true;
  await vm.runInContext('loadSnapshot()', r.context);
  assert.equal(vm.runInContext('JSON.stringify(state.snapshot)', r.context), before);
  assert.equal(r.text('value-accepted'), '2');
  assert.match(r.text('source-status'), /stale/i);
  assert.match(r.text('verdict-label'), /stale/i);
  assert.match(r.text('dataset-boundary'), /no current check/i);
  assert.doesNotMatch(r.text('gate-matrix-body'), /PASS/);
  vm.runInContext('state.selectedProject="case"; render()', r.context);
  vm.runInContext('document.getElementById("project-nav-case").focus()', r.context);
  assert.match(r.text('source-status'), /stale/i);
  assert.doesNotMatch(r.text('gate-matrix-body'), /PASS/);
});

test('regressing or malformed response cannot replace the last good snapshot', async () => {
  let response = pollingSnapshot();
  const r = renderer(undefined, async () => ({ok:true,json:async () => response}));
  await tick();
  const before = vm.runInContext('JSON.stringify(state.snapshot)', r.context);
  for (const invalid of [pollingSnapshot(1, '2026-10-12T12:00:00Z'), {schema:'wrong'}, pollingSnapshot(3, 'invalid')]) {
    response = invalid;
    await vm.runInContext('loadSnapshot()', r.context);
    assert.equal(vm.runInContext('JSON.stringify(state.snapshot)', r.context), before);
    assert.equal(r.text('value-accepted'), '2');
    assert.match(r.text('source-status'), /stale/i);
  }
});

test('request timeout aborts and releases polling without inventing a snapshot', async () => {
  let signal;
  const r = renderer(undefined, (_, options) => new Promise((resolve,reject) => {
    signal = options?.signal;
    signal?.addEventListener('abort', () => reject(Error('timeout')));
  }));
  assert.equal(r.timeouts.size, 1);
  r.advance(9999);
  assert.equal(signal.aborted, false);
  r.advance(1);
  await tick();
  assert.equal(signal.aborted, true);
  assert.equal(vm.runInContext('state.loading', r.context), false);
  assert.equal(vm.runInContext('state.snapshot', r.context), null);
  assert.equal(r.root('dashboard-content').hidden, true);
  assert.equal(r.timeouts.size, 0);
});

test('successful recovery clears transport stale state without incrementing data', async () => {
  let fail = false;
  const good = pollingSnapshot();
  const r = renderer(undefined, async () => { if (fail) throw Error('offline'); return {ok:true,json:async () => good}; });
  await tick();
  fail = true;
  await vm.runInContext('loadSnapshot()', r.context);
  fail = false;
  await vm.runInContext('loadSnapshot()', r.context);
  assert.equal(r.text('value-accepted'), '2');
  assert.doesNotMatch(r.text('source-status'), /stale/i);
  assert.equal(r.root('error-banner').hidden, true);
  assert.equal(r.timeouts.size, 0);
});

test('malformed render preserves the selected project and last valid payload', async () => {
  let response = pollingSnapshot();
  const r = renderer(undefined, async () => ({ok:true,json:async () => response}));
  await tick();
  vm.runInContext('state.selectedProject="case"; render(); document.getElementById("project-nav").children[0].focus()', r.context);
  const before = vm.runInContext('JSON.stringify(state.snapshot)', r.context);
  response = {...pollingSnapshot(3,'2026-10-13T12:00:01Z'),projects:[{project_id:'other',available:true,objective:null}]};
  await vm.runInContext('loadSnapshot()', r.context);
  assert.equal(vm.runInContext('state.selectedProject', r.context), 'case');
  assert.equal(vm.runInContext('document.activeElement.id', r.context), 'project-nav-case');
  assert.equal(vm.runInContext('JSON.stringify(state.snapshot)', r.context), before);
  assert.match(r.text('source-status'), /stale/i);
});

test('body acquisition timeout is bounded and preserves the last valid values', async () => {
  let hang = false;
  const r = renderer(undefined, async (_, options) => ({ok:true,json:() => hang
    ? new Promise((resolve,reject) => options.signal.addEventListener('abort', () => reject(Error('body timeout'))))
    : Promise.resolve(pollingSnapshot())}));
  await tick();
  hang = true;
  const request = vm.runInContext('loadSnapshot()', r.context);
  await tick();
  r.advance(10000);
  await request;
  assert.equal(r.text('value-accepted'), '2');
  assert.match(r.text('source-status'), /stale/i);
  assert.equal(vm.runInContext('state.loading', r.context), false);
});

const blindedTrial = '{enabled:true,trial_id:"t",verdict:"blinded",margin:-0.05,min_compliance:0.7,compliance:0.8,' +
  'enrollment:{open:true,per_arm:{medium:3,xhigh:2},target:100,deadline:"2026-12-20",closed_at:null},sessions:{medium:4,xhigh:2},' +
  'gates:{compliance:true,sample:false,manipulation:true},readout:{"7":false,"30":false},' +
  'blinded_until:{"7":"2026-12-28T00:00:00Z","30":"2027-01-20T00:00:00Z"},primary:"blinded",kaplan_meier:"blinded",' +
  'secondary:{survival_7d:"blinded",survival_14d:"blinded",corrective_share:"blinded"}}';

test('effort trial shows only enrollment, compliance and gates while its outcomes are blinded', () => {
  const r = renderer();
  vm.runInContext(`renderTrial(${blindedTrial})`, r.context);
  const text = r.text('observatory-trial');
  assert.match(text, /outcomes blinded until 2027-01-20/);
  assert.match(text, /Enrollment open.*medium 3, xhigh 2.*target 100 per arm.*2026-12-20/);
  assert.match(text, /compliance 80%.*gates: compliance ok · sample not yet · manipulation ok/);
  assert.doesNotMatch(text, /survival:|CI 90|NaN|undefined/);
});

test('after the readout the effort trial shows 30-day line survival with its intervals', () => {
  const r = renderer();
  vm.runInContext(`const t = ${blindedTrial}; renderTrial({...t, verdict:"NON-INFERIOR", enrollment:{...t.enrollment, open:false},
    readout:{"7":true,"30":true}, primary:{survival_30d:{medium:0.9,xhigh:0.91}, difference_medium_minus_xhigh:-0.01,
    intervals:{"90":[-0.03,0.01],"95":[-0.04,0.02],"99":[-0.06,0.03]}},
    secondary:{survival_7d:{by_arm:{medium:0.98,xhigh:0.97}}, survival_14d:{by_arm:{medium:0.95,xhigh:0.95}},
    corrective_share:{medium:{share:0.25},xhigh:{share:0.2}}}})`, r.context);
  const text = r.text('observatory-trial');
  assert.match(text, /verdict: NON-INFERIOR/);
  assert.match(text, /30-day line survival: medium 90%, xhigh 91%.*−4 to \+2 pp.*margin −5 pp/);
  assert.match(text, /7 days: medium 98%, xhigh 97%.*corrective share of later commits: medium 25%, xhigh 20%/);
  assert.doesNotMatch(text, /blinded until/);
});

const verdictSnapshot = () => ({ generated_at: '2026-11-01T12:00:00Z', lab_report: null, projects: [{ name: 'repo', project_id: 'p',
  activity: { recent_sessions: [
    { status: 'active', source: 'codex', model: 'm', effort: 'high', started_at: '2026-11-01T11:30:00Z', usage: { total_tokens: 900 } },
    { status: 'active', source: 'claude', model: 'other', effort: 'xhigh', started_at: 'bad', usage: {} },
    { status: 'idle', source: 'codex', model: 'm', effort: 'high' }] },
  observatory: { calibrations: [{ cli: 'codex', model: 'm', arms: { medium: { accepted: 6, units: 6, wall_per_accepted_s: 100 }, high: { accepted: 6, units: 6, wall_per_accepted_s: 200 } }, by_effort: {
    medium: { verdict: 'good-choice', badge: 'Calibrated', gain: { effort: 'medium', against: 'high', time_reduction: .5, cost_reduction: .3 } },
    high: { verdict: 'above-necessary', badge: 'Calibrated', gain: { effort: 'medium', against: 'high' } } } }],
  sessions: [
    { started_at: '2026-10-30T00:00:00Z', total_tokens: 90, durability: { 30: { status: 'pending' } }, questions: [{}, {}, { verdict: 'above-necessary' }] },
    { started_at: '2026-10-30T00:00:00Z', total_tokens: 10, durability: { 30: { status: 'mature', lines_added: 10, lines_surviving: 8 } }, questions: [{}, {}, { verdict: 'good-choice' }] },
    { started_at: '2026-10-30T00:00:00Z', total_tokens: 500, questions: [{}, {}, { verdict: 'no-evidence' }] },
    { started_at: '2026-01-01T00:00:00Z', total_tokens: 500, questions: [{}, {}, { verdict: 'above-necessary' }] }] } }] });

test('live sessions carry the verdict for their own model and effort, and only active ones count', () => {
  const r = renderer();
  r.context.snapshotFixture = verdictSnapshot();
  const rows = vm.runInContext('liveSessions(snapshotFixture.projects, Date.parse(snapshotFixture.generated_at))', r.context);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].says, 'A lower effort matched: medium');  // an equal count never says "enough"
  assert.equal(rows[0].minutes, 30);
  assert.equal(rows[1].says, 'No evidence to change it');
  assert.equal(rows[1].minutes, null);
});

test('scores weigh quota by tokens, ignore uncalibrated sessions and stay inside 30 days', () => {
  const r = renderer();
  r.context.snapshotFixture = verdictSnapshot();
  const s = vm.runInContext('effortScores(snapshotFixture.projects, Date.parse(snapshotFixture.generated_at))', r.context);
  assert.equal(s.quota, .1);
  assert.deepEqual([s.enough, s.judged, s.sessions, s.lines, s.calibrated], [1, 2, 3, .8, 1]);
});

test('durable is never claimed without a proving lab report', () => {
  const r = renderer();
  r.context.snapshotFixture = verdictSnapshot();
  const claim = (report) => { r.context.report = report; return vm.runInContext('thesisClaims(bestVerdict(calibrationsOf(snapshotFixture.projects)), report).at(-1).state[0]', r.context); };
  assert.equal(claim(null), 'NOT PROVEN');
  assert.equal(claim({ durability: 'NO-INFORMATION' }), 'NOT PROVEN');
  assert.equal(claim({ durability: 'KILL' }), 'FAILED');
  assert.equal(claim({ durability: 'PROVEN' }), 'PROVEN');
});

test('the same change is only called proven by a lab report that says so', () => {
  const r = renderer();
  r.context.snapshotFixture = verdictSnapshot();
  const claim = (report) => { r.context.report = report; return vm.runInContext('thesisClaims(bestVerdict(calibrationsOf(snapshotFixture.projects)), report).find((c) => c.id === "claim-change").state[0]', r.context); };
  assert.equal(claim(null), 'NOT PROVEN');
  assert.equal(claim({ same_change_reachable: 'NOT-PROVEN' }), 'NOT PROVEN');
  assert.equal(claim({ same_change_reachable: 'PROVEN' }), 'PROVEN');
  assert.equal(claim({ same_change_reachable: 'KILL' }), 'FAILED');
  assert.equal(claim({ same_change: 'KILL', same_change_reachable: 'NOT-PROVEN' }), 'NOT PROVEN');  // the superseded rule never decides
});

test('quota is never called supported from a price estimate', () => {
  const r = renderer();
  r.context.snapshotFixture = verdictSnapshot();
  const quota = vm.runInContext('thesisClaims(bestVerdict(calibrationsOf(snapshotFixture.projects)), null).find((c) => c.id === "claim-quota").state[0]', r.context);
  assert.equal(quota, 'ESTIMATED');
  const reasoning = vm.runInContext('thesisClaims(bestVerdict(calibrationsOf(snapshotFixture.projects)), null).find((c) => c.id === "claim-reasoning").state[0]', r.context);
  assert.equal(reasoning, 'CHECK');  // the manipulation check is not a benefit
});
