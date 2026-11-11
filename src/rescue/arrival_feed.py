"""Production arrival-order transport with one stock/outbox owner, no RF decoding."""
import asyncio,json,os,time
from pathlib import Path
from .feed import Records
from .arrival_output import ArrivalOutput

async def run(a):
    epoch=getattr(a,'receiver_epoch',None)
    if epoch is None:
        process=await asyncio.create_subprocess_exec('systemctl','show','readsb','-p','MainPID','--value',stdout=asyncio.subprocess.PIPE)
        raw,_=await process.communicate();epoch=int(raw)
    if epoch<=0:raise RuntimeError('Primary receiver epoch unavailable')
    output=ArrivalOutput(a,epoch);connected=False;connected_since=None;error=None
    outbox=a.runtime/'feed-outbox';outbox.mkdir(parents=True,exist_ok=True)
    connection_base=0
    async def upstream():
        nonlocal connected,connected_since,error,connection_base
        while True:
            writer=None;parser=Records()
            try:
                reader,writer=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',getattr(a,'stock_port',30005)),10)
                connected=True;connected_since=time.time();error=None
                connection_base=output.relay.count['stock_bytes_relayed']
                output.count['upstream_connections']+=1
                while True:
                    try:raw=await asyncio.wait_for(reader.read(65536),15)
                    except asyncio.TimeoutError:continue
                    if not raw:raise ConnectionError('Stock source disconnected')
                    output.stock(parser.feed(raw),time.monotonic())
            except (OSError,asyncio.TimeoutError) as exc:
                error=repr(exc);output.count['upstream_disconnects']+=1
            finally:
                connected=False;connected_since=None
                if parser.buffer:output.stock([(bytes(parser.buffer),None)],time.monotonic())
                output.disconnect()
                if writer:writer.close()
            # Receiver restart changes sample-clock epoch; refresh before reconnection.
            process=await asyncio.create_subprocess_exec('systemctl','show','readsb','-p','MainPID','--value',stdout=asyncio.subprocess.PIPE)
            raw,_=await process.communicate();output.epoch=int(raw)
            await asyncio.sleep(2)
    async def pump():
        last=0
        while True:
            now=time.monotonic()
            for path in sorted(outbox.glob('*.json')):
                try:
                    if path.stat().st_size<2*1048576:output.batch(json.loads(path.read_text()),now,time.time())
                    else:output.count['oversize_batch']+=1
                except FileNotFoundError:output.count['outbox_file_races']+=1
                except (ValueError,KeyError,TypeError,OverflowError):output.count['malformed_batch']+=1
                finally:path.unlink(missing_ok=True)
            if now-last>1:
                output.write_status(connected)
                counts=dict(output.relay.count)
                for source in output.relay.allowed_sources:
                    counts['relayed_'+source]=output.count['forwarded_'+source]
                counts['dsp_frames_relayed']=sum(v for k,v in output.count.items() if k.startswith('forwarded_'))
                counts['upstream_connections']=output.count['upstream_connections']
                counts['client_bytes_sent']=output.count['client_bytes']
                status=dict(pid=os.getpid(),started_unix=output.started,updated_unix=time.time(),stock_connected=connected,upstream_connected_since_unix=connected_since,upstream_error=error,holdback_s=0,mode='arrival_order_stock_plus_validated_dsp',clients=len(output.clients),buffer_bytes=output.relay.bytes,counts=counts,current_connection_stock_bytes_relayed=counts.get('stock_bytes_relayed',0)-connection_base,fr24_routed=Path('/run/adsb-rescue/feed-routing.json').exists(),dedup=dict(output.relay.cache.count),fault=output.fault)
                temp=a.runtime/'feed-status.tmp';temp.write_text(json.dumps(status));temp.replace(a.runtime/'feed-status.json');last=now
            await asyncio.sleep(.005)
    server=await asyncio.start_server(output.serve,'127.0.0.1',a.port)
    async with server:await asyncio.gather(upstream(),pump(),server.serve_forever())
