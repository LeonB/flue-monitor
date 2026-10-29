// Exercise actual dashboard calibration commands, including uncertain delivery.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={console,AbortSignal,setTimeout,clearTimeout,Date};vm.createContext(context);
vm.runInContext(fs.readFileSync('main/web_ui/dashboard.js','utf8'),context);
function app(){const a=context.app();a.view='calibration';a.settings={panel_srgb:false,panel_red_gain:1};a.draft={...a.settings};a.showToast=m=>a.toast=m;return a;}
(async()=>{
 const a=app();let submitted,fetches=0;
 a.calibration={color:'#f3b54a',brightness:96,mode:'srgb',gamma:2.25,red:0.85,green:1,blue:1};
 a.authorizedFetch=async(path,options)=>{assert.equal(path,'/api/calibration');submitted=JSON.parse(options.body);return {ok:true,json:async()=>({active:submitted.action==='preview',remaining_ms:submitted.action==='preview'?180000:0,settings_revision:17})}};
 a.waitForDisplaySettings=async(revision,path)=>{assert.equal(revision,17);assert.equal(path,'/api/calibration');return true;};
 a.fetchSettings=async()=>{fetches++;a.settings.panel_srgb=true;};
 await a.calibrationCommand('preview');assert.equal(submitted.srgb,true);assert.equal(submitted.gamma,2.25);assert.equal(submitted.red,0.85);assert(a.calibrationActive);assert.equal(a.view,'calibration');assert.equal(fetches,0);
 await a.calibrationCommand('cancel');assert.equal(a.view,'settings');assert(!a.calibrationActive);assert.equal(fetches,0);assert.equal(a.settings.panel_srgb,false);
 a.view='calibration';await a.calibrationCommand('save');assert.equal(fetches,1);assert.equal(a.view,'settings');assert(a.settings.panel_srgb);
 a.view='calibration';a.waitForDisplaySettings=async()=>false;
 await a.calibrationCommand('save');assert.equal(a.view,'calibration');assert(a.calibrationError);assert.match(a.calibrationMessage,/saved, but display delivery is unconfirmed/);
 await a.calibrationCommand('cancel');assert.match(a.calibrationMessage,/expire automatically/);assert.equal(a.calibrationBusy,false);
 a.authorizedFetch=async()=>{throw new Error('offline')};await a.calibrationCommand('preview');assert(a.calibrationError);assert.equal(a.calibrationBusy,false);assert.match(a.calibrationMessage,/No confirmation/);
 const dirty=app();dirty.draft.panel_red_gain=0.8;dirty.authorizedFetch=()=>{throw new Error('Dirty settings were discarded')};await dirty.openCalibration();assert.match(dirty.toast,/Save or undo/);
 const pending=app();let finish;pending.authorizedFetch=()=>new Promise(r=>finish=r);pending.waitForDisplaySettings=async()=>true;
 const request=pending.calibrationCommand('preview');assert(pending.calibrationBusy);await pending.calibrationCommand('cancel');finish({ok:true,json:async()=>({active:true,remaining_ms:180000,settings_revision:3})});await request;assert.equal(pending.calibrationBusy,false);
 const unavailable=app();unavailable.authorizedFetch=async()=>({ok:true,json:async()=>({supported:false,active:false,remaining_ms:0})});await unavailable.refreshCalibrationStatus();assert(!unavailable.calibrationSupported);assert(unavailable.calibrationError);
 console.log('PASS calibration UI: preview/cancel preserve saved correction, save refreshes, capable-display ACK path, delivery failure, offline, dirty edits and duplicate requests');
})().catch(e=>{console.error(e);process.exitCode=1});
