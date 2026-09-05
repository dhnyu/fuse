"""Read-only reporting contracts; no training or inference tests."""
import ast
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from p9_p10_results_report import COMPARISON, MODELS, NA, ROOT, independent_selection, sha, validate_output


def candidate(epoch, loss, margin):
    return {'epoch':epoch,'validation_retrieval_loss':loss,'validation_margin':margin}


@pytest.mark.parametrize('rows,expected', [
    ([candidate(5,1.,.3),candidate(10,.9,.1)],10),
    ([candidate(5,1.,.3),candidate(10,1.00005,.4)],10),
    ([candidate(5,0.,.3),candidate(10,1e-4,.9)],5),
    ([candidate(5,0.,.3),candidate(10,0.,.3)],5),
    ([candidate(5,1.,.4),candidate(10,.99995,.3)],5),
])
def test_selection_strict_threshold_margin_and_epoch(rows,expected):
    assert independent_selection(rows)[0]['epoch']==expected


def test_margin_change_does_not_reset_patience():
    rows = [candidate(5,1.,.3),candidate(10,1.00005,.4),candidate(15,.9,.1)]
    assert [s['patience'] for s in independent_selection(rows)[1]]==[0,1,0]


def test_reader_does_not_execute_science():
    tree = ast.parse((ROOT/'python/p9_p10_results_report.py').read_text())
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not calls.intersection({'backward','step','forward','fit','predict','tar_make','cuda'})
    assert len(MODELS)==20 and len(COMPARISON)==8
    assert list(MODELS).count('cfg_d128')==1


@pytest.fixture(scope='module')
def output():
    path = os.environ.get('P9_P10_REPORT_DIR')
    if not path:
        pytest.skip('Set P9_P10_REPORT_DIR to a generated immutable summary for readback tests')
    return Path(path)


def test_generated_package(output):
    result = validate_output(output)
    assert result['primary_models']==20
    assert result['selection_agreements']==20
    assert result['p10_metric_rows']==8


def test_all_update_values_are_source_readbacks(output):
    import torch
    inventory = pd.read_parquet(output/'model_inventory.parquet')
    training = pd.read_parquet(output/'training_history.parquet')
    fields = {'total_loss':'training_total_loss','scene_loss':'training_scene_loss',
              'ip_loss':'training_ip_loss_raw','weighted_ip_loss':'training_ip_loss_weighted',
              'learning_rate':'learning_rate','gradient_norm':'gradient_norm'}
    for row in inventory.itertuples():
        assert sha(row.source_payload_path)==row.source_payload_sha256
        stored = torch.load(row.source_payload_path,map_location='cpu',weights_only=False)['training_trace']
        assert sha(row.selected_payload_path)==row.selected_payload_sha256
        selected = torch.load(row.selected_payload_path,map_location='cpu',weights_only=False)['training_trace']
        assert stored[:len(selected)]==selected
        reported = training[training.model_id==row.model_id].reset_index(drop=True)
        assert len(stored)==len(reported)
        for source,destination in fields.items():
            expected = pd.Series([t.get(source,float('nan')) for t in stored],dtype=float)
            pd.testing.assert_series_equal(expected,reported[destination],check_names=False)
            missing = expected.isna()
            assert reported.loc[missing,destination+'_status'].eq(NA).all()


def test_validation_and_p10_provenance(output):
    inventory = pd.read_parquet(output/'model_inventory.parquet').set_index('model_id')
    validation = pd.read_parquet(output/'validation_history.parquet')
    for model, frame in validation.groupby('model_id'):
        assert frame.source_payload_sha256.eq(inventory.loc[model,'source_payload_sha256']).all()
        assert frame.source_event_id.nunique()==len(frame)
    heldout = pd.read_parquet(output/'p10_heldout_summary.parquet')
    for row in heldout.itertuples():
        assert sha(row.source_artifact_path)==row.source_artifact_sha256
        evidence = json.loads(Path(row.source_artifact_path).read_text())
        actual = heldout[heldout.model_id==row.model_id].iloc[0]
        assert all(actual[k]==v for k,v in evidence['metrics'].items())
        assert actual.checkpoint_id==inventory.loc[row.model_id,'checkpoint_id']


def test_missing_metrics_not_reconstructed(output):
    coverage = pd.read_parquet(output/'metric_availability.parquet').set_index('model_id')
    assert coverage.loc['cfg_d64','validation_mrr']=='NOT_RECORDED'
    assert coverage.validation_mrr.eq('AVAILABLE').sum()==19
    assert coverage.p10_metrics.eq('NOT_EVALUATED').sum()==12
    assert coverage.training_ip_loss_raw.eq('NOT_RECORDED').sum()==6
    training = pd.read_parquet(output/'training_history.parquet')
    ip0 = training[training.model_id=='cfg_ip0']
    assert ip0.training_ip_loss_raw.gt(0).all()
    assert ip0.training_ip_loss_weighted.eq(0).all()


def test_master_table_values_and_scope(output):
    manifest = json.loads((output/'manifest.json').read_text())
    text = (ROOT/manifest['report_path']).read_text()
    assert text.count('P11')==1
    assert all(value==0 for value in manifest['scientific_execution_counts'].values())
    master = text.split('## 5. Twenty-Model Master Summary')[1].split('## 6.')[0]
    rows = [line for line in master.splitlines() if line.startswith('| ')][2:]
    assert len(rows)==20
    assert [row.split('|')[1].strip() for row in rows]==list(MODELS)
