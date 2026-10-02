import numpy as np
from s10_all_query import select
from s10_all_models import band_ranks,HEADER,MAGIC,pack_query,unpack_query

def test_exact_s10_boundary_self_and_ties():
    x=np.ones((64,2),dtype=np.float32)/np.sqrt(np.float32(2))
    c=np.column_stack((np.arange(64)*3000.,np.zeros(64)));c[1,0]=1999.999;c[2,0]=2000.;c[3,0]=2000.001
    ids=[f's{i:03d}' for i in range(64)]
    out=select(x,c,ids,0)
    assert out['standard']['candidate_count']==63
    assert out['nonlocal']['candidate_count']==62
    assert out['standard']['bands']['most'][0][1]==2
    assert out['nonlocal']['bands']['most'][0][1]==3
    assert out['nonlocal']['bands']['most'][0][3]==2000.
    assert [r[1] for r in out['nonlocal']['bands']['top']]==list(range(4,14))
    raw=HEADER.pack(MAGIC,1,1)+pack_query(out)
    assert unpack_query(raw,1)==out

def test_legacy_bands_variable_eligible_population():
    for n in [62,7001,8999]:
        b=band_ranks(n)
        assert b=={'most':[1],'top':list(range(2,12)),'middle':list(range((n-10)//2+1,(n-10)//2+11)),'bottom':list(range(n-9,n+1))}

def test_near_tie_not_quantized():
    x=np.ones((64,2),dtype=np.float32);x[2,0]=np.nextafter(np.float32(1),np.float32(2));x[0]=[1,0]
    c=np.column_stack((np.arange(64)*3000.,np.zeros(64)))
    assert select(x,c,[str(i) for i in range(64)],0)['nonlocal']['bands']['most'][0][1]==3
