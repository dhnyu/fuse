"""Display-only query eligibility and stable ordering fixtures."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_s10_nonempty_high import select

class NonemptyTests(unittest.TestCase):
    def test_query_only_nonempty_and_exact_tie(self):
        rows=[{'query_scene_id':f'q{i:03}','rank1_scene_id':'empty_gallery_candidate','rank1_cosine':1.,'nonlocal_rank1_cosine':1.} for i in reversed(range(105))]
        counts={r['query_scene_id']:{'n_buildings':0,'n_roads':int(r['query_scene_id']!='q000'),'n_pois':0} for r in rows}
        for mode in ('standard','nonlocal'):
            result=select(rows,counts,mode)
            self.assertEqual([r['query_scene_id'] for r in result],[f'q{i:03}' for i in range(1,101)])
            self.assertTrue(all(r['rank1_scene_id']=='empty_gallery_candidate' for r in result))
    def test_single_poi_is_eligible_and_mode_score_used(self):
        rows=[{'query_scene_id':f'q{i:03}','rank1_cosine':float(i),'nonlocal_rank1_cosine':float(-i)} for i in range(101)]
        counts={r['query_scene_id']:{'n_buildings':0,'n_roads':0,'n_pois':1} for r in rows}
        self.assertEqual(select(rows,counts,'standard')[0]['query_scene_id'],'q100')
        self.assertEqual(select(rows,counts,'nonlocal')[0]['query_scene_id'],'q000')

if __name__=='__main__':unittest.main()
