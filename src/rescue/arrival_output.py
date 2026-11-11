"""Arrival-order output from the existing stock/outbox reader."""
import asyncio
import json
import math
import os
import time
from collections import Counter
from pathlib import Path

from .async_dedup import HistoryMerge
from .async_immediate import ImmediateRelay
from rescue.feed import ALLOWED, MOD, unwrap
from rescue.pipeline import settings
from rescue.wire import BeastParser

LIMITS_MS = (50, 100, 250, 500, 1000, 2000, 3000)


class ArrivalRelay(ImmediateRelay):
    def push(self, tick, deadline, wire, source):
        self.seq += 1
        self.heap.append((tick, self.seq, deadline, wire, source))
        self.bytes += len(wire)
        if self.bytes > 16 * 1048576 or len(self.heap) > 200000:
            raise RuntimeError("Immediate output cap")

    def ready(self, now):
        # This owner serializes stock reads and admitted outbox batches.
        records, self.heap = self.heap, []
        self.bytes = 0
        return b"".join(record[3] for record in records)

    def stock(self, wire, frame, now, epoch=None):
        super().stock(wire, frame, now, epoch)
        self.count["stock_bytes_relayed"] += len(wire)


class ArrivalOutput:
    def __init__(self, args, epoch):
        self.relay = ArrivalRelay(HistoryMerge, allowed_sources=ALLOWED,
                                max_extra_age=3, config=args.config)
        self.epoch = epoch
        self.status = args.runtime / "feed-arrival-status.json"
        self.count = Counter()
        self.clients = {}
        self.high_tick = None
        self.ages = Counter()
        self.started = time.time()
        self.fault = None

    def safe(self, action, *args):
        if self.fault is None:
            try:
                action(*args)
            except Exception as exc:
                self.fault = type(exc).__name__
                for writer in list(self.clients):
                    writer.close()

    async def serve(self, reader, writer):
        if self.fault:
            writer.close()
            return
        pending = asyncio.Queue(256)
        self.clients[writer] = pending
        self.count["client_connections"] += 1

        async def send():
            while True:
                raw = await pending.get()
                writer.write(raw)
                await asyncio.wait_for(writer.drain(), .5)
                self.count["client_bytes"] += len(raw)

        async def receive():
            while await reader.read(4096):
                pass

        sender = asyncio.create_task(send())
        receiver = asyncio.create_task(receive())
        try:
            await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.clients.pop(writer, None)
            sender.cancel()
            receiver.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)
            writer.close()

    def publish(self, raw):
        if not raw:
            return
        for writer, pending in list(self.clients.items()):
            try:
                pending.put_nowait(raw)
            except asyncio.QueueFull:
                self.count["slow_clients_closed"] += 1
                writer.close()

    def observe_tick(self, tick, source):
        if self.high_tick is not None and tick < self.high_tick:
            self.count["out_of_order_" + source] += 1
            self.count["max_backwards_ticks"] = max(
                self.count["max_backwards_ticks"], self.high_tick - tick)
        self.high_tick = tick if self.high_tick is None else max(self.high_tick, tick)

    def stock(self, records, now):
        pieces = []
        for wire, frame in records:
            self.relay.stock(wire, frame, now, epoch=self.epoch)
            if frame:
                self.observe_tick(self.relay.anchor, "stock")
            pieces.append(self.relay.ready(now))
        self.publish(b"".join(pieces))

    def batch(self, batch, now, unix):
        if not isinstance(batch, dict) or batch.get("epoch") != self.epoch:
            self.count["wrong_epoch"] += 1
            return
        audit = batch.get("alignment")
        events = batch.get("extra")
        created = batch.get("created_unix")
        if not isinstance(audit, dict) or not isinstance(events, list):
            self.count["invalid_contract"] += 1
            return
        median = audit.get("median_abs_error_us")
        matches = audit.get("matches")
        if (audit.get("verified") is not True or type(matches) is not int or matches < 20
                or type(median) not in (int, float) or not math.isfinite(median)
                or not 0 <= median <= 2 or type(created) not in (int, float)
                or not math.isfinite(created) or len(events) > 5000):
            self.count["invalid_contract"] += 1
            return
        enabled = settings(self.relay.config)
        workers = json.loads(Path("/etc/default/adsb-rescue-workers.json").read_text())
        enabled.update({name: bool(workers.get("sequence_acquisition") and
                                   workers.get(name + "_enabled"))
                        for name in ("sequence", "acquisition")})
        pieces = []
        for event in events:
            if (not isinstance(event, dict) or type(event.get("ticks")) not in (int, float)
                    or not math.isfinite(event["ticks"])
                    or not isinstance(event.get("source"), str)):
                self.count["invalid_event"] += 1
                continue
            source = event["source"]
            self.relay.batch(dict(batch, extra=[event]), now, unix, enabled)
            raw = self.relay.ready(now)
            if not raw:
                continue
            frame = BeastParser().feed(raw)[0]
            tick = unwrap(frame["ticks_12mhz"] % MOD, self.relay.anchor)
            self.observe_tick(tick, source)
            age = (self.relay.anchor - tick) / 12000
            bucket = next((limit for limit in LIMITS_MS if age <= limit), "older")
            self.ages[f"{source}:{bucket}"] += 1
            self.count["forwarded_" + source] += 1
            pieces.append(raw)
        self.publish(b"".join(pieces))

    def disconnect(self):
        for writer in list(self.clients):
            writer.close()
        self.relay.reset_source()
        self.relay.epoch = None
        self.relay.cache.reset(None)
        self.high_tick = None

    def write_status(self, connected):
        value = dict(pid=os.getpid(), updated_unix=time.time(), started_unix=self.started,
                     connected=connected, clients=len(self.clients), epoch=self.epoch,
                     counts=dict(self.count), policy=dict(self.relay.count),
                     dedup=dict(self.relay.cache.count), rf_age_ms_buckets=dict(self.ages),
                     holdback_s=0, fault=self.fault)
        temporary = self.status.with_suffix(".tmp")
        temporary.write_text(json.dumps(value))
        temporary.replace(self.status)
