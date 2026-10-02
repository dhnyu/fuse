"""OBJ20 boundary, deterministic query ties and unchanged candidate eligibility."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_s10_obj20_high import select

class Obj20Tests(unittest.TestCase):
    def test_boundary_and_ties(self):
        rows=[{'query_scene_id':f'q{i:03}','rank1_scene_id':'empty_candidate','rank1_cosine':1.,'nonlocal_rank1_cosine':1.} for i in reversed(range(104))]
        counts={r['query_scene_id']:{'n_buildings':0,'n_roads':0,'n_pois':20} for r in rows}
        for i,n in [(0,0),(1,1),(2,19)]:counts[f'q{i:03}']['n_pois']=n
        for mode in ('standard','nonlocal'):
            result=select(rows,counts,mode)
            self.assertEqual([r['query_scene_id'] for r in result],[f'q{i:03}' for i in range(3,103)])
            self.assertTrue(all(r['rank1_scene_id']=='empty_candidate' for r in result))
    def test_fewer_than_100_fails(self):
        with self.assertRaises(ValueError):select([],{},'standard')
    def test_mode_specific_order(self):
        rows=[{'query_scene_id':str(i),'rank1_cosine':i,'nonlocal_rank1_cosine':-i} for i in range(101)]
        counts={r['query_scene_id']:{'n_buildings':10,'n_roads':9,'n_pois':1} for r in rows}
        self.assertEqual(select(rows,counts,'standard')[0]['query_scene_id'],'100')
        self.assertEqual(select(rows,counts,'nonlocal')[0]['query_scene_id'],'0')

if __name__=='__main__':unittest.main()
