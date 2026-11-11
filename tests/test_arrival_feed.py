"""Replay valid late extras and originals through the exact staged adapter."""
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rescue.arrival_output import ArrivalOutput as TrialOutput
from rescue.feed import Records, beast, CORRECTION

P = "8d40621d58c382d690c8ac2863a7"
Q = "8d40621d58c386435cc412692ad6"
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    config = root / "methods.json"
    config.write_text(json.dumps(dict(energy=True, neural=True)))
    trial = TrialOutput(SimpleNamespace(runtime=root, config=config), 8)
    output = []
    trial.publish = output.append
    now = time.monotonic()
    raw = b"opaque" + beast(P, CORRECTION + 10) + beast(P, CORRECTION + 1200000)
    trial.stock(Records().feed(raw), now)
    assert b"".join(output) == raw
    batch = dict(epoch=8, created_unix=time.time(),
                 alignment=dict(verified=True, matches=20, median_abs_error_us=0),
                 extra=[dict(source="energy", ticks=600000, message_hex=Q)])
    original = Path.read_text

    def config_read(path, *args, **kwargs):
        if str(path) == "/etc/default/adsb-rescue-workers.json":
            return "{}"
        return original(path, *args, **kwargs)

    with patch.object(Path, "read_text", config_read):
        trial.batch(batch, now, time.time())
        trial.batch(batch, now, time.time())
        trial.batch(dict(batch, epoch=9), now, time.time())
    expected = beast(Q, CORRECTION + 600000)
    assert b"".join(output) == raw + expected
    assert trial.count["out_of_order_energy"] == 1
    assert trial.relay.count["duplicates_rejected"] == 1 and trial.count["wrong_epoch"] == 1
    trial.stock(Records().feed(expected), now)
    assert b"".join(output) == raw + expected + expected
    assert trial.relay.cache.count["late_stock_after_extra_race"] == 1
    print("Exact staged adapter passed immediate stock, backward DSP, duplicate, epoch and late-stock checks")

import asyncio


async def client_handshake():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        endpoint = TrialOutput(SimpleNamespace(runtime=root, config=None), 8)
        server = await asyncio.start_server(endpoint.serve, "127.0.0.1", 0)
        async with server:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.sockets[0].getsockname()[1])
            try:
                writer.write(b"\x1a1J\x1a1d")
                await writer.drain()
                await asyncio.sleep(.03)
                assert len(endpoint.clients) == 1, "Receiver configuration closed the stream"
                endpoint.publish(b"stock-data")
                assert await asyncio.wait_for(reader.readexactly(10), 1) == b"stock-data"
            finally:
                writer.close()
                await writer.wait_closed()


asyncio.run(client_handshake())
print("Receiver configuration bytes preserve the subscription")

import unittest
class AdapterChecks(unittest.TestCase):
    def test_completed_adapter_checks(self):
        self.assertEqual(trial.relay.cache.count["late_stock_after_extra_race"],1)

class ArrivalBurstTests(unittest.IsolatedAsyncioTestCase):
 async def test_large_stock_burst_does_not_starve_subscribers(self):
  import socket
  from types import SimpleNamespace
  from rescue.arrival_feed import run
  raw=b''.join(beast(P,i*3000+CORRECTION) for i in range(6000));gate=asyncio.Event();end=asyncio.Event()
  async def source(reader,writer):
   await gate.wait();writer.write(raw);await writer.drain();await end.wait();writer.close()
  upstream=await asyncio.start_server(source,'127.0.0.1',0)
  probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
  with tempfile.TemporaryDirectory() as d:
   path=Path(d);cfg=path/'cfg';cfg.write_text(json.dumps(dict(energy=True,sic=False)))
   a=SimpleNamespace(receiver_epoch=8,config=cfg,runtime=path,stock_port=upstream.sockets[0].getsockname()[1],port=port);task=asyncio.create_task(run(a));writer=None
   try:
    for i in range(100):
     try:reader,writer=await asyncio.open_connection('127.0.0.1',port);break
     except OSError:await asyncio.sleep(.01)
    self.assertIsNotNone(writer);gate.set();received=await asyncio.wait_for(reader.readexactly(len(raw)),5);self.assertEqual(received,raw)
   finally:
    end.set()
    if writer:writer.close();await writer.wait_closed()
    task.cancel();await asyncio.gather(task,return_exceptions=True)
  upstream.close();await upstream.wait_closed()
