const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function renderer() {
  const nodes = new Map();
  const node = () => ({textContent: '', children: [], style: {}, classList: {
    add() {}, remove() {}, toggle() {},
  }, addEventListener() {}, append(...items) { this.children.push(...items); },
  replaceChildren() { this.children = []; }});
  const document = { getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, node());
    return nodes.get(id);
  }, createElement: node};
  const context = vm.createContext({ document, window: { setInterval() {} },
    fetch: () => new Promise(() => {}), console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../dashboard/app.js'), 'utf8'), context);
  const text = item => [item.textContent, ...item.children.map(text)].join(' ');
  return { context, text: id => text(document.getElementById(id)) };
}

test('an unmeasured overview does not assert correctness or reduced rework', () => {
  const r = renderer();
  vm.runInContext('renderHeader({}, null)', r.context);
  assert.doesNotMatch(r.text('view-title'), /entrega correta|menos retrabalho/i);
  assert.match(r.text('view-title'), /evidência/i);
  assert.match(r.text('scope-sample'), /0 iniciadas.*0 concluídas.*0 aceitas/);
  assert.match(r.text('verdict-label'), /NOT YET MEASURABLE/);
});

test('a just-completed declaration does not claim verified D7 survival', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({accepted: 1, tasks: 1, reliable_first_pass_yes: 1, reliable_first_pass_known: 1, reliable_first_pass_rate: 1})', r.context);
  assert.match(r.text('metric-reliable-detail'), /declarad/i);
  assert.match(r.text('metric-reliable-detail'), /não verificado/);
  assert.doesNotMatch(r.text('metric-reliable-detail'), /madur|sobrevivência verificada|intact/i);
});

test('missing follow-up is not explained as verified time-window maturation', () => {
  const r = renderer();
  const labels = vm.runInContext('[reasonLabel("fewer than 5 matured accepted tasks"), reasonLabel("7-day escape rate is N/D")]', r.context);
  for (const label of labels) {
    assert.match(label, /declara/i);
    assert.doesNotMatch(label, /madur|amadurec/i);
  }
});

test('provisional accounting and open attempts are visible next to USD', () => {
  const r = renderer();
  vm.runInContext('renderMetrics({tasks: 2, active_tasks: 1, cost_usd_known_sum: 1, cost_usd_known_tasks: 2, cost_coverage: 1, cost_accounting_status: "provisional", cost_sources: {"rate-card-estimate": 2}})', r.context);
  assert.match(r.text('metric-reliable-cost-detail'), /provis/i);
  assert.match(r.text('metric-reliable-cost-detail'), /rate-card-estimate/);
  assert.match(r.text('metric-reliable-cost-detail'), /1 aberta/);
  vm.runInContext('renderMetrics({tasks: 2, cost_usd_known_sum: 1, cost_usd_known_tasks: 2, cost_coverage: 1, cost_accounting_status: "final", cost_sources: {"provider-reported": 2}})', r.context);
  assert.match(r.text('metric-reliable-cost-detail'), /final/);
  assert.match(r.text('metric-reliable-cost-detail'), /provider-reported/);
});

test('route costs retain the adjacent accounting source and state', () => {
  const r = renderer();
  vm.runInContext('renderRoutes({routes: [{provider:"example", model:"estimate", reliable:1, reliable_known:1, cost_usd_per_reliable:0.4, cost_sources:{"rate-card-estimate":1}, cost_accounting_status:"provisional"}, {provider:"example", model:"billed", reliable:1, reliable_known:1, cost_usd_per_reliable:0.6, cost_sources:{"provider-reported":1}, cost_accounting_status:"final"}]})', r.context);
  const rendered = r.text('route-list');
  assert.match(rendered, /provisório.*rate-card-estimate/);
  assert.match(rendered, /final.*provider-reported/);
});

test('causal identity with zero verified cells is not reported verified', () => {
  const r = renderer();
  vm.runInContext('state.snapshot = {causal_evidence: {sample: {tasks: 1, accepted: 6, cells: 6}, served_identity: {verified_cells: 0, total_cells: 6}}}; renderEvidence()', r.context);
  assert.doesNotMatch(r.text('causal-sample'), /identidade servida verificada/);
  assert.match(r.text('causal-sample'), /0\/6/);
  vm.runInContext('state.snapshot.causal_evidence.served_identity = {verified_cells: 6, total_cells: 6}; renderEvidence()', r.context);
  assert.match(r.text('causal-sample'), /identidade servida verificada/);
  assert.match(r.text('causal-scope'), /global|históric/i);
});
