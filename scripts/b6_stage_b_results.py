"""Post-training float64 aggregation/readback only; frozen training source unchanged.

The original float32 strided NumPy reduction drifted 3.7--4.1e-6 from the
production PyTorch metric. Cast already-computed per-query values to float64;
retain the original 2e-6 check. No inference, selection or training changes.
"""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import json
import numpy as np
import b6_formal_analysis as analysis
from b6_formal_training import ROOT, ARMS, checked_path, source_inventory, immutable_json, manifest_check
from b6_stage_b_preparation import read, sha256_file
from b6_postbank_adapter import digest

DESIGN='b6formal_e593d0bb2f2f6acd77056c76'


def reporting_contract(root):
    body={'purpose':'post_training_reporting_only','input_training_design':DESIGN,
        'training_contract_sha256':sha256_file(root/'contract.json'),
        'adapter_sha256':sha256_file(__file__),'aggregation':'float64_of_unchanged_float32_per_query_values',
        'readback_atol_unchanged':2e-6,'checkpoint_selection_changed':False,'training_source_changed':False}
    body['identity']='b6report_'+digest(body)[:24]
    return body


def install_reporting_adapter(contract):
    original_metrics=analysis.query_metrics
    original_write=analysis.immutable_json
    def metrics(*args,**kwargs):
        return original_metrics(*args,**kwargs).astype(np.float64)
    def publish(path,value):
        if Path(path).name in ('acceptance.json','results.json'):
            value={**value,'reporting_contract':contract}
        return original_write(path,value)
    analysis.query_metrics=metrics
    analysis.immutable_json=publish


def run():
    root=checked_path(ROOT/DESIGN);c=read(root/'contract.json')
    assert source_inventory()==c['sources'],'frozen scientific source inventory changed'
    for arm in ARMS:assert read(root/arm/'completion.json')['status']=='COMPLETE'
    report=reporting_contract(root)
    install_reporting_adapter(report)
    acceptance=analysis.summarize(root)
    assert read(acceptance)['reporting_contract']==report
    audit=root/'final_audit';audit.mkdir(exist_ok=True)
    immutable_json(audit/'reporting_contract.json',report)
    for arm in ARMS:
        out=root/arm;completion=read(out/'completion.json');authority=read(out/'authority.json')
        events=[json.loads(x) for x in (out/'events.jsonl').read_text().splitlines()]
        assert events[-1]['event']=='TRAINING_COMPLETED' and events[-1]['selected']==completion['selected']
        files=[out/'authority.json',out/'completion.json',out/'events.jsonl']
        files+=sorted(out.glob('boundary-*.json'))+sorted(out.glob('performance-*.json'))
        files+=sorted(out.glob('validation-*.pt'))+sorted(out.glob('epoch-*.pt'))
        receipt={'status':'PASS','authority':authority,'source_sha':completion['source_sha'],
            'selection':completion['selected'],'training_complete':True,'reporting_contract':report,
            'training_contract_sha256':sha256_file(root/'contract.json'),
            'runtime_preflight_sha256':sha256_file(root/'preflight.json'),
            'comparison_manifest_sha256':sha256_file(root/'comparison/manifest.json'),
            'files':[{'path':str(p.relative_to(root)),'sha256':sha256_file(p)} for p in files]}
        immutable_json(audit/f'{arm}-acceptance.json',receipt)
    immutable_json(audit/'manifest.json',{'files':[{'path':p.name,'sha256':sha256_file(p)} for p in sorted(audit.iterdir()) if p.name!='manifest.json']})
    manifest_check(root/'comparison');manifest_check(audit)
    return audit/'manifest.json'


if __name__=='__main__':print(run())
