// Run from the project root with node tools/test_burn_graph.js.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let now = 100000;
const plots = [], commits = [];
function flushCommits() { while (commits.length) commits.shift()(); }
class Plot {
  constructor(options, data) {
    this.options = options; this.data = data; this.scales = { x: {} };
    this.over = { addEventListener() {} }; this.pending = {}; plots.push(this);
  }
  setScale(key, range) {
    this.pending[key] = range;
    commits.push(() => this.commit());
  }
  commit() {
    const pending = this.pending; this.pending = {};
    for (const [key, range] of Object.entries(pending)) {
      this.scales[key] = range;
      this.options.hooks.setScale.forEach(fn => fn(this, key));
    }
    if (!this.ready) {
      this.ready = true;
      this.options.hooks.ready?.forEach(fn => fn(this));
    }
  }
  batch(fn) { fn(this); this.commit(); }
  setData(data) { this.data = data; }
  redraw() {}
  destroy() {}
}
const context = {
  Date: class extends Date { static now() { return now * 1000; } },
  ResizeObserver: class { observe() {} disconnect() {} },
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  ZONE_ORDER: [], uPlot: Plot,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('main/web_ui/burn-graph.js', 'utf8'), context);
const range = samples => JSON.parse(JSON.stringify(context.burnHistoryRange(samples, 125, now)));
assert.deepEqual(range([[now-86400, 20], [now, 20]]), { min: now-10800, max: now });
assert.deepEqual(range([[now-15000, 130], [now-14000, 20], [now, 20]]), { min: now-10800, max: now });
// Completed recent burns keep their start padding and cooling tail through now.
assert.deepEqual(range([[now-20000, 20], [now-9000, 130], [now-6000, 20], [now, 20]]),
  { min: now-9900, max: now });
// Long cold intervals split burns; brief dips and compressed hot plateaus do not.
assert.deepEqual(range([[now-20000, 20], [now-16000, 130], [now-15000, 20],
  [now-8000, 140], [now-6000, 20], [now, 20]]), { min: now-8900, max: now });
assert.deepEqual(range([[now-20000, 20], [now-8000, 130], [now-7000, 20],
  [now-6000, 130], [now, 140]]), { min: now-8900, max: now });
assert.deepEqual(range([[now-20000, 20], [now-18000, 130], [now, 130]]),
  { min: now-18900, max: now });
assert.deepEqual(range([[now-20000, 20], [now-8000, 130], [now-500, 20], [now, 20]]),
  { min: now-8900, max: now });
// Threshold is configurable; short records still have a readable time axis.
assert.deepEqual(JSON.parse(JSON.stringify(context.burnHistoryRange([[now-20000,20], [now-1000,80], [now,80]],80,now))),
  { min: now-1900, max: now });
assert.deepEqual(range([[now, 130]]), { min: now-600, max: now });
assert.deepEqual(range([[now-30000,20], [now-25000,130], [now-24000,20]]),
  { min: now-10800, max: now });
assert.deepEqual(range([[now-30000,20], [now-25000,130]]),
  { min: now-10800, max: now });
function graph() {
  const g = context.burnGraph();
  g.$refs = { plot: { clientWidth: 600, isConnected: true }, tooltip: {} };
  g.$nextTick = fn => fn(); g.init(); return g;
}
const history = { samples: [[20000,20], [8000,130], [0,140]] };
const g = graph();
assert.equal(g.chartReady, false, 'keep the loading state before drawing');
g.update(history, {thermocouple_ok:false}, {zone_cold_max_c:125}, true, [], now*1000);
flushCommits();
assert.equal(g.chartReady, true, 'dismiss the loading state after the first draw');
const p = plots.at(-1);
assert.equal(p.scales.x.min, now-8900);
p.setScale('x', {min:now-2000,max:now-1000});
flushCommits();
g.update(history, {thermocouple_ok:false}, {zone_cold_max_c:125}, true, [], now*1000);
flushCommits();
assert.equal(p.scales.x.min, now-2000);
g.resetRange(); flushCommits(); assert.equal(p.scales.x.min, now-8900); g.destroy();
const reopened = graph();
reopened.update(history, {thermocouple_ok:false}, {zone_cold_max_c:125}, true, [], now*1000);
flushCommits();
assert.equal(plots.at(-1).scales.x.min, now-8900);
reopened.update({samples:[[20000,20],[0,20]]}, {thermocouple_ok:false}, {}, true, [], now*1000);
flushCommits();
assert.equal(plots.at(-1).scales.x.min, now-10800);
// uPlot commits scale hooks after setScale returns. Automatic commits must not
// turn off following; user zoom remains fixed until the explicit reset.
const following = graph();
following.update(history, {thermocouple_ok:true,thermocouple_c:140}, {zone_cold_max_c:125}, true, [], now*1000);
flushCommits();
const live = plots.at(-1), initial = now;
now += 60;
following.update(history, {thermocouple_ok:true,thermocouple_c:145}, {zone_cold_max_c:125}, true, [], initial*1000);
flushCommits();
assert.equal(live.scales.x.max, now, 'automatic updates must follow an active burn');
following.applyBounds(initial-2000, initial-1000); flushCommits();
now += 60;
following.update(history, {thermocouple_ok:true,thermocouple_c:150}, {zone_cold_max_c:125}, true, [], initial*1000);
flushCommits();
assert.equal(live.scales.x.max, initial-1000, 'manual zoom must remain fixed');
following.resetRange(); flushCommits();
now += 60;
following.update(history, {thermocouple_ok:true,thermocouple_c:155}, {zone_cold_max_c:125}, true, [], initial*1000);
flushCommits();
assert.equal(live.scales.x.max, now, 'reset must resume following after the deferred hook');
// Session-end detection must not freeze the right edge in the past.
const cooling = graph(), coolingReceived = now;
const coolingHistory = {samples:[[20000,20],[9000,180],[6000,56],[0,56]]};
cooling.update(coolingHistory, {thermocouple_ok:true,thermocouple_c:56}, {zone_cold_max_c:125}, true, [], coolingReceived*1000);
flushCommits();
const cooled = plots.at(-1);
assert.equal(cooled.scales.x.min, coolingReceived-9900);
assert.equal(cooled.scales.x.max, now, 'a completed recent session must extend to now');
now += 60;
cooling.update(coolingHistory, {thermocouple_ok:true,thermocouple_c:55}, {zone_cold_max_c:125}, true, [], coolingReceived*1000);
flushCommits();
assert.equal(cooled.scales.x.max, now, 'cooling tail must keep following current time');
console.log('PASS burn detection, cold-gap merging, recent cutoff, threshold, padding, stale history, deferred uPlot commits, live following, manual zoom, reset and no restored zoom');
