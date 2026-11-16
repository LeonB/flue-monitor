const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={console,AbortSignal,setTimeout,clearTimeout,Date};vm.createContext(context);
vm.runInContext(fs.readFileSync('main/web_ui/dashboard.js','utf8'),context);
(async()=>{
 const app=context.app();app.showToast=m=>app.toast=m;
 assert.equal(app.refillTime(1380),'23:00');assert.equal(app.refillTime(420),'07:00');
 app.draft={};app.setRefillTime('refill_quiet_end_min','08:15');assert.equal(app.draft.refill_quiet_end_min,495);
 app.setRefillTime('refill_quiet_end_min','99:00');assert.equal(app.draft.refill_quiet_end_min,495);
 const posts=[];context.fetch=async(url,options)=>{if(options?.method==='POST')posts.push({url,body:JSON.parse(options.body)});return {ok:true,json:async()=>({result:'pending'})};};
 await app.refillAction('test');assert.equal(posts[0].url,'/api/refill/test');assert.deepEqual(posts[0].body,{});assert.match(app.toast,/Test queued/);assert.equal(app.refillBusy,false);
 app.settings={refill_enabled:true};app.refillStatus={quiet:true};assert.match(app.refillStatusText,/Quiet hours/);
 app.refillStatus={result:'failed'};assert.match(app.refillStatusText,/could not be sent/);
 context.fetch=async()=>({ok:false});await app.refillAction('quiet');assert.match(app.toast,/Could not update/);
 // Credential fields are forgotten after save; destination flags remain available.
 app.settings={refill_url_set:false,refill_token_set:false};
 app.draft={refill_enabled:true,refill_url:'https://ntfy.example/private-topic',refill_token:'tk_dummy'};
 app.waitForDisplaySettings=()=>{throw Error('Monitor-only notification save contacted display');};
 context.fetch=async()=>({ok:true,json:async()=>({settings_revision:2,refill_url_set:true,refill_token_set:true})});
 await app.saveSettings();assert.equal(app.draft.refill_url,'');assert.equal(app.draft.refill_token,'');assert.equal(app.settings.refill_url,'');assert.equal(app.settings.refill_url_set,true);assert.equal(app.changeCount,0);
 // A replacement typed during save is not erased by the prior response.
 let finish;app.draft.refill_url='https://ntfy.example/first';context.fetch=()=>new Promise(r=>finish=r);
 const saving=app.saveSettings();app.draft.refill_url='https://ntfy.example/newer';finish({ok:true,json:async()=>({settings_revision:3,refill_url_set:true})});await saving;
 assert.equal(app.draft.refill_url,'https://ntfy.example/newer');assert.equal(app.changeCount,1);
 console.log('PASS notification UI clock fields, quiet/status text, test/actions/error guard, monitor-only save, redaction and pending edits');
})().catch(e=>{console.error(e);process.exitCode=1});
