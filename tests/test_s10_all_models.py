import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'python'))
import numpy as np
from s10_all_models import pack_query,unpack_query,HEADER,MAGIC,order_index
from s10_all_query import select
class Bands(unittest.TestCase):
 def test_binary_and_boundary(self):
  ids=[f'{j:03d}' for j in range(64)];X=np.full((64,4),.5,dtype=np.float32);C=np.column_stack([np.arange(64)*3000,np.zeros(64)]).astype(float);C[1,0]=1999;C[2,0]=2000
  data=select(X,C,ids,0);raw=HEADER.pack(MAGIC,1,1)+pack_query(data);self.assertEqual(unpack_query(raw,1),data);self.assertEqual(data['nonlocal']['bands']['most'][0][1],3);self.assertEqual(data['standard']['bands']['most'][0][1],2)
 def test_query_ties(self):
  r=order_index([.5,.8,.5,.8]);self.assertEqual(r['asc'],[1,3,2,4]);self.assertEqual(r['desc'],[2,4,1,3]);self.assertNotIn('torch',sys.modules)
if __name__=='__main__':unittest.main()
