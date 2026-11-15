// Test the real dashboard's grouped event selection and existing log endpoint.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const read = name => fs.readFileSync(path.join(__dirname,'..',name),'utf8');
const focus = [];
const context = { console, Date, AbortSignal, setTimeout, clearTimeout,
  document: { getElementById: id => ({ focus: () => focus.push(id) }) } };
vm.createContext(context);
vm.runInContext(read('main/web_ui/dashboard.js'), context);
const api = read('main/rest_api.c');
const menu = api.split('static const woodstove_event_t EVENTS[] = {')[1].split('};')[0];
const events = [...menu.matchAll(/\{"([^"]+)", "([^"]+)"\}/g)].map(m => ({slug:m[1],label:m[2]}));
// These IDs are part of the saved snapshot format, not the visual menu order.
assert.deepEqual(events.map(e => e.slug), ['cold_start','opened_stove','added_wood','damper_up','damper_down',
  'burning_optimally','roaring','dying_down','fire_out','stove_off','coaling']);
const a = context.app(); a.events = events; a.$nextTick = fn => fn();
const slugs = group => Array.from(a.eventOptions(group), e => e.slug);
assert.deepEqual(slugs('actions'), ['cold_start','added_wood','opened_stove','damper_up','damper_down']);
assert.deepEqual(slugs('status'), ['burning_optimally','roaring','coaling','dying_down','fire_out','stove_off']);
const coaling = a.eventOptions('status').find(e => e.slug === 'coaling');
assert.equal(coaling.title, 'Coaling'); assert.equal(coaling.detail, 'Glowing embers, little flame');
assert.equal(a.eventOptions('status')[0].title, 'Burning steadily');
assert.equal(events[5].label, 'Burning Optimally'); // presentation never changes the API vocabulary
// A dashboard served against an older device must not offer unsupported events.
a.events = events.slice(0,10); assert(!slugs('status').includes('coaling')); a.events = events;
a.openSheet(); assert(a.sheetOpen && a.logTab === 'actions');
a.setLogTab('status'); assert.equal(focus.at(-1),'moment-tab-status');
a.closeSheet(); assert(!a.sheetOpen); assert.equal(focus.at(-1),'event-log-open');
(async () => {
  const reading = JSON.stringify(a.reading), settings = JSON.stringify(a.settings);
  let calls = 0;
  context.fetch = async (url,options) => {
    calls++; assert.equal(url,'/api/event'); assert.equal(options.method,'POST');
    assert.deepEqual(JSON.parse(options.body),{event:'coaling'});
    return { ok:true, json:async()=>({success:true,sheets_queued:false}) };
  };
  a.showToast = message => { a.toast = message; }; a.sheetOpen = true; a.historyReceivedMs = 123;
  await a.logEvent(coaling);
  assert.equal(calls,1); assert(!a.sheetOpen); assert.equal(a.historyReceivedMs,0);
  assert.equal(a.toast,'Logged: Coaling (not sent to Sheets)');
  assert.equal(JSON.stringify(a.reading),reading); assert.equal(JSON.stringify(a.settings),settings);
  context.fetch = async () => { throw new Error('offline'); };
  await a.logEvent(coaling); assert.match(a.toast,/Couldn't log Coaling/);
  const html=read('main/web_ui/dashboard.html');
  assert(html.includes('eventOptions(logTab)') && !html.includes('x-html="ev.icon"'));
  console.log('PASS stable event IDs, grouped choices, Coaling, old-device filtering, tab focus, log POST, local-only status, Sheets queue feedback and network failure');
})().catch(e=>{console.error(e);process.exitCode=1;});
