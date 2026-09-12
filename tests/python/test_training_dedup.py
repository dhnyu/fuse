from __future__ import annotations

import ast
import copy
import json
import runpy
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from artifact_protocol import canonical_json_bytes, canonical_sha256
from checkpoint_resolution import make_acceptance_eligibility
from training_controller import (AcceptedConfiguration, TrainingControllerError,
    acceptance_domain, accepted_scientific_configurations, build_training_authority,
    is_accepted_duplicate, training_run_id, validate_startup)
from test_training_controller import PARENTS


def authority(runtime='a' * 64, config='main', digest='c' * 64, phase='OFAT'):
    return build_training_authority(configuration_id=config, configuration_hash=digest,
        scientific_implementation_hash=runtime, root_seed=17, parents=PARENTS,
        phase=phase, model_id='FM')


def record(a):
    s = a['content']['scientific']
    return AcceptedConfiguration(acceptance_domain(a), s['configuration_id'],
        s['configuration_hash'], a['identity'], training_run_id(a), 'acceptance', 'checkpoint')


@pytest.mark.parametrize('phase,config', [('OFAT', 'main'), ('COMPARISON', 'cmp_FM')])
def test_runtime_generation_scope_and_both_collision_keys(phase, config):
    old = authority(phase=phase, config=config)
    accepted = (record(old),)
    assert is_accepted_duplicate(old, accepted)
    assert is_accepted_duplicate(authority(phase=phase, config=config, digest='d'*64), accepted)
    assert is_accepted_duplicate(authority(phase=phase, config='cmp_other'), accepted)
    assert not is_accepted_duplicate(authority(runtime='b'*64, phase=phase, config=config), accepted)


@pytest.fixture(scope='module')
def production():
    c = yaml.safe_load((ROOT / 'config/training_controller.yml').read_text())
    canonical = Path(c['roots']['immutable_publication']) / 'canonical'
    snapshot = Path(c['roots']['eligibility_snapshot'])
    records = accepted_scientific_configurations(canonical, snapshot, c['roots']['writable_runs'])
    return c, canonical, snapshot, records


def test_current_evidence_all_eleven_and_startup(production):
    c, canonical, snapshot, records = production
    assert len(records) == 11
    assert {r.domain[1] for r in records} == {'0479d8ae41fb22a4c3c2f82360fa2d12cd0f59fd73d8a50ef0868d2eff1cf66d'}
    from training_campaign import ofat_authorities, authority_parents, current_lineage
    p = json.loads(Path(c['roots']['experiment_plan']).read_text())
    cache = Path(c['roots']['production_cache']) / 's09cache_dc4e9e271e40ffe8ae17967c'
    accepted = json.loads((cache / 'acceptance.json').read_text())
    parents = authority_parents(current_lineage(p,c), accepted)
    authorities = ofat_authorities(p, yaml.safe_load((ROOT/'config/training.yml').read_text()),
        yaml.safe_load((ROOT/'config/model_inputs.yml').read_text()), parents,
        'baf19aa078973c19e19ed55c8ea6ee2f733db9d9b94a33b0c8e03e74fc695c9a')
    assert authorities[0]['identity'] == 's09auth_4d2bb6e9c91c5e716897a7c9'
    from training_runtime_provenance import runtime_implementation_provenance
    current = ofat_authorities(p, yaml.safe_load((ROOT/'config/training.yml').read_text()),
        yaml.safe_load((ROOT/'config/model_inputs.yml').read_text()), parents,
        runtime_implementation_provenance(ROOT)['implementation_sha256'])
    assert len(current) == 11
    resolved = copy.deepcopy(c)
    resolved['parents'] = {k:v for k,v in parents.items() if k != 'scientific_revision_token'}
    resolved['roots'].update(production_cache=str(cache), production_cache_acceptance=str(cache/'acceptance.json'))
    from artifact_protocol import sha256_file
    resolved['production_cache_manifest_sha256'] = sha256_file(cache/'production_cache_manifest.json')
    inputs = runpy.run_path(str(ROOT/'scripts/training_controller.py'))['startup_inputs']
    for a in authorities + current:
        assert not is_accepted_duplicate(a, records)
        # Only local test worktree dirtiness is waived; production keeps require_clean=True.
        assert validate_startup(a, inputs(resolved,a), accepted_configurations=records,
                                require_clean=False, cuda_devices=2)['status'] == 'PASS'
        with pytest.raises(TrainingControllerError, match='ALREADY_ACCEPTED'):
            validate_startup(a, inputs(resolved,a), accepted_configurations=(record(a),),
                             require_clean=False, cuda_devices=2)


@pytest.fixture
def copied_evidence(tmp_path, production):
    c, canonical, snapshot, _ = production
    entry = next(e for e in json.loads(snapshot.read_text())['entries']
                 if e['authority_id'] == 's09auth_6446cd16ebc90b8d29a07d8a')
    source = canonical / 'acceptances' / entry['acceptance_id']
    acceptance = json.loads((source/'acceptance.json').read_text())
    bundle = tmp_path/'bundles'/acceptance['run_bundle_id']
    shutil.copytree(source, tmp_path/'acceptances'/entry['acceptance_id'])
    shutil.copytree(canonical/'bundles'/acceptance['run_bundle_id'], bundle)
    for path in tmp_path.rglob('*'):
        if path.is_file(): path.chmod(0o600)
    eligibility = tmp_path/'eligibility.json'
    eligibility.write_bytes(canonical_json_bytes(make_acceptance_eligibility([entry], namespace='current-training')))
    return tmp_path, eligibility, c['roots']['writable_runs'], bundle, entry


@pytest.mark.parametrize('fault', ['missing_authority','authority_hash','runtime','plan','config',
                                    'snapshot_hash','extra_runtime','acceptance_hash','checkpoint_locator'])
def test_corrupt_evidence_fails_before_cross_runtime_filter(copied_evidence, fault):
    root, snapshot, writable, bundle, entry = copied_evidence
    authority_path = bundle/'authority/authority_manifest.json'
    if fault == 'missing_authority':
        authority_path.unlink()
    elif fault in {'authority_hash','runtime','plan','config'}:
        a = json.loads(authority_path.read_text())
        if fault == 'authority_hash': a['content_sha256'] = '0'*64
        if fault == 'runtime': a['content']['scientific']['scientific_implementation_hash'] = 'b'*64
        if fault == 'plan': a['content']['parents']['experiment_plan_id'] = 'wrong-plan'
        if fault == 'config': a['content']['scientific']['configuration_hash'] = 'b'*64
        authority_path.write_bytes(canonical_json_bytes(a))
    elif fault in {'snapshot_hash','extra_runtime'}:
        value = json.loads(snapshot.read_text())
        if fault == 'snapshot_hash': value['content_sha256'] = '0'*64
        else: value['entries'][0]['runtime_sha256'] = 'b'*64
        snapshot.write_bytes(canonical_json_bytes(value))
    elif fault == 'acceptance_hash':
        path = root/'acceptances'/entry['acceptance_id']/'acceptance.json'
        a=json.loads(path.read_text()); a['payload_sha256']='0'*64
        path.write_bytes(canonical_json_bytes(a))
    else:
        path=bundle/'checkpoints/checkpoint_inventory.json'
        a=json.loads(path.read_text()); a['checkpoints'][0]['payload_locator']['content_sha256']='0'*64
        path.write_bytes(canonical_json_bytes(a))
    with pytest.raises(Exception):
        accepted_scientific_configurations(root, snapshot, writable)


def test_missing_and_duplicate_snapshot_fails(copied_evidence):
    root, snapshot, writable, _, entry = copied_evidence
    value=json.loads(snapshot.read_text()); value['entries'].append(entry)
    pre={k:v for k,v in value.items() if k not in {'content_sha256','eligibility_id'}}
    h=canonical_sha256(pre); value.update(content_sha256=h,eligibility_id='p9elig_'+h[:24])
    snapshot.write_bytes(canonical_json_bytes(value))
    with pytest.raises(Exception): accepted_scientific_configurations(root,snapshot,writable)
    with pytest.raises(Exception): accepted_scientific_configurations(root,root/'missing.json',writable)


def test_preflight_and_run_use_one_canonical_startup():
    tree=ast.parse((ROOT/'scripts/training_controller.py').read_text())
    for name in ('main','run'):
        f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        calls=[n.func.id for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        assert calls.count('validate_formal_startup') == 1
        assert 'accepted_scientific_configurations' not in calls
        assert 'validate_startup' not in calls


def test_controller_registered_runtime_not_prepared_payload():
    from training_runtime_provenance import runtime_source_paths
    assert ROOT/'python/training_controller.py' in runtime_source_paths(ROOT)
    source=(ROOT/'R/training_targets.R').read_text().split('s09_runtime_source_files')[0]
    assert 'python/training_controller.py' not in source
