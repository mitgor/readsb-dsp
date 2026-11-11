const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('dashboard/statistics.html','utf8').split('<script>')[1].split('</script>')[0];
const elements=new Map(),posts=[];let relay={available:true,revision:'r1',desired_mode:'arrival_order',actual_holdback_s:0,native_backend:'incremental_native',guard_state:'active',operation:{state:'idle'}};
function element(){return {textContent:'',disabled:false,checked:false,append(){},replaceChildren(){},addEventListener(event,fn){this[event]=fn}}}
const status={updated_unix:Date.now()/1000,health:{gain_db:38.6},counts:{aligned_seconds:1},distance:{total:{stock_df17:1},bins_nm:{}},workers:{},archive:{files:[]},input:{},method_switches:{energy:true}};
const ctx={URL,Date,Number,Object,Promise,Math,console,location:{origin:'http://receiver'},AbortController,document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id)},createElement:element},setTimeout(){return 1},clearTimeout(){},setInterval(){},fetch:async(url,opts={})=>{let path=new URL(url,'http://receiver').pathname;let data;if(path.endsWith('/relay')){if(opts.method==='POST'){let body=JSON.parse(opts.body);posts.push(body);relay={...relay,revision:'r'+(posts.length+1),desired_mode:body.mode,actual_holdback_s:body.mode==='ordered_3s'?3:0}}data=relay}else if(path.endsWith('dashboard-status'))data=status;else if(path.endsWith('api/settings'))data={methods:{energy:true},capture:{},operation:{state:'idle'}};else data={updated_unix:Date.now()/1000,counts:{},stock_connected:true};return {ok:true,json:async()=>data}}};
vm.runInNewContext(script,ctx);
setImmediate(async()=>{
 let checkbox=elements.get('ordered-relay'),button=elements.get('apply-relay');assert.equal(checkbox.checked,false);assert.equal(button.disabled,false);
 checkbox.checked=true;checkbox.change();await button.onclick();assert.equal(posts[0].mode,'ordered_3s');assert.equal(posts[0].revision,'r1');assert.equal(checkbox.checked,true);
 checkbox.checked=false;checkbox.change();await button.onclick();assert.equal(posts[1].mode,'arrival_order');assert.equal(checkbox.checked,false);assert.match(elements.get('relay-mode').textContent,/incremental_native/);
 console.log('Dashboard submits explicit ordered/arrival revisions and displays actual native backend.');
});
