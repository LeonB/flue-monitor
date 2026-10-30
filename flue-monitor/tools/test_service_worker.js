// Exercise the real worker with an in-memory Cache API and an unavailable network.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const worker = fs.readFileSync('main/web_ui/service-worker.js', 'utf8');
const handlers = {}, entries = new Map(), deleted = [], fetched = [];
let claimed = false, skipped = false, offline = false;
const cache = {async put(url, response){entries.set(url,response)},async match(url){return entries.get(url)}};
const context = {
  URL,
  self: {location:{origin:'https://demo.pagekite.me'},addEventListener(name,handler){handlers[name]=handler},async skipWaiting(){skipped=true},clients:{async claim(){claimed=true}}},
  caches: {async open(){return cache},async keys(){return ['flue-startup-old','another-app-cache']},async delete(key){deleted.push(key)}},
  async fetch(url){fetched.push(url);if(offline)throw new Error('offline');return {ok:true,headers:{get:()=> 'text/html'},marker:'public loading screen'}}
};
vm.createContext(context);vm.runInContext(worker,context);
(async()=>{
  let pending;
  handlers.install({waitUntil(p){pending=p}});await pending;
  assert.equal(skipped,true);assert.deepEqual(fetched,['/loading.html']);assert.deepEqual([...entries.keys()],['/loading.html']);
  handlers.activate({waitUntil(p){pending=p}});await pending;
  assert.equal(claimed,true);assert.deepEqual(deleted,['flue-startup-old']);
  offline=true;
  const request={url:'https://demo.pagekite.me/',method:'GET',mode:'navigate'};
  let response;
  handlers.fetch({request,respondWith(p){response=p}});assert.equal((await response).marker,'public loading screen');
  for(const request of [
    {url:'https://demo.pagekite.me/login',method:'GET',mode:'navigate'},
    {url:'https://demo.pagekite.me/api/reading',method:'GET',mode:'same-origin'},
    {url:'https://demo.pagekite.me/api/auth/login',method:'POST',mode:'same-origin'},
    {url:'https://demo.pagekite.me/',method:'GET',mode:'same-origin'}, // live HTML fetch
    {url:'https://other.example/',method:'GET',mode:'navigate'}
  ])handlers.fetch({request,respondWith(){assert.fail('Private/network request intercepted')}});
  assert.deepEqual(fetched,['/loading.html']);
  console.log('PASS cached startup without network; only public shell cached; APIs/auth/live HTML untouched; old shell caches retired');
})().catch(error=>{console.error(error);process.exitCode=1});
