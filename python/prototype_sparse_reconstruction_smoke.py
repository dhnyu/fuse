#!/usr/bin/env python3
"""Regression fixture for sparse rank-local reconstruction aggregation."""

from __future__ import annotations
import hashlib,json,os,socket,tempfile
from pathlib import Path
from typing import Any
import torch,torch.distributed as dist,torch.multiprocessing as mp
from torch import nn
from torch.nn.parallel import DistributedDataParallel
from run_prototype_training import state_digest

LIMITS={"atol":1e-7,"rtol":1e-5,"relative_l2_max":1e-6,"cosine_min":0.9999999}
CASES={
 "rank0_empty_rank1_nonempty":([[0,2,1,4],[3,2,1,4]],[[0,1,0],[2,1,0]]),
 "rank0_nonempty_rank1_empty":([[3,2,1,4],[0,2,1,4]],[[2,1,0],[0,1,0]]),
 "both_empty":([[0,2,1,4],[0,2,1,4]],[[0,1,0],[0,1,0]]),
 "unequal_nonempty":([[1,2,1,4],[7,3,1,2]],[[1,0,2],[5,3,0]]),
 "one_local_microbatch_empty":([[0,2,1,4],[4,2,1,4]],[[0,0,1],[4,2,1]]),
 "partial_fields_empty":([[2,2,0,4],[2,2,0,4]],[[0,2,0],[3,0,0]]),
}

class SparseObjective(nn.Module):
 def __init__(self)->None:
  super().__init__();self.weight=nn.Parameter(torch.tensor([.2,-.3,.4,-.5],dtype=torch.float32))
 def forward(self,counts:torch.Tensor)->torch.Tensor:
  return self.weight.square()*counts.to(self.weight.dtype)+self.weight*0.0

def port()->int:
 with socket.socket() as s:s.bind(("127.0.0.1",0));return int(s.getsockname()[1])

def metrics(expected:torch.Tensor,observed:torch.Tensor)->dict[str,Any]:
 diff=(expected-observed).double();den=float(torch.linalg.vector_norm(expected.double()));obs=float(torch.linalg.vector_norm(observed.double()))
 rel=float(torch.linalg.vector_norm(diff))/den if den else (0.0 if obs==0 else float("inf"))
 cosine=float(torch.dot(expected.double(),observed.double())/(den*obs)) if den and obs else 1.0
 return {"maximum_absolute_difference":float(diff.abs().max()),"relative_l2":rel,"cosine":cosine,
  "allclose":bool(torch.allclose(expected,observed,atol=LIMITS["atol"],rtol=LIMITS["rtol"])),
  "pass":bool(torch.allclose(expected,observed,atol=LIMITS["atol"],rtol=LIMITS["rtol"]) and rel<=LIMITS["relative_l2_max"] and cosine>=LIMITS["cosine_min"])}

def worker(rank:int,master_port:int,out:str)->None:
 os.environ.update(MASTER_ADDR="127.0.0.1",MASTER_PORT=str(master_port),RANK=str(rank),WORLD_SIZE="2",LOCAL_RANK=str(rank))
 torch.cuda.set_device(rank);torch.use_deterministic_algorithms(True);dist.init_process_group("nccl",rank=rank,world_size=2,device_id=torch.device(f"cuda:{rank}"))
 results={}
 for name,(modality_counts,field_counts) in CASES.items():
  torch.manual_seed(7);model=SparseObjective().to(rank);ddp=DistributedDataParallel(model,device_ids=[rank],broadcast_buffers=False)
  local=torch.tensor(modality_counts[rank],device=rank,dtype=torch.int64);global_count=local.clone();dist.all_reduce(global_count)
  local_sum=ddp(local);active=global_count>0;m_active=int(active.sum())
  loss=(local_sum[active]/global_count[active]).sum()/m_active if m_active else local_sum.sum()
  (loss*2.0).backward();gradient=model.weight.grad.detach().cpu()
  expected=torch.tensor([2*.2,-2*.3,2*.4,-2*.5],dtype=torch.float32)/max(1,m_active);expected[~active.cpu()]=0
  field_local=torch.tensor(field_counts[rank],device=rank,dtype=torch.int64);field_global=field_local.clone();dist.all_reduce(field_global)
  present=[parameter.grad is not None for parameter in model.parameters()];zero=[not bool(torch.count_nonzero(parameter.grad)) for parameter in model.parameters()]
  results[name]={"global_modality_counts":global_count.cpu().tolist(),"global_field_counts":field_global.cpu().tolist(),
   "active_modalities":m_active,"gradient":gradient,"gradient_metrics":metrics(expected,gradient),
   "gradient_present":all(present),"inactive_zero":all(bool(zero[0])==bool((~active).all()) for _ in [0]) if m_active in (0,4) else bool(torch.all(gradient[~active.cpu()]==0))}
  del ddp,model
 digest=state_digest(results);digests=[None,None];dist.all_gather_object(digests,digest)
 if rank==0:torch.save({"results":results,"rank_digests":digests,"digest":digest},out)
 dist.barrier();dist.destroy_process_group()

def main()->None:
 with tempfile.TemporaryDirectory(prefix="fuse-sparse-ddp-") as directory:
  runs=[]
  for repeat in range(2):
   out=str(Path(directory)/f"run-{repeat}.pt");mp.spawn(worker,args=(port(),out),nprocs=2,join=True);runs.append(torch.load(out,weights_only=False))
 passed=all(value["gradient_metrics"]["pass"] and value["gradient_present"] and value["inactive_zero"] for value in runs[0]["results"].values())
 passed=passed and len(set(runs[0]["rank_digests"]))==1 and runs[0]["digest"]==runs[1]["digest"]
 print(json.dumps({"status":"PASS" if passed else "BLOCKED","limits":LIMITS,"cases":runs[0]["results"],
  "rank_state_exact":len(set(runs[0]["rank_digests"]))==1,"ddp_repeat_exact":runs[0]["digest"]==runs[1]["digest"],
  "digest":runs[0]["digest"]},default=lambda x:x.tolist() if isinstance(x,torch.Tensor) else x,sort_keys=True))

if __name__=="__main__":main()
