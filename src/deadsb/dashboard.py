"""Loopback dashboard; CPU-policy writes only, no service/SDR/feeder access."""
from dataclasses import asdict
import hashlib,json,os,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .governor import Config

HTML='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>deadsb dsp</title><style>body{font:16px system-ui;background:#101b28;color:#e7eff8;max-width:1100px;margin:40px auto;padding:20px}section{background:#192b3e;border-radius:12px;padding:24px;margin:20px 0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #38516b}input,button{font:inherit;padding:8px;margin:6px}small{color:#adbed1}.scroll{overflow:auto}</style><h1>deadsb dsp</h1><p>readsb + energy + DSP + neural · stock-first reception</p><section><h2>CPU budget</h2><p id="state">Waiting for receiver status…</p><label>Target % <input id="target" type="number" min="5" max="94"></label><label>Ceiling % <input id="ceiling" type="number" min="6" max="95"></label><label><input id="enabled" type="checkbox">Adaptive rescue</label><button id="save">Save budget</button><p id="notice"></p><small>This is a cooperative total-CPU target, not a hard cap. Stock decoding and feeders keep priority. Rescue coverage may fall under load. Changes are read without a restart.</small></section><section><h2>Methods</h2><div class="scroll"><table><thead><tr><th>Method</th><th>Configured</th><th>Admission now</th><th>Additional packets</th><th>CPU seconds</th><th>CPU ms / extra</th></tr></thead><tbody id="methods"></tbody></table></div><small>Counts use validated original-first attribution. Shared frontend costs are separate; attribution is not causal marginal recovery or measured power.</small></section><section><h2>Reception</h2><pre id="health"></pre></section><script>
let rev=null,cfg=null,dirty=false;const by=id=>document.getElementById(id);for(const id of ['target','ceiling','enabled'])by(id).oninput=()=>dirty=true;
async function refresh(){try{const d=await(await fetch('/api/status',{cache:'no-store'})).json();if(!dirty){rev=d.revision;cfg=d.config;by('target').value=cfg.target_percent;by('ceiling').value=cfg.ceiling_percent;by('enabled').checked=cfg.enabled}const g=d.status.cpu_budget||{};by('state').textContent=`Total CPU: ${g.total_system_cpu_percent?.toFixed(1)??'unknown'}% · profile: ${g.profile??'inactive'} · ${g.reason??'Coordinator has not enabled CPU budgeting'}`;const root=by('methods');root.replaceChildren();const methods=d.status.method_switches||{}, metrics=d.status.method_metrics?.methods||{},level=g.level??0;for(const [name,on]of Object.entries(methods)){const active=on&&level<4&&!(level>=3&&name!=='energy')&&!(level>=2&&['coherent','neural','pulse','sequence','acquisition','header','sic','crc'].includes(name))&&!(level>=1&&['sequence','acquisition'].includes(name));const m=metrics[name]||{};const tr=document.createElement('tr');for(const value of [name,on?'on':'off',active?(level===1?'bounded':'eligible'):'off',m.additional_packets??'—',m.cpu_seconds?.toFixed(3)??'—',m.cpu_ms_per_additional?.toFixed(2)??'—']){let td=document.createElement('td');td.textContent=value;tr.append(td)}root.append(tr)}by('health').textContent=JSON.stringify({updated:d.status.updated_unix,workers:d.status.workers?.workers,pending:d.status.workers?.pending_jobs,distance:d.status.distance?.total},null,2)}catch(e){by('state').textContent='Status unavailable: '+e.message}}
by('save').onclick=async()=>{try{let conf={...cfg,target_percent:Number(by('target').value),ceiling_percent:Number(by('ceiling').value),enabled:by('enabled').checked};const r=await fetch('/api/budget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:rev,config:conf})});if(!r.ok)throw Error((await r.json()).error);dirty=false;by('notice').textContent='Budget saved. Coordinator must have --cpu-budget-config enabled.';refresh()}catch(e){by('notice').textContent=e.message}};refresh();setInterval(refresh,5000);
</script></html>'''

def create_server(runtime,config_path,port):
 runtime,config_path=Path(runtime),Path(config_path)
 lock=threading.Lock()
 class Handler(BaseHTTPRequestHandler):
  def reply(self,code,data,kind='application/json'):
   blob=data.encode() if kind.startswith('text/') else json.dumps(data).encode()
   self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob)
  def do_GET(self):
   if self.path=='/':return self.reply(200,HTML,'text/html; charset=utf-8')
   if self.path!='/api/status':return self.reply(404,{'error':'Unknown endpoint'})
   try:
    b=config_path.read_bytes();config=asdict(Config.from_dict(json.loads(b)))
    try:status=json.loads((runtime/'status.json').read_text())
    except FileNotFoundError:status={}
    self.reply(200,{'status':status,'config':config,'revision':hashlib.sha256(b).hexdigest()})
   except (OSError,ValueError):self.reply(503,{'error':'Invalid or unavailable status/config'})
  def do_POST(self):
   if self.path!='/api/budget' or self.headers.get('Origin')!='http://'+self.headers.get('Host','') or self.headers.get('Content-Type')!='application/json':return self.reply(403,{'error':'Same-origin JSON requests only'})
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<=4096:raise ValueError('Invalid request size')
    d=json.loads(self.rfile.read(n))
    self.save(d)
   except (OSError,ValueError,TypeError):self.reply(409,{'error':'Invalid settings or changed revision'})
  def save(self,d):
   with lock:
    if set(d)!= {'revision','config'} or d['revision']!=hashlib.sha256(config_path.read_bytes()).hexdigest():raise ValueError('Settings changed; reload')
    validated=Config.from_dict(d['config']);temp=config_path.with_suffix('.tmp');temp.write_text(json.dumps(asdict(validated),indent=2)+'\n');os.replace(temp,config_path);self.reply(200,{'saved':True})
  def log_message(self,*args):pass
  def setup(self):super().setup();self.connection.settimeout(5)
 return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def serve(runtime,config_path,port):
 create_server(runtime,config_path,port).serve_forever()
