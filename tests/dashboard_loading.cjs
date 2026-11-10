// Exercise the shipped page, with a capture request that never resolves.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('dashboard/statistics.html','utf8').split('<script>')[1].split('</script>')[0];
const elements=new Map(),intervals=[],requests=[];
function element(){return {textContent:'',disabled:false,append(){},replaceChildren(){},addEventListener(){}}}
const status={updated_unix:Date.now()/1000,health:{gain_db:38.6},counts:{aligned_seconds:123},distance:{total:{stock_df17:900,energy_extra:10},bins_nm:{}},workers:{},archive:{files:[]},input:{},method_switches:{energy:true}};
const context={URL,Date,Number,Object,Promise,Math,console,location:{origin:'http://receiver'},AbortController,
 document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id)},createElement:element},
 setTimeout(){return 1},clearTimeout(){},setInterval(fn){intervals.push(fn)},
 fetch:async url=>{const path=new URL(url).pathname;requests.push(path);
  if(path.endsWith('capture-status.json'))return new Promise(()=>{});
  let data=path.endsWith('dashboard-status')?status:path.endsWith('api/settings')?{methods:{energy:true},capture:{},operation:{state:'idle'}}:{updated_unix:Date.now()/1000,counts:{},stock_connected:true};
  return {ok:true,json:async()=>data};}
};
vm.runInNewContext(script,context);
setImmediate(async()=>{
 assert.equal(elements.get('stock').textContent,'900');
 assert.equal(elements.get('extras').textContent,'10');
 assert.equal(elements.get('apply').disabled,false);
 assert.equal(intervals.length,5);
 await intervals[0]();
 assert.equal(requests.filter(p=>p.endsWith('dashboard-status')).length,2);
 assert.equal(requests.filter(p=>p.endsWith('capture-status.json')).length,1);
 console.log('Statistics and controls render/retry while optional capture is stalled.');
});
