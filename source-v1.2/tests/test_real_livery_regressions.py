from __future__ import annotations
import hashlib,os
from pathlib import Path
import unittest
from fh6garage.fh6_clivery import decode_clivery_file
from fh6garage.fh6_clivery.container import inflate_clivery
from fh6garage.fh6_clivery.scene import tree_stats
SAMPLE_3761_SHA256="565e75445c70501dc98c00cc76c1d162d703b1921fd55735fcccb857757dac18"
SAMPLE_2997_SHA256="677751360dba1a7fe6eead246236094836e9e1433709a0fd8dc5a1b2635f7ded"
EXPECTED_3761=((0,1,72,110,128,0,1,0),(1,21,128,833,851,1,21,1),(2,2980,851,96686,96704,4,2980,2),(3,2761,96704,185435,185453,1,2761,1),(4,2785,185453,274951,274969,1,2785,1),(5,3,274969,275071,275089,0,3,0),(6,0,275089,275089,275112,0,0,0),(7,0,275112,275112,275135,0,0,0),(8,0,275135,275135,275158,0,0,0),(9,18,275158,275767,275768,1,18,1),(10,0,275768,275768,275791,0,0,0))
EXPECTED_2997=((0,24,72,873,891,1,24,1),(1,156,891,6328,6346,17,156,3),(2,2894,6346,99596,99614,11,2894,2),(3,2989,99614,196013,196031,15,2989,4),(4,2964,196031,291624,291642,15,2964,3),(5,0,291642,291642,291665,0,0,0),(6,18,291665,292347,292365,4,18,2),(7,41,292365,293859,293860,7,41,2),(8,0,293860,293860,293883,0,0,0),(9,0,293883,293883,293906,0,0,0),(10,0,293906,293906,293929,0,0,0))
def _sample_path(v):
    x=os.environ.get(v)
    if not x:return None
    p=Path(x); return p if p.is_file() else None
def _sha256(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def _assert_artwork(test,path,expected_rows):
    result=decode_clivery_file(path); test.assertIsNotNone(result.artwork); artwork=result.artwork
    test.assertTrue(artwork.lossless_record_coverage); test.assertEqual(len(artwork.sections),11)
    payload,_=inflate_clivery(path.read_bytes())
    test.assertEqual(b"".join(r.raw for r in artwork.records),payload[result.body_start:result.body_end])
    actual=[]
    for section in artwork.sections:
        if section.root is None:nested=leaves=depth=0
        else:
            st=tree_stats(section.root); nested=st["nested_group_count"];leaves=st["leaf_count"];depth=st["max_group_depth"]
        actual.append((section.slot,section.declared_count,section.section_start,section.tree_end,section.section_end,nested,leaves,depth))
        test.assertTrue(section.complete);test.assertEqual(section.parsed_leaf_count,section.declared_count);test.assertEqual(section.unknown_spans,())
    test.assertEqual(tuple(actual),expected_rows)
class RealLiveryRegressionTests(unittest.TestCase):
    def test_car_3761_fluorite_ake_when_sample_is_available(self):
        p=_sample_path("FH6_CLIVERY_3761")
        if p is None:self.skipTest("set FH6_CLIVERY_3761 to uploaded raw sample C_livery(1)")
        self.assertEqual(_sha256(p),SAMPLE_3761_SHA256);r=decode_clivery_file(p)
        self.assertEqual((r.car_id,r.gyvl_offset,r.body_start,r.body_end),(3761,51,72,275791));self.assertEqual([x.declared_count for x in r.sections],[1,21,2980,2761,2785,3,0,0,0,18,0]);_assert_artwork(self,p,EXPECTED_3761)
    def test_livery_2997_when_sample_is_available(self):
        p=_sample_path("FH6_CLIVERY_2997")
        if p is None:self.skipTest("set FH6_CLIVERY_2997 to uploaded raw sample C_livery(2)")
        self.assertEqual(_sha256(p),SAMPLE_2997_SHA256);r=decode_clivery_file(p)
        self.assertEqual((r.car_id,r.gyvl_offset,r.body_start,r.body_end),(2997,51,72,293929));self.assertEqual([x.declared_count for x in r.sections],[24,156,2894,2989,2964,0,18,41,0,0,0]);_assert_artwork(self,p,EXPECTED_2997)
if __name__=="__main__": unittest.main()
