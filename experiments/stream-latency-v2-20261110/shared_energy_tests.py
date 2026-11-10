"""Standalone tests; no receiver, files, model runtime or network required."""
import unittest
from dataclasses import replace
from shared_energy import EnergyCompletion, SharedEnergyFeed, EnergyAccounting, completion_from_block, COVERAGE

PAYLOAD='8d40621d58c382d690c8ac2863a7'


def receipt(sequence=0, start=100, end=200, available=.05, done=False, **kw):
    fields=dict(epoch=7,window='a',sequence=sequence,start_tick=start,end_tick=end,
                observed_through_tick=end+20,watermark=end-10,available_s=available,
                rows=({'source':'energy','ticks':start+1,'message_hex':PAYLOAD},),
                done=done,producer_id=f'a:{sequence}',producer_cpu_s=.01)
    fields.update(kw)
    return EnergyCompletion(**fields)


class SharedEnergyTests(unittest.TestCase):
    def feed(self, **kw):
        out=[]
        f=SharedEnergyFeed(7,lambda *args:out.append(args),**kw)
        f.begin('a',100,300)
        return f,out

    def test_causal_future_not_authorized(self):
        f,out=self.feed()
        with self.assertRaises(ValueError):f.submit(receipt(available=.051),.05)
        self.assertFalse(out)
        self.assertEqual(f.count['queued_completions'],0)

    def test_replay_release_uses_availability_not_RF_end(self):
        f,out=self.feed(replay=True)
        f.queue_replay(receipt(available=.2))
        self.assertEqual(f.release(.199),0)
        self.assertFalse(out)
        self.assertEqual(f.release(.2),1)
        self.assertEqual(out[0][:3],('a','energy',7))
        self.assertEqual(f.release(.2),0)

    def test_normal_callback_and_ownership(self):
        f,out=self.feed()
        self.assertEqual(f.submit(receipt(),.05),1)
        self.assertEqual(out[0][4:],(190,False))
        self.assertEqual(f.submit(receipt(1,200,300,.1,True),.1),1)
        self.assertFalse(f.windows)
        self.assertEqual(f.count['delivered_rows'],2)
        with self.assertRaises(ValueError):f.begin('a',100,300)

    def test_source_rows_are_immutable_copies(self):
        f,out=self.feed(replay=True)
        c=receipt(available=.2)
        f.queue_replay(c)
        c.rows[0]['message_hex']='bad caller mutation'
        c.rows[0]['ticks']=99999
        f.release(.2)
        self.assertEqual(out[0][3][0],dict(source='energy',ticks=101,message_hex=PAYLOAD))

    def test_epoch_gap_overlap_repetition_rejected(self):
        f,out=self.feed()
        for c in [receipt(epoch=8),receipt(sequence=1),receipt(start=101),receipt(start=99)]:
            with self.assertRaises(ValueError):f.submit(c,.05)
        f.submit(receipt(),.05)
        with self.assertRaises(ValueError):f.submit(receipt(),.05)
        self.assertEqual(len(out),1)

    def test_extras_only_missing_coverage_rejected(self):
        f,out=self.feed()
        with self.assertRaises(ValueError):f.submit(receipt(coverage='accepted_extras_only'),.05)
        self.assertFalse(out)

    def test_candidate_may_lead_conservative_watermark(self):
        f,out=self.feed()
        f.submit(receipt(watermark=150,rows=({'source':'energy','ticks':199,'message_hex':PAYLOAD},)),.05)
        self.assertEqual(out[0][3][0]['ticks'],199)
        self.assertEqual(out[0][4],150)

    def test_bad_provenance_and_future_RF_rejected(self):
        f,out=self.feed()
        for c in [receipt(watermark=221),receipt(observed_through_tick=199),receipt(available_s=float('nan')),
                  receipt(done=True),receipt(producer_cpu_s=-1),receipt(rows=({'source':'neural','ticks':101,'message_hex':PAYLOAD},)),
                  receipt(rows=({'source':'energy','ticks':200,'message_hex':PAYLOAD},))]:
            with self.assertRaises(ValueError):f.submit(c,.05)
        self.assertFalse(out)

    def test_regressing_clocks_and_watermarks_rejected(self):
        f,out=self.feed()
        f.submit(receipt(),.05)
        for c in [receipt(1,200,300,.04,True),receipt(1,200,300,.1,True,watermark=180)]:
            with self.assertRaises(ValueError):f.submit(c,.1)
        with self.assertRaises(ValueError):f.release(.049)

    def test_bounded_memory(self):
        f,out=self.feed(replay=True,max_pending=1,max_rows=1)
        f.queue_replay(receipt(available=.2))
        with self.assertRaises(OverflowError):f.queue_replay(receipt(1,200,300,.3,True))
        self.assertEqual(f.pending_rows,1)
        f.release(.2)
        self.assertEqual(f.pending_rows,0)

    def test_empty_complete_block_is_a_real_completion(self):
        f,out=self.feed()
        f.submit(receipt(rows=()),.05)
        self.assertEqual(out[0][3],[])
        self.assertEqual(f.count['delivered_completions'],1)

    def test_upstream_compute_counted_once_across_consumers(self):
        ledger=EnergyAccounting()
        f,_=self.feed(accounting=ledger)
        g,_=self.feed(accounting=ledger)
        f.submit(receipt(),.05);g.submit(receipt(),.05)
        q=ledger.summary(1)
        self.assertEqual(q['unique_upstream_jobs'],1)
        self.assertEqual(q['upstream_cpu_s_counted_once'],.01)
        self.assertEqual(q['duplicate_energy_decodes_by_adapter'],0)
        self.assertGreater(q['adapter_cpu_s'],0)
        with self.assertRaises(ValueError):ledger.record('a:0',.02)

    def test_50ms_block_adapter_preserves_all_owned_anchors(self):
        first=100000;total=2401200;lo=(first+600)*5;end=(first+600+2400000)*5
        out=[];f=SharedEnergyFeed(7,lambda *args:out.append(args));f.begin_case(0,{'first':first})
        owned=[]
        for i,at in enumerate(range(0,total,120000)):
            stop=min(total,at+120000)
            candidates=[dict(source='energy',ticks=x,message_hex=PAYLOAD) for x in [(first+at)*5,(first+stop)*5-1]]
            c=completion_from_block(epoch=7,window=0,index=i,first=first,total_samples=total,stop=stop,
                                    rows=candidates,available_s=(i+1)*.05,producer_cpu_s=.001)
            f.submit(c,(i+1)*.05)
            owned.extend(c.rows)
        self.assertEqual(len(out),21)
        self.assertTrue(out[-1][-1])
        self.assertEqual(out[-1][-2],end+1440)
        self.assertTrue(all(lo<=r['ticks']<end for r in owned))
        self.assertEqual(len(owned),40)
        self.assertEqual(len({r['ticks'] for r in owned}),len(owned))
        self.assertEqual(f.count['delivered_rows'],40)
        self.assertFalse(f.pending)
        self.assertFalse(f.windows)


if __name__=='__main__':unittest.main(verbosity=2)
