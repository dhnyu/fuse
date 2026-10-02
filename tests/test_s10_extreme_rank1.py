"""Small scientific-contract fixtures; no production/model execution."""
import ast
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import s10_extreme_rank1 as m

class ExtremeTests(unittest.TestCase):
    def test_self_distance_candidate_tie_and_blocks(self):
        ids=['a','b','c','d'];x=np.ones((4,2),np.float32)/np.sqrt(np.float32(2))
        centers=np.array([[0,0],[1999,0],[2000,0],[5000,0]],float)
        a=m.rank1(x,centers,ids,1);b=m.rank1(x,centers,ids,3)
        self.assertEqual(a,b)
        self.assertEqual(a[0]['rank1_scene_id'],'b')
        self.assertEqual(a[0]['nonlocal_rank1_scene_id'],'c')
        self.assertEqual(a[0]['nonlocal_distance_m'],2000)
        self.assertTrue(all(r['query_scene_id']!=r['rank1_scene_id'] for r in a))
    def test_four_sets_and_boundary_ties(self):
        rows=[{'query_scene_id':f'{i:04}','rank1_cosine':1.,'nonlocal_rank1_cosine':1.} for i in reversed(range(210))]
        sets=m.memberships(rows)
        self.assertEqual(set(sets),set(m.SETS))
        for rs in sets.values():self.assertEqual([r['query_scene_id'] for r in rs],[f'{i:04}' for i in range(100)])
    def test_band_semantics(self):
        self.assertEqual(m.band_ranks(8999),{'most':[1],'top':list(range(2,12)),'middle':list(range(4495,4505)),'bottom':list(range(8990,9000))})
    def test_no_model_dependency(self):
        tree=ast.parse(Path(m.__file__).read_text())
        imports=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imports += [x.name for x in n.names]
            if isinstance(n,ast.ImportFrom):imports.append(n.module or '')
        self.assertFalse(any('torch' in x or 'training' in x or 'inference' in x for x in imports))
    def test_envelope_hash_rejects_tampering(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'manifest.json';v={'body':{},'files':[]};h=m.digest(v);v.update(sha256=h,artifact_id='test_'+h[:24]);p.write_text(json.dumps(v));m.envelope(p)
            v['body']['changed']=True;p.write_text(json.dumps(v))
            with self.assertRaises(ValueError):m.envelope(p)

if __name__=='__main__':unittest.main()
