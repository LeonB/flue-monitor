const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { console, AbortSignal, Date, URL, setTimeout, clearTimeout };
vm.createContext(context);
vm.runInContext(fs.readFileSync('main/web_ui/dashboard.js', 'utf8'), context);
(async () => {
  const a = context.app();
  let posted;
  context.fetch = async (url, options) => {
    assert.equal(url, '/api/bosch');
    if (options.method === 'POST') { posted = JSON.parse(options.body); return { ok: true }; }
    return { ok: true, json: async () => ({ state: 'connected', linked: true, available: true, temperature_c: 19.6, busy: false }) };
  };
  await a.fetchBosch();assert.equal(a.boschTemperature,'19.6 °C');
  a.bosch.zones=['zn10','zn2','zn2','bogus'];a.bosch.zone='zn1';a.boschZone='zn3';
  assert.equal(a.boschZoneOptions.map(o=>o.id).join(','),'zn1,zn2,zn3,zn10');
  a.bosch.zones=null;assert.ok(a.boschZoneOptions.some(o=>o.id==='zn3'));
  a.boschReceivedMs -= 21000;assert.equal(a.boschTemperature,'Unavailable');
  a.boschCallback='random value';posted=null;
  await a.boschAction('callback');assert.equal(posted,null);assert.match(a.boschMessage,/Invalid Bosch return link/);
  await a.fetchBosch();assert.match(a.boschMessage,/Invalid Bosch return link/);
  assert.equal(a.boschCallback,'random value');
  a.boschCallback = '  com.bosch.tt.dashtt.pointt://app/login?code=test&state=test  ';
  await a.boschAction('callback');assert.equal(a.boschCallback,'');assert.equal(posted.action,'callback');assert.ok(!posted.callback.startsWith(' '));
  a.boschCallback = 'com.bosch.tt.dashtt.pointt://app/login?code=old&state=old';
  context.fetch = async (url, options) => options.method === 'POST' ? {ok:true} :
    {ok:true,json:async()=>({state:'login_error',busy:false,error:'Link expired or belongs to an earlier sign-in.'})};
  await a.boschAction('callback');assert.match(a.boschMessage,/Link expired/);
  assert.ok(a.boschMessageError);assert.ok(a.boschCallback.includes('code=old'));
  await a.fetchBosch();assert.match(a.boschMessage,/Link expired/);
  context.fetch = async (url, options) => {
    if (options.method === 'POST') {posted=JSON.parse(options.body);return {ok:true};}
    return {ok:true,json:async()=>({state:'connected',linked:true,available:true,temperature_c:19.6,busy:false})};
  };
  await a.boschAction('callback');assert.match(a.boschMessage,/Bosch connected/);assert.equal(a.boschCallback,'');
  let pendingState = {state:'connecting',linked:true,available:false,busy:false};
  context.fetch = async (url, options) => options.method === 'POST' ? {ok:true} : {ok:true,json:async()=>pendingState};
  a.boschCallback='com.bosch.tt.dashtt.pointt://app/login?code=new&state=new';
  await a.boschAction('callback');assert.match(a.boschMessage,/Checking/);assert.equal(a.boschPendingAction,'callback');
  pendingState={state:'connected',linked:true,available:true,temperature_c:19.6,busy:false};
  await a.fetchBosch();assert.match(a.boschMessage,/Bosch connected/);assert.equal(a.boschCallback,'');
  context.fetch = async (url, options) => {
    if (options.method === 'POST') {posted=JSON.parse(options.body);return {ok:true};}
    return {ok:true,json:async()=>pendingState};
  };
  a.bosch.busy = true;posted=null;await a.boschAction('disconnect');assert.equal(posted,null);
  a.bosch.busy = false;a.boschDevice='123';a.boschZone='zn2';await a.boschAction('select');assert.equal(posted.zone,'zn2');
  context.fetch = async (url, options) => options.method === 'POST'
    ? {ok:false,text:async()=> 'Invalid device selection'}
    : {ok:true,json:async()=>({state:'connected',linked:true,busy:false})};
  await a.boschAction('select');assert.equal(a.boschMessage,'Invalid device selection');
  await a.fetchBosch();assert.equal(a.boschMessage,'Invalid device selection');
  context.fetch = async () => {throw new Error('offline');};
  await a.fetchBosch();assert.equal(a.boschTemperature,'Unavailable');assert.equal(a.bosch.auth_url,null);
  a.boschCallback='keep on failure';await a.boschAction('callback');assert.equal(a.boschCallback,'keep on failure');assert.equal(a.boschBusy,false);
  let destination;
  context.location={assign:value=>destination=value};
  context.fetch=async()=>({ok:true});
  await a.logout();assert.equal(destination,'/');
  destination=null;context.fetch=async()=>({ok:false});
  await a.logout();assert.equal(destination,null);assert.match(a.authMessage,/Could not sign out/);
  console.log('PASS Bosch UI: stale/offline readings, callback cleanup, busy guard, zone selection and retry feedback');
})().catch(e=>{console.error(e);process.exitCode=1});
