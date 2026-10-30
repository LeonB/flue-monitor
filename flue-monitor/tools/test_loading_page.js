const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('main/web_ui/loading.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
async function run(url, fails=false) {
  const fields={};let writes=[],navigations=[];
  const context={URL,AbortController,setTimeout,clearTimeout,
    location:{href:'https://monitor.example/',replace:url=>navigations.push(url)},
    navigator:{onLine:!fails},window:{addEventListener(){}},
    document:{getElementById:id=>fields[id] ||= {addEventListener(){}},open(){},write:html=>writes.push(html),close(){}},
    fetch:async (url,options)=>{
      assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');
      if(fails)throw Error('offline');
      return {ok:true,url:context.responseUrl,headers:{get:()=> 'text/html'},text:async()=>'<main>dashboard</main>'};
    },responseUrl:url};
  vm.createContext(context);vm.runInContext(script,context);await new Promise(resolve=>setImmediate(resolve));
  return {fields,writes,navigations};
}
(async()=>{
  const login=await run('https://monitor.example/login');assert.deepEqual(login.navigations,['/login']);assert.equal(login.writes.length,0);
  const dashboard=await run('https://monitor.example/');assert.equal(dashboard.navigations.length,0);assert.deepEqual(dashboard.writes,['<main>dashboard</main>']);
  const offline=await run('',true);assert.equal(offline.fields.retry.hidden,false);assert.match(offline.fields['startup-message'].textContent,/offline/);
  console.log('PASS actual startup: real navigation for login, dashboard insertion preserved, offline retry');
})().catch(e=>{console.error(e);process.exitCode=1});
