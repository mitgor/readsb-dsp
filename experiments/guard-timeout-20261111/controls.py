"""Offline controls use actual guard retry function and native budget definition."""
import ast,http.client,urllib.error,time,json,pathlib,subprocess,tempfile
R=pathlib.Path(__file__).resolve().parents[2]
def main():
 tree=ast.parse((R/'experiments/stream-latency-activation-20261110/deploy.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='monitoring_snapshot');ns=dict(time=time,http=http,urllib=urllib);exec(compile(ast.Module(body=[fn],type_ignores=[]),'guard','exec'),ns);retry=ns['monitoring_snapshot'];checks=[]
 for failures in [0,1,2,3]:
  calls=[];pauses=[]
  def fetch():
   calls.append(1)
   if len(calls)<=failures:raise http.client.RemoteDisconnected('injected')
   return {'fresh':len(calls)}
  try:out=retry(fetch,pauses.append);assert failures<3 and out['fresh']==failures+1
  except http.client.RemoteDisconnected:assert failures==3
  assert len(calls)==min(3,failures+1) and len(pauses)==min(failures,2);checks.append('transport failures '+str(failures))
 for error in [AssertionError('real disconnect'),ValueError('bad JSON'),urllib.error.HTTPError('url',401,'auth',{},None)]:
  calls=[]
  def fetch():calls.append(1);raise error
  try:retry(fetch,lambda _:None);raise AssertionError('not raised')
  except type(error):pass
  assert len(calls)==1;checks.append(type(error).__name__+' not masked')
 src=(R/'readsb/contrib/stream1090-native/incremental.cpp').read_text();budget=src[src.index('struct Budget {'):src.index('struct Empty')]
 cpp='#include <cstdint>\n#include <algorithm>\n#include <cassert>\nint64_t cpu=0,wall=0;int64_t cpuUs(){return cpu;}int64_t nowUs(){return wall;}\n'+budget+'''int main(){Budget b(100000); wall=250000;cpu=3000;assert(b.expired()==0);cpu=100001;assert(b.expired()==-4);cpu=0;wall=1000001;assert(b.expired()==-6);Budget unlimited(0);cpu=wall=10000000;assert(unlimited.expired()==0);}\n'''
 with tempfile.TemporaryDirectory() as d:
  out=pathlib.Path(d)/'budget-control.cpp';out.write_text(cpp);subprocess.run(['c++','-std=c++20',str(out),'-o',str(out.with_suffix(''))],check=True);subprocess.run([str(out.with_suffix(''))],check=True)
 print(json.dumps(dict(passed=True,monitoring_controls=checks,budget_controls=['250ms deschedule allowed with 3ms CPU','100ms CPU rejected','1s wall rejected','explicit unlimited test binding retained'])))
if __name__=='__main__':main()
