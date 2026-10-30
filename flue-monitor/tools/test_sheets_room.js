// Execute the actual Apps Script with in-memory Sheets; never contacts Google.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('google-sheets-logger/Code.gs', 'utf8');
const legacy = ['Timestamp','Thermocouple (C)','Cold Junction (C)','Event','Rate (C/min)','Zone'];
function harness(initial = [legacy, ['older',100,20,'',1,'cold']]) {
  const rows = initial.map(r=>r.slice()), formats = new Map();
  let locked=false, releases=0, columns=26, fail=false;
  const sheet = {
    getLastRow:()=>rows.length, getLastColumn:()=>Math.max(0,...rows.map(r=>r.length)),
    getMaxColumns:()=>columns, getMaxRows:()=>1000,
    insertColumnsAfter:(after,count)=>{assert.equal(after,columns);columns+=count;},
    appendRow:r=>{assert.ok(locked);if(fail)throw Error('write failed');rows.push(Array.from(r));},
    getRange:(row,col,height=1,width=1)=>({
      getValues:()=>[Array.from({length:width},(_,i)=>rows[row-1]?.[col-1+i] || '')],
      setValues:values=>{assert.ok(locked);rows[row-1] ||= [];values[0].forEach((v,i)=>rows[row-1][col-1+i]=v);},
      getNumberFormat:()=>formats.get(col) || 'Automatic',
      setNumberFormat:v=>formats.set(col,v),
    })
  };
  const context = {
    SpreadsheetApp:{getActiveSpreadsheet:()=>({getSheetByName:()=>sheet,insertSheet:()=>sheet}),flush:()=>assert.ok(locked)},
    LockService:{getScriptLock:()=>({tryLock:()=>{if(locked)return false;locked=true;return true;},releaseLock:()=>{locked=false;releases++;}})},
    ContentService:{MimeType:{TEXT:'text'},createTextOutput:text=>({setMimeType:()=>text})}
  };
  vm.createContext(context);vm.runInContext(source,context);
  return {rows,formats,send:(extra={})=>context.doGet({parameter:{secret:'REPLACE_ME_WITH_A_RANDOM_STRING',thermocouple:'123.4',cold_junction:'21.2',event:'added_wood',rate:'1.25',zone:'cold',event_ts:'1793358000',...extra}}),
    setLock:v=>locked=v,setFail:v=>fail=v,get releases(){return releases;}};
}
for (const input of [undefined,'','  ','bad','1000','Infinity','NaN','-41','61','=1+1']) {
  const h=harness();assert.equal(h.send({room_temperature:input}),'ok');assert.equal(h.rows.at(-1)[6],'');
}
for (const input of ['19.6','0','-10.5','60','-40']) {
  const h=harness();h.send({room_temperature:input});assert.equal(h.rows.at(-1)[6],Number(input));
  assert.equal(h.formats.get(7),'0.0');assert.equal(h.rows[1].length,6);
  assert.equal(h.rows.at(-1)[0].getTime(),1793358000000);
}
const h=harness();h.send({humidity:'45.6',fan_on:'true',note:'=IMPORTXML("bad")'});
assert.deepEqual(h.rows[0].slice(0,6),legacy);
function value(h,key){return h.rows.at(-1)[h.rows[0].indexOf(key)];}
assert.equal(value(h,'humidity'),45.6);assert.equal(value(h,'fan_on'),'true');
assert.equal(value(h,'note'),'\'=IMPORTXML("bad")');
h.send({humidity:'0',new_sensor:'-1.5'});assert.equal(value(h,'humidity'),0);
assert.equal(value(h,'fan_on'),'');assert.equal(value(h,'new_sensor'),-1.5);
assert.equal(h.rows[0].filter(x=>x==='humidity').length,1);
assert.ok(!h.rows[0].includes('secret'));assert.ok(!h.rows[0].includes('event_ts'));
const reordered=harness([['humidity',...legacy.slice().reverse()]]);
reordered.send({humidity:'50'});assert.equal(value(reordered,'humidity'),50);
assert.equal(value(reordered,'Thermocouple (C)'),123.4);
const fresh=harness([]);fresh.send();assert.equal(fresh.rows[0].length,7);
const denied=harness();assert.equal(denied.send({secret:'wrong'}),'forbidden');assert.equal(denied.rows.length,2);assert.equal(denied.releases,0);
const busy=harness();busy.setLock(true);assert.equal(busy.send(),'busy');assert.equal(busy.rows.length,2);
const failed=harness();failed.setFail(true);assert.throws(()=>failed.send(),/write failed/);assert.equal(failed.releases,1);
const wide=harness();wide.send(Object.fromEntries(Array.from({length:30},(_,i)=>['sensor_'+i,String(i)])));assert.equal(wide.rows[0].length,37);
console.log('PASS actual Sheets handler: dynamic fields, reordered headers, old rows, types, blanks, formula escaping, authentication, locking and column expansion');
