"""Frozen accepted vectors expose strided float32 aggregate drift; no retraining."""
from pathlib import Path
import importlib.util
import numpy as np
import torch
from b6_formal_analysis import query_metrics
from b6_formal_training import ROOT, ARMS, read, source_inventory


def test_float64_readback_preserves_individual_query_metrics():
    root=ROOT/'b6formal_e593d0bb2f2f6acd77056c76'
    assert source_inventory()==read(root/'contract.json')['sources']
    for arm in ARMS:
        m=read(root/arm/'completion.json')['selected']
        vectors=torch.load(root/arm/f"validation-{m['completed_epoch']:03d}.pt",map_location='cpu',weights_only=False)['vectors']
        values=query_metrics(vectors)
        expected=np.array([m[k] for k in ['validation_retrieval_loss','mean_source_separation_margin','MRR','HIT@1','HIT@5','HIT@10']])
        wide=values.astype(np.float64)
        assert np.array_equal(wide.astype(np.float32),values)
        assert np.allclose(wide.mean(0),expected,atol=2e-6,rtol=0)
        assert np.max(abs(wide.mean(0)-expected))<6e-8
