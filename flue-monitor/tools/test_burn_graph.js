// Run from the project root with node tools/test_burn_graph.js.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const now = 100000, plots = [];
class Plot {
  constructor(options, data) {
    this.options = options; this.data = data; this.scales = { x: {} };
    this.over = { addEventListener() {} }; plots.push(this);
  }
  setScale(key, range) {
    this.scales[key] = range;
    this.options.hooks.setScale.forEach(fn => fn(this, key));
  }
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
// Completed burns include padding without the long idle tail.
assert.deepEqual(range([[now-20000, 20], [now-9000, 130], [now-6000, 20], [now, 20]]),
  { min: now-9900, max: now-5100 });
// Long cold intervals split burns; brief dips and compressed hot plateaus do not.
assert.deepEqual(range([[now-20000, 20], [now-16000, 130], [now-15000, 20],
  [now-8000, 140], [now-6000, 20], [now, 20]]), { min: now-8900, max: now-5100 });
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
g.update(history, {thermocouple_ok:false}, {zone_cold_max_c:125}, true, [], now*1000);
const p = plots.at(-1);
assert.equal(p.scales.x.min, now-8900);
p.setScale('x', {min:now-2000,max:now-1000});
g.update(history, {thermocouple_ok:false}, {zone_cold_max_c:125}, true, [], now*1000);
assert.equal(p.scales.x.min, now-2000);
g.resetRange(); assert.equal(p.scales.x.min, now-8900); g.destroy();
const reopened = graph();
reopened.update(history, {thermocouple_ok:false}, {zone_cold_max_c:125}, true, [], now*1000);
assert.equal(plots.at(-1).scales.x.min, now-8900);
reopened.update({samples:[[20000,20],[0,20]]}, {thermocouple_ok:false}, {}, true, [], now*1000);
assert.equal(plots.at(-1).scales.x.min, now-10800);
console.log('PASS burn detection, cold-gap merging, recent cutoff, threshold, padding, stale history, automatic updates and no restored zoom');
