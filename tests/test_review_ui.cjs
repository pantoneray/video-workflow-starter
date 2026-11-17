// Execute the shipped UI in a minimal DOM; this is not a browser visual test.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const listeners = {};
const status = {textContent: ''};
const decision = {value: 'pending'};
const checkbox = {dataset: {check:'meaning'}, checked:false};
const selection = {value:''};
const card = {dataset:{index:'0'}, querySelector:s=>({'[data-decision]':decision,'[data-comment]':{value:''},'[data-selection]':selection}[s]), querySelectorAll:()=>[checkbox]};
const data = {stage:'T1',task_id:'sample',version:'v1',items:[{id:'01',version:'r1',content_sha256:'hash',required_checks:['meaning'],approval_blockers:[]}]};
const submit = {disabled:false,addEventListener:(name,fn)=>listeners.submit=fn};
const download = {addEventListener:(name,fn)=>listeners.download=fn};
const refresh = {disabled:true,addEventListener:(name,fn)=>listeners.refresh=fn};
let requests=0;
const receiptId = 'a'.repeat(64);
const stored = new Map();
const sessionStorage = {getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)};
const ctx = {document:{getElementById:id=>({'review-data':{textContent:JSON.stringify(data)},status,submit,download,refresh}[id]),querySelectorAll:()=>[card]},window:{},AbortController,setTimeout,clearTimeout,Date,JSON,console,
fetch:async()=>{requests++;return {ok:true,json:async()=>({accepted:true,state:'received',id:receiptId})};}};
ctx.window.sessionStorage = sessionStorage;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../templates/reviews/review.js'),'utf8'),ctx);
(async()=>{
  decision.value='approved';
  await listeners.submit(); assert.equal(requests,0); assert.match(status.textContent,/核对/);
  checkbox.checked=true;
  await listeners.submit(); assert.equal(requests,0); assert.match(status.textContent,/请选择 A 或 B/);
  selection.value='A';
  await listeners.submit(); assert.equal(requests,0); assert.match(status.textContent,/离线页面/);
  ctx.window.REVIEW_TRANSPORT={submit_url:'/submit',status_url:'/status/',token:'test'};
  await listeners.submit(); assert.equal(requests,1); assert.match(status.textContent,/已接收/); assert.doesNotMatch(status.textContent,/处理完成/);
  assert.equal(refresh.disabled,false);
  ctx.fetch=async(url,options)=>{assert.equal(url,'/status/'+receiptId);assert.equal(options.method,undefined);return {ok:true,json:async()=>({accepted:true,state:'completed',id:receiptId})};};
  await listeners.refresh(); assert.match(status.textContent,/处理完成/);
  ctx.fetch=async()=>{throw Error('network failed');};
  await listeners.refresh(); assert.match(status.textContent,/已保存的收据不受影响/);
  await listeners.submit(); assert.match(status.textContent,/结果待核/); assert.equal(submit.disabled,false);
  assert.equal(stored.size,1); assert.equal([...stored.values()][0],receiptId);
  const code=fs.readFileSync(path.join(__dirname,'../templates/reviews/review.js'),'utf8');
  const reload = () => {
    status.textContent='待提交'; refresh.disabled=true;
    const next={...ctx};vm.createContext(next);vm.runInContext(code,next);
  };
  reload(); assert.match(status.textContent,/已恢复本轮收据编号/);
  assert.doesNotMatch(status.textContent,/处理完成/); assert.equal(refresh.disabled,false);
  assert.equal(requests,1); // Reload does not submit or query automatically.
  data.version='v2';reload();assert.equal(status.textContent,'待提交');assert.equal(refresh.disabled,true);
  data.version='v1';ctx.window.sessionStorage={getItem:()=>{throw Error('blocked');},setItem:()=>{throw Error('blocked');}};
  reload();assert.equal(status.textContent,'待提交');
  console.log('UI: checks, offline, accepted, failures, scoped reload, blocked storage passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
