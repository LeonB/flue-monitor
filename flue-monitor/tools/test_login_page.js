// Exercise the actual inline firmware login-page script without a browser.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('main/rest_api.c', 'utf8').split('static const char login_page[] = ')[1].split('\n\nstatic esp_err_t auth_status_handler')[0];
const html = [...source.matchAll(/"(?:[^"\\]|\\.)*"/g)].map(m => JSON.parse(m[0])).join('');
assert.match(html, /type="password"/);
assert.match(html, /<form id="dashboard-login" name="dashboard-login" method="post" action="\/api\/auth\/login" autocomplete="on">/);
assert.match(html, /id="b" type="submit"/);
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]).find(script => script.includes("const form="));
async function page(configured, remote = false, single = false) {
  const elements = Object.fromEntries(['p','c','intro','label','b','e','show','title','remember'].map(k => [k, { value: '', style: {}, textContent: '', disabled: k === 'b', checked:false, type:'password', setAttribute(name,value){this[name]=value} }]));
  const form = {}; let writes = [], redirects = [];
  const context = { AbortController, setTimeout, clearTimeout, document: { querySelector: selector => selector === 'form' ? form : elements.e, getElementById: id => single && id === 'c' ? null : elements[id], createElement: () => ({style:{},setAttribute(name,value){this[name]=value}}) },
    location: { pathname: '/login', protocol: 'https:', hostname: 'demo.pagekite.me', host: 'demo.pagekite.me', replace: value => redirects.push(value) },
    fetch: async (url, options) => { if (!options.method) return {ok:true,json: async () => ({ configured, setup_local_only: remote })}; writes.push({url, body: JSON.parse(options.body)}); return {ok:true, json: async()=>({success:true})}; }
  };
  vm.createContext(context); vm.runInContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  return { context, elements, form, writes, redirects };
}
(async () => {
  const redirects=[];
  const legacy={location:{pathname:'/',replace:url=>redirects.push(url)}};
  vm.createContext(legacy);vm.runInContext(script,legacy);
  assert.deepEqual(redirects,['/login']); // old cached shell must navigate before touching fields
  const setup = await page(false);
  assert.equal(setup.elements.b.disabled, false);
  assert.equal(setup.form.action,'/api/auth/setup');
  assert.equal(setup.elements.p.autocomplete,'new-password');
  assert.equal(setup.elements.c.autocomplete,'new-password');
  assert.equal(setup.elements.c.disabled,false);
  assert.equal(setup.elements.c['aria-hidden'],'false');
  setup.elements.show.onclick(); assert.equal(setup.elements.p.type,'text');
  setup.elements.show.onclick(); assert.equal(setup.elements.p.type,'password');
  setup.elements.p.value = 'mock-password'; setup.elements.c.value = 'different';
  await setup.form.onsubmit({preventDefault(){}});
  assert.equal(setup.writes.length, 0); assert.match(setup.elements.e.textContent, /do not match/);
  setup.elements.c.value = 'mock-password';
  await setup.form.onsubmit({preventDefault(){}});
  assert.equal(setup.writes[0].url, '/api/auth/setup'); assert.equal(setup.writes[0].body.confirm_password, 'mock-password'); assert.equal(setup.redirects[0], '/');
  const single = await page(true, false, true);
  single.elements.p.value='mock-password';
  await single.form.onsubmit({preventDefault(){}});
  assert.equal(single.writes[0].url,'/api/auth/login');
  assert.equal(single.redirects[0],'/');
  const remote = await page(false, true);
  assert.equal(remote.elements.b.disabled, true); assert.equal(remote.elements.p.disabled, true); assert.match(remote.elements.intro.textContent, /home network/);
  const login = await page(true);
  assert.equal(login.form.action,'/api/auth/login');
  assert.equal(login.elements.p.autocomplete,'current-password');
  assert.equal(login.elements.c.autocomplete,'off');
  assert.equal(login.elements.c.disabled,true);
  assert.equal(login.elements.c['aria-hidden'],'true');
  assert.equal(login.elements.c.style.display, 'none'); login.elements.p.value = 'mock-password';
  await login.form.onsubmit({preventDefault(){}}); assert.equal(login.writes[0].body.remember,false); assert.equal(login.writes[0].url, '/api/auth/login'); assert.equal(login.redirects[0], '/');
  login.elements.remember.checked=true;await login.form.onsubmit({preventDefault(){}});assert.equal(login.writes.at(-1).body.remember,true);
  login.context.fetch = async () => ({ok:false,json:async()=>({error:'Password is incorrect.'})});
  await login.form.onsubmit({preventDefault(){}}); assert.equal(login.elements.e.textContent, 'Password is incorrect.');
  login.context.fetch = async () => { throw new Error('Network disconnected'); };
  await login.form.onsubmit({preventDefault(){}});
  assert.equal(login.elements.e.textContent, 'Network disconnected'); assert.equal(login.elements.b.disabled, false);
  login.context.fetch = async () => ({ok:false,status:403,json:async()=>{throw new Error('not JSON')}});
  await login.form.onsubmit({preventDefault(){}}); assert.match(login.elements.e.textContent, /unexpected response/);
  login.context.fetch = async () => { const err=new Error();err.name='AbortError';throw err; };
  await login.form.onsubmit({preventDefault(){}}); assert.match(login.elements.e.textContent, /20 seconds/);
  let complete;
  login.context.fetch = () => new Promise(resolve=>{complete=resolve});
  const pending=login.form.onsubmit({preventDefault(){}});
  assert.equal(login.elements.b.disabled,true); assert.equal(login.elements.b.textContent,'Signing in…');
  assert.match(login.elements.e.textContent,/Waiting/);
  complete({ok:true,json:async()=>({success:true})}); await pending;
  assert.match(login.elements.e.textContent,/Signed in/);
  console.log('PASS real login page: first-password confirmation, remote enrollment blocked, login, error display and redirect');
})().catch(error=>{console.error(error);process.exitCode=1;});
