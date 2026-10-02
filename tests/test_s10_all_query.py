import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'python'))
import numpy as np
from s10_all_query import select
class Contract(unittest.TestCase):
 def test_tie_boundary_and_bands(self):
  ids=[f'scene_{i:03d}' for i in range(64)];X=np.full((64,4),.5,dtype=np.float32);C=np.column_stack([np.arange(64)*3000,np.zeros(64)]).astype(float);C[1,0]=1999;C[2,0]=2000
  r=select(X,C,ids,0);self.assertEqual(r['standard']['candidate_count'],63);self.assertEqual(r['standard']['bands']['most'][0][1],2);self.assertEqual(r['nonlocal']['candidate_count'],62);self.assertEqual(r['nonlocal']['bands']['most'][0][1],3);self.assertEqual(r['nonlocal']['bands']['most'][0][3],2000)
  for mode,d in r.items():
   self.assertEqual(sum(map(len,d['bands'].values())),31);self.assertEqual(d['bands']['middle'][0][0],(d['candidate_count']-10)//2+1);self.assertEqual(d['bands']['bottom'][-1][0],d['candidate_count']);self.assertTrue(all(z[1]!=1 for a in d['bands'].values() for z in a))
  self.assertEqual(select(X,C,ids,0),r);self.assertNotIn('torch',sys.modules)
if __name__=='__main__':unittest.main()
