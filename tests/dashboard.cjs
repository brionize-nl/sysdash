const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('web/app.js','utf8');
const extract=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b,src.indexOf(a)));
(async()=>{
let ctx={DEMO:false,STATE:{latest:{fixture:{cpu:5,ts:new Date().toISOString()}}},api:async()=>[{machine:'fixture',cpu:99,ts:'2000-01-01T00:00:00Z'}]};vm.createContext(ctx);vm.runInContext(extract('async function loadLive()','function setLive()'),ctx);await ctx.loadLive();assert.equal(ctx.STATE.latest.fixture.cpu,5);
ctx={STATE:{machines:[{machine:'extra',tailscale_ip:'100.64.0.2'}]},CFG:{hub:'http://100.64.0.1:9000'},location:{protocol:'https:',pathname:'/',search:''},alert:()=>{}};vm.createContext(ctx);vm.runInContext(extract('function needsTailscaleHop(','function callGateway('),ctx);assert(ctx.needsTailscaleHop('extra'));assert.equal(ctx.location.href,'http://100.64.0.1:9000/?machine=extra');
ctx={PERF_BUSY_CPU:65,PERF_MIN_SAMPLES:10,num:Number};vm.createContext(ctx);vm.runInContext(extract('function findSession(','async function loadPerf('),ctx);assert.equal(ctx.findSession(Array.from({length:10},(_,i)=>({cpu:90,ts:new Date(1700000000000+i*3600000).toISOString()}))),null);assert(ctx.findSession(Array.from({length:11},(_,i)=>({cpu:90,ts:new Date(1700000000000+i*30000).toISOString()}))));
let calls=0;ctx={api:async path=>{calls++;const off=Number(path.split('offset=')[1]);return Array.from({length:Math.max(0,Math.min(100,1201-off))},(_,i)=>i+off)}};vm.createContext(ctx);vm.runInContext(extract('async function paged(','function holdWrite('),ctx);assert.equal((await ctx.paged('metrics?order=ts.asc')).length,1201);assert(calls>2);
function runWorkflow(file,rows,machines,store={},config={}){
 const d=JSON.parse(fs.readFileSync('n8n/'+file+'.json'));const n=d.nodes.find(n=>n.type==='n8n-nodes-base.code');const ctx={$input:{all:()=>rows.map(json=>({json}))},$getWorkflowStaticData:()=>store,$env:{HEALTHCHECK_PING_URL:'https://mock.invalid'},$json:{status:'ok'},$:name=>({all:()=>name==='Machines ophalen'||name==='Inventaris'?machines.map(json=>({json})):name==='Laatste metingen'?rows.map(json=>({json})):name==='Bezorgingsstatus'?[{json:{last_delivery:new Date().toISOString()}}]:[{json:{thresholds:{default:config}}}]})};vm.createContext(ctx);return vm.runInContext('(function(){'+n.parameters.jsCode+'})()',ctx);
}
const row={machine:'fixture',ts:new Date().toISOString(),cpu:20,mem:30,disk:10,updates:1,temp:80,disks:[{mount:'/data',pct:99}],battery:10,bat_plugged:false,extra:{}};
let store={};let out=runWorkflow('alerts',[row],[{machine:'fixture',thresholds:{temp_alarm:75}}],store);assert(out.some(x=>x.json.caption.includes('/data')));assert(!out.some(x=>x.json.caption.includes('TE HEET')));store.hotSince.fixture=Date.now()-180000;out=runWorkflow('alerts',[row],[{machine:'fixture',thresholds:{temp_alarm:75}}],store);assert(out.some(x=>x.json.caption.includes('TE HEET')));
out=runWorkflow('alerts',[],[{machine:'missing'}]);assert(out.some(x=>x.json.caption.includes('OFFLINE')));
for(const file of ['report','updates','battery'])assert(Array.isArray(runWorkflow(file,[row],[{machine:'fixture'}])));
assert.equal(runWorkflow('heartbeat',[row],[{machine:'fixture'}]).length,1);assert.throws(()=>runWorkflow('heartbeat',[],[{machine:'fixture'}]));
console.log('Dashboard/workflow regressions OK (stale live, hub hop, gaps, pagination, mounts, overrides, sustained temperature, missing machine, heartbeat).');
})();
