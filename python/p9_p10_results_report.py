"""Read-only P9 v2/P10 consolidation; no model execution or authority publication.

Methodology: results/03-representation-analysis.typ (selection and retrieval)
and results/05-hyperparameter-study.typ (historical d64 OFAT reference).
"""
from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import torch
import yaml

from p9_v2_downstream import AcceptedCheckpointResolver, load_acceptance_eligibility

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('/mnt/hdd002/dhnyu/fusedata')
CANON = DATA / 'models/reduced/p9_v2/canonical'
P10 = DATA / 'models/reduced/p10/canonical/execution_attempts/p10exec_7fee193dac532190c79e02c6'
ELIG = CANON / 'eligibility/p9elig_250e0140d593f360f1368ef1.json'
INTER_ELIG = CANON / 'eligibility/p9elig_aa74178012b5636c2f20c9f2.json'
FINAL = CANON / 'final_model/p9fms_389a0ce89992eee507d7c846.json'
INTER = CANON / 'selected_fm/p9sfm_dca5569ef50bd9bfb1940032.json'
NA = 'NA_NOT_RECORDED'
MODELS = {
    'cfg_d48': 'cfg_d48', 'cfg_d64': 'cfg_main', 'cfg_d128': 'cfg_d128',
    'cfg_k2': 'cfg_k2', 'cfg_k4': 'cfg_k4', 'cfg_k16': 'cfg_k16',
    'cfg_intensity_05': 'cfg_intensity_05', 'cfg_intensity_20': 'cfg_intensity_20',
    'cfg_ema990': 'cfg_ema_990', 'cfg_ip0': 'cfg_ip_0',
    'cfg_lr2': 'cfg_lr_2', 'cfg_lr3': 'cfg_lr_3', 'cfg_lr10': 'cfg_lr_10',
    'A1': 'cmp_a1_geometric_core', 'A2': 'cmp_a2_semantic_enriched',
    'A3': 'cmp_a3_object_context_enriched', 'A4': 'cmp_a4_raster_complete_non_relational',
    'A5': 'cmp_a5_relation_type_agnostic', 'SSV': 'cmp_ssv_like', 'DS': 'cmp_ds_like',
}
COMPARISON = ['cfg_d128', 'A1', 'A2', 'A3', 'A4', 'A5', 'SSV', 'DS']
ARCH = {
    'cfg_d128': 'FM: four object modalities, raster branches, heterogeneous relations',
    'A1': 'Relative position + intrinsic geometry; no semantic/context/raster/relation branches',
    'A2': 'A1 + semantic attributes; no object context/raster/relations',
    'A3': 'A2 + object environmental context; no scene raster/relations',
    'A4': 'A3 + scene LC/DEM raster branches; no relational contextualization',
    'A5': 'FM edge support unchanged; one generic relation embedding replaces relation identity',
    'SSV': 'Controlled SSV-like: relative position + semantics; no geometry/context/raster/relations',
    'DS': 'Controlled DS-like: common 100x100, 26-channel raster; no entity/fusion/relation/IP modules',
}
TRAIN_FIELDS = {'learning_rate':'learning_rate', 'total_loss':'training_total_loss',
    'scene_loss':'training_scene_loss', 'ip_loss':'training_ip_loss_raw',
    'weighted_ip_loss':'training_ip_loss_weighted', 'gradient_norm':'gradient_norm',
    'queue_count':'queue_count', 'queue_pointer':'queue_pointer', 'wall_seconds':'update_wall_seconds'}
VAL_FIELDS = {'validation_retrieval_loss':'validation_retrieval_loss',
    'mean_source_separation_margin':'validation_margin', 'MRR':'validation_mrr',
    'HIT@1':'validation_hit1', 'HIT@5':'validation_hit5', 'HIT@10':'validation_hit10',
    'query_count':'validation_query_count', 'gallery_count':'validation_gallery_count'}


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Sources:
    def __init__(self):
        self.hashes = {}

    def bind(self, path, expected=None):
        path = Path(path).resolve()
        if str(path) not in self.hashes:
            self.hashes[str(path)] = sha(path)
        digest = self.hashes[str(path)]
        if expected is not None:
            assert digest == expected, f'Hash mismatch: {path}'
        return digest

    def read(self, path):
        self.bind(path)
        return json.loads(Path(path).read_text())

    def verify(self):
        for path, digest in self.hashes.items():
            assert sha(path) == digest, f'Source mutated: {path}'
        return {'status':'PASS', 'files_checked':len(self.hashes), 'changed_files':0}


def independent_selection(rows, tolerance=1e-4):
    """Independent chronological replay, including strict binary64 tolerance."""
    best = None
    patience = 0
    states = []
    tol = Decimal.from_float(tolerance)
    for row in rows:
        if best is None:
            replace, reset = True, True
        else:
            delta = Decimal.from_float(float(row['validation_retrieval_loss'])) - Decimal.from_float(float(best['validation_retrieval_loss']))
            reset = -delta >= tol
            if abs(delta) < tol:
                replace = (row['validation_margin'], -row['epoch']) > (best['validation_margin'], -best['epoch'])
            else:
                replace = delta < 0
        patience = 0 if reset else patience + 1
        if replace:
            best = row
        states.append({'epoch':row['epoch'], 'patience':patience, 'best_epoch':best['epoch']})
    return best, states


def locate(locator, roots, sources):
    loc = locator['location']
    path = roots[loc['namespace']] / loc['relative_path']
    sources.bind(path, locator['content_sha256'])
    assert path.stat().st_size == locator['byte_size']
    return path


def collect():
    sources = Sources()
    contract_path = ROOT / 'config/p10_evaluation.yml'
    sources.bind(contract_path)
    contract = yaml.safe_load(contract_path.read_text())
    matrix = sources.read(contract['inputs']['hyperparameter_matrix'])
    matrix_rows = {r['configuration_id']:r for r in matrix['rows']}
    alias = sources.read(ROOT / 'config/dissertation_authority_refresh.json')['historical_reference']
    assert alias['configuration_id'] == 'cfg_main' and alias['reporting_alias'] == 'cfg_d64'
    sources.read(contract['inputs']['comparison_matrix'])
    sources.read(contract['inputs']['p9b_status'])
    sources.read(DATA / 'runtime/p9_a_campaigns/20260901_1450/campaign_status.json')
    final, interaction = sources.read(FINAL), sources.read(INTER)
    eligibility = load_acceptance_eligibility(ELIG)
    inter_eligibility = load_acceptance_eligibility(INTER_ELIG)
    sources.bind(ELIG); sources.bind(INTER_ELIG)
    by_config, roots = {}, {'p9-v1-history': DATA / 'models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029'}
    entries = {e['acceptance_id']:e for e in eligibility['entries']}
    for item in interaction['results'].values():
        entry = next(e for e in inter_eligibility['entries'] if e['acceptance_id'] == item['acceptance_id'])
        entries[entry['acceptance_id']] = entry
    for aid, entry in entries.items():
        assert entry['eligibility'] == 'ELIGIBLE'
        acceptance = sources.read(CANON / 'acceptances' / aid / 'acceptance.json')
        bundle = CANON / 'bundles' / acceptance['run_bundle_id']
        cfg = sources.read(bundle / 'config/scientific_configuration.json')['content']
        cid = cfg['configuration_id']
        assert cid not in by_config, f'Ambiguous configuration {cid}'
        by_config[cid] = (acceptance, bundle, cfg)
        if cid != 'cfg_main':
            handoff = sources.read(DATA / 'runtime/p9_v2_training_lifecycle' / acceptance['authority_id'] / 'bundle.json')
            assert handoff['bundle_id'] == acceptance['run_bundle_id']
            roots[handoff['checkpoint_namespace']] = Path(handoff['checkpoint_root'])
    assert set(by_config) == set(MODELS.values()) | set(interaction['results'])
    resolver = AcceptedCheckpointResolver(CANON/'acceptances', CANON/'bundles', roots, eligibility)
    inter_resolver = dataclasses.replace(resolver, eligibility=inter_eligibility)
    inventory, training, validation, secondary_training, secondary_validation, secondary = [], [], [], [], [], []
    for label, cid in {**MODELS, **{k:k for k in interaction['results']}}.items():
        acceptance, bundle, cfg = by_config[cid]
        for path in bundle.rglob('*'):
            if path.is_file(): sources.bind(path)
        for path in (CANON/'acceptances'/acceptance['acceptance_id']).rglob('*'):
            if path.is_file(): sources.bind(path)
        checkpoint_inventory = sources.read(bundle/'checkpoints/checkpoint_inventory.json')['checkpoints']
        for ck in checkpoint_inventory:
            locate(ck['payload_locator'], roots, sources)
            locate(ck['manifest_locator'], roots, sources)
        resolved = (resolver if label in MODELS else inter_resolver).resolve_accepted_checkpoint(acceptance['acceptance_id'])
        assert resolved.checkpoint_id == acceptance['checkpoint_id']
        events = [json.loads(line) for path in sorted((bundle/'ledger/segments').glob('*.jsonl')) for line in path.read_text().splitlines()]
        boundary = sources.read(bundle/'summary/stopping_boundary.json')['boundary']
        terminal = [c for c in checkpoint_inventory if (c['completed_epoch'], c['optimizer_update']) == (boundary['completed_epoch'], boundary['optimizer_update'])]
        assert len(terminal) == 1, f'Unresolved terminal boundary {cid}'
        terminal = terminal[0]
        payload = locate(terminal['payload_locator'], roots, sources)
        # CPU deserialization of trusted, hash-validated accepted bytes; no model construction.
        state = torch.load(payload, map_location='cpu', weights_only=False)
        trace, vtrace = state['training_trace'], state['validation_trace']
        assert len(trace) == boundary['optimizer_update'] and len(vtrace) == len(checkpoint_inventory)
        science = cfg.get('scientific', matrix_rows.get(cid, {}).get('scientific'))
        assert science is not None
        if cid in matrix_rows and cid != 'cfg_main': assert science == matrix_rows[cid]['scientific']
        role = 'P9-A selected FM' if label == 'cfg_d128' else ('P9-A OFAT' if label in list(MODELS)[:13] else 'P9-B comparison' if label in MODELS else 'Secondary interaction diagnostic')
        common = {'model_id':label, 'configuration_id':cid, 'model_role':role,
                  'source_artifact_id':resolved.run_bundle_id, 'source_payload_path':str(payload),
                  'source_payload_sha256':sources.bind(payload)}
        vals = []
        for v, ck in zip(vtrace, checkpoint_inventory, strict=True):
            epoch = v.get('completed_epoch', v.get('epoch'))
            assert epoch == ck['completed_epoch']
            assert v['validation_retrieval_loss'] == ck['validation_retrieval_loss']
            assert v['mean_source_separation_margin'] == ck['mean_source_separation_margin']
            vevent = next(e for e in events if e['event_id'] == ck['event_id'])
            row = {**common, 'epoch':epoch, 'update':ck['optimizer_update'],
                **{dest:v.get(src) for src,dest in VAL_FIELDS.items()}, 'checkpoint_id':ck['checkpoint_id'],
                'selected_checkpoint':ck['checkpoint_id']==resolved.checkpoint_id,
                'terminal_checkpoint':ck['checkpoint_id']==terminal['checkpoint_id'],
                'source_event_id':ck['event_id'], 'source_event_hash':vevent['event_hash'],
                'recorded_at':vevent['occurred_at'], 'source_record_index':len(vals)}
            vals.append(row)
        best, replay = independent_selection(vals)
        assert best['checkpoint_id'] == resolved.checkpoint_id, f'Selection mismatch {cid}'
        assert best['validation_retrieval_loss'] == resolved.validation_retrieval_loss
        assert best['validation_margin'] == resolved.mean_source_separation_margin
        assert [v['epoch'] for v in vals] == list(range(5, boundary['completed_epoch']+1, 5))
        early = [e['payload'] for e in events if e['event_type']=='EARLY_STOPPING_UPDATED']
        assert len(early) == len(vals)
        for v, step, recorded in zip(vals, replay, early, strict=True):
            assert step['patience'] == recorded['events_without_improvement']
            v.update({'events_without_improvement':step['patience'], 'early_stopping_trigger':step['patience']>=4})
        train_rows = []
        by_update = {v['update']:v for v in vals}
        for i, t in enumerate(trace):
            assert t['global_update'] == i+1
            assert t['epoch'] == i//76+1
            v = by_update.get(i+1)
            train_rows.append({**common, 'epoch':t['epoch'], 'update':t['global_update'],
                'batch_index':t['batch_index'], 'lambda_ip':science['lambda_ip'],
                **{dest:t.get(src) for src,dest in TRAIN_FIELDS.items()},
                **{dest:(v[dest] if v else None) for dest in VAL_FIELDS.values()},
                'validation_record_status':'RECORDED' if v else 'NOT_A_VALIDATION_INTERVAL',
                'checkpoint_id':v['checkpoint_id'] if v else 'N/A_NO_CHECKPOINT',
                'selected_checkpoint':bool(v and v['selected_checkpoint']),
                'selected_epoch':t['epoch']==best['epoch'],
                'batch_identity_digest':t.get('batch_identity_digest', NA),
                'source_record_index':i})
        tr = pd.DataFrame(train_rows)
        numeric = list(TRAIN_FIELDS.values())
        selected_means = tr.loc[tr.epoch == best['epoch'], numeric].astype(float).mean().to_dict()
        terminal_means = tr.loc[tr.epoch == boundary['completed_epoch'], numeric].astype(float).mean().to_dict()
        started = next(e for e in events if e['event_type']=='RUN_STARTED')
        completed = next(e for e in events if e['event_type']=='TRAINING_COMPLETED')
        imported = any(e.get('legacy_import') for e in events)
        duration = None if imported else (datetime.fromisoformat(completed['occurred_at'])-datetime.fromisoformat(started['occurred_at'])).total_seconds()
        row = {**common, 'p9_authority_id':resolved.authority_id, 'run_id':events[0]['run_id'],
            'source_run_id':terminal['source_run_id'], 'run_bundle_id':resolved.run_bundle_id,
            'p9_acceptance_id':resolved.acceptance_id, 'checkpoint_id':resolved.checkpoint_id,
            'selected_payload_path':str(locate(resolved.payload_locator, roots, sources)),
            'selected_payload_sha256':resolved.payload_sha256,
            'selected_epoch':best['epoch'], 'selected_update':best['update'],
            'stop_epoch':boundary['completed_epoch'], 'stop_update':boundary['optimizer_update'],
            'stop_reason':boundary['reason'], 'terminal_checkpoint_id':terminal['checkpoint_id'],
            'p10_evaluated':label in COMPARISON, 'p10_status':'EVALUATED' if label in COMPARISON else 'P10_NOT_EVALUATED',
            'effective_config_json':packed(science), **science,
            'architecture':ARCH.get(label, f"FM architecture; OFAT {matrix_rows.get(cid, {}).get('changed_factor', 'joint factors')}"),
            'changed_factor':matrix_rows.get(cid, {}).get('changed_factor', 'architecture' if label in MODELS else 'joint factors'),
            'transformation_contract_json':packed(cfg.get('transformation_contract', {})),
            'validation_count':len(vals), 'training_update_count':len(trace),
            'training_start':NA if imported else started['occurred_at'],
            'training_end':NA if imported else completed['occurred_at'],
            'training_duration_seconds':duration, 'duration_semantics':'NA_IMPORTED_EVENT_TIMES_ARE_NOT_TRAINING_TIMES' if imported else 'RUN_STARTED_TO_TRAINING_COMPLETED_INCLUDES_VALIDATION',
            'recorded_update_wall_seconds_sum':float(tr.update_wall_seconds.sum()) if tr.update_wall_seconds.notna().all() else None,
            'early_stopping':replay[-1]['patience']>=4,
            **{f'selected_{k}':v for k,v in selected_means.items()},
            **{f'terminal_{k}':v for k,v in terminal_means.items()},
            **{f'selected_{k}':best[k] for k in VAL_FIELDS.values()},
            **{f'terminal_{k}':vals[-1][k] for k in VAL_FIELDS.values()},
            'recomputed_selected_epoch':best['epoch'], 'selection_agreement':'PASS',
            'minimum_recorded_validation_loss':min(v['validation_retrieval_loss'] for v in vals),
            'p10_result_path':str(P10/'evaluations'/cid/'evaluation.json') if label in COMPARISON else 'P10_NOT_EVALUATED'}
        if label in MODELS:
            inventory.append(row); training.extend(train_rows); validation.extend(vals)
        else:
            secondary.append(row); secondary_training.extend(train_rows); secondary_validation.extend(vals)
        print(f'RESOLVED {label}: {len(trace)} updates, {len(vals)} validation records, selected {best["epoch"]}', flush=True)
        del state, trace, tr
    p10acc = sources.read(P10/'commit/evaluation_acceptance.json')
    assert p10acc['acceptance_id']=='p10acc_6e5071beee7616750dec7907' and p10acc['status']=='PASS'
    final_comparison = sources.read(P10/'final_comparison.json')
    assert final_comparison['models']==p10acc['comparison']
    evaluations, heldout = [], []
    for label in COMPARISON:
        inv = next(r for r in inventory if r['model_id']==label)
        path = P10/'evaluations'/inv['configuration_id']/'evaluation.json'
        result = sources.read(path)
        assert result['checkpoint_id']==inv['checkpoint_id'] and result['acceptance_id']==inv['p9_acceptance_id']
        accepted_metrics = next(r for r in p10acc['comparison'] if r['configuration_id']==inv['configuration_id'])
        assert result['metrics']=={k:v for k,v in accepted_metrics.items() if k!='configuration_id'}
        evaluations.append(result)
        heldout.append({'model_id':label, 'configuration_id':inv['configuration_id'],
            'checkpoint_id':inv['checkpoint_id'], 'p9_acceptance_id':inv['p9_acceptance_id'],
            'p10_acceptance_id':p10acc['acceptance_id'], 'p10_authority_id':p10acc['authority_id'],
            'source_artifact_path':str(path), 'source_artifact_sha256':sources.bind(path),
            **result['metrics']})
    # Bind the accepted model-result list, not an unaccepted historical execution path.
    from p9_v2_canonical import canonical_sha256
    assert canonical_sha256(evaluations)==p10acc['model_evaluation_sha256']
    for path in P10.rglob('*'):
        if path.is_file(): sources.bind(path)
    for path in (ROOT/'config').glob('p9*'):
        if path.is_file(): sources.bind(path)
    for path in [ROOT/'config/p7_deterministic_training.yml', ROOT/'python/p9_v2_training_worker.py', ROOT/'scripts/p9_formal_training.py', ROOT/'python/p9_model_families.py', ROOT/'python/p9_v2_finalization.py']:
        sources.bind(path)
    dissertation = ROOT.parent/'dhnyu-masters-dissertation/template'
    for relative in ['sections/chapters/results/01-experimental-setup.typ', 'sections/chapters/results/03-representation-analysis.typ', 'sections/chapters/results/05-hyperparameter-study.typ', 'sections/chapters/04-methodology-training.typ']:
        sources.bind(dissertation/relative)
    frames = {'model_inventory':pd.DataFrame(inventory), 'training_history':pd.DataFrame(training),
        'validation_history':pd.DataFrame(validation), 'interaction_diagnostics':pd.DataFrame(secondary),
        'interaction_training_history':pd.DataFrame(secondary_training), 'interaction_validation_history':pd.DataFrame(secondary_validation),
        'p10_heldout_summary':pd.DataFrame(heldout)}
    return frames, sources, {'final_decision':final, 'interaction_decision':interaction}


def enrich(frames, sources):
    """Attach recorded operational intervals without treating them as loss metrics."""
    for prefix in ['', 'interaction_']:
        inventory = frames['model_inventory' if not prefix else 'interaction_diagnostics']
        vals, training = frames[prefix+'validation_history'], frames[prefix+'training_history']
        for model_index, model in inventory.iterrows():
            bundle = CANON/'bundles'/model.run_bundle_id
            val_events = {e['event_id']:e for path in sorted((bundle/'ledger/segments').glob('*.jsonl'))
                          for e in [json.loads(line) for line in path.read_text().splitlines()]
                          if e['event_type']=='VALIDATION_CHECKPOINT_COMMITTED'}
            for idx,row in vals.loc[vals.model_id==model.model_id].iterrows():
                queue = val_events[row.source_event_id]['payload'].get('queue',{})
                for src,dest in [('count','queue_count'),('pointer','queue_pointer'),('state_sha256','queue_state_sha256')]:
                    vals.loc[idx,dest] = queue.get(src, None)
            if model.model_id == 'cfg_d64':
                provenance = sources.read(bundle/'provenance/source_inventory.json')['entries']
                expected = next(e['content_sha256'] for e in provenance if e['logical_path']=='attempt/attempt_state.json')
                path = Path(model.source_payload_path).parents[2]/'attempt_state.json'
                sources.bind(path,expected)
                terminal_state = sources.read(path)
                assert terminal_state['run_id']==model.source_run_id
                inventory.loc[model_index,'training_start'] = datetime.fromtimestamp(terminal_state['started_unix'],ZoneInfo('UTC')).isoformat()
                inventory.loc[model_index,'controller_terminal_time'] = datetime.fromtimestamp(terminal_state['failed_unix'],ZoneInfo('UTC')).isoformat()
                inventory.loc[model_index,'controller_elapsed_seconds'] = terminal_state['failed_unix']-terminal_state['started_unix']
                inventory.loc[model_index,'controller_terminal_state'] = terminal_state['state']
                inventory.loc[model_index,'controller_timing_source'] = str(path)
                continue
            diagnostic_dir = Path(model.source_payload_path).parents[2]/'staging/diagnostics'
            for idx, row in vals.loc[vals.model_id==model.model_id].iterrows():
                path = diagnostic_dir/f'boundary-{row.epoch:04d}.json'
                if not path.exists():
                    continue
                value = sources.read(path)
                assert value['checkpoint_id']==row.checkpoint_id and value['optimizer_update']==row['update']
                for field in ['update_wall_seconds', 'median_update_wall_seconds', 'p95_update_wall_seconds',
                              'throughput_scenes_per_second', 'validation_wall_seconds', 'checkpoint_commit_wall_seconds',
                              'peak_vram_bytes', 'peak_rank_rss_bytes', 'rank_wall_skew_seconds']:
                    target = 'boundary_epoch_training_wall_seconds' if field=='update_wall_seconds' else field
                    vals.loc[idx, target] = value.get(field, np.nan)
                vals.loc[idx, 'runtime_source_path'] = str(path)
                vals.loc[idx, 'runtime_source_sha256'] = sources.bind(path)
                vals.loc[idx, 'runtime_interval_epochs'] = 1
        # Stable numeric types plus explicit missing-value status; CSV uses NA_NOT_RECORDED.
        for frame in [training, vals]:
            for col in list(frame.columns):
                if col in TRAIN_FIELDS.values() or col in VAL_FIELDS.values():
                    frame[col] = pd.to_numeric(frame[col], errors='raise').astype(float)
                    frame[col+'_status'] = np.where(frame[col].notna(), 'AVAILABLE', NA)
        numeric = list(TRAIN_FIELDS.values())
        epoch = training.groupby(['model_id', 'epoch'], sort=False)[numeric].mean().reset_index()
        epoch['aggregation'] = 'arithmetic_mean_of_recorded_rank0_updates_in_epoch_no_smoothing'
        frames[prefix+'training_epoch_summary'] = epoch
    inv = frames['model_inventory']
    frames['selection_summary'] = inv.copy()
    frames['p9a_summary'] = inv[inv.model_id.isin(list(MODELS)[:13])].copy()
    p9b = inv.set_index('model_id').loc[COMPARISON].reset_index()
    fm = inv.loc[inv.model_id=='cfg_d128'].iloc[0]
    p9b['delta_validation_retrieval_loss_from_fm'] = p9b.selected_validation_retrieval_loss-fm.selected_validation_retrieval_loss
    p9b['delta_validation_margin_from_fm'] = p9b.selected_validation_margin-fm.selected_validation_margin
    frames['p9b_summary'] = p9b
    frames['selection_contract_validation'] = inv[['model_id','selected_epoch','selected_validation_retrieval_loss',
        'selected_validation_margin','recomputed_selected_epoch','selection_agreement']].copy()
    availability = []
    for model in MODELS:
        vals = frames['validation_history'].query('model_id == @model')
        tr = frames['training_history'].query('model_id == @model')
        row = {'model_id':model}
        for column in VAL_FIELDS.values():
            row[column] = 'AVAILABLE' if vals[column].notna().all() else 'NOT_RECORDED' if vals[column].isna().all() else 'PARTIALLY_RECORDED'
            row[column+'_recorded_count'] = int(vals[column].notna().sum())
        for column in ['training_ip_loss_raw','training_ip_loss_weighted']:
            row[column] = 'AVAILABLE' if tr[column].notna().all() else 'NOT_RECORDED' if tr[column].isna().all() else 'PARTIALLY_RECORDED'
        row['p10_metrics'] = 'AVAILABLE' if model in COMPARISON else 'NOT_EVALUATED'
        availability.append(row)
    frames['metric_availability'] = pd.DataFrame(availability)
    return frames


def validate_frames(frames):
    inv, tr, val, heldout = [frames[k] for k in ['model_inventory','training_history','validation_history','p10_heldout_summary']]
    assert inv.model_id.tolist()==list(MODELS) and len(inv)==20
    assert len(frames['p9a_summary'])==13
    assert len(inv[inv.model_role=='P9-B comparison'])==7
    assert frames['p9b_summary'].model_id.tolist()==COMPARISON
    assert heldout.model_id.tolist()==COMPARISON and len(heldout)==8
    assert inv.configuration_id.nunique()==20 and not tr.duplicated(['model_id','update']).any()
    assert not val.duplicated(['model_id','epoch']).any()
    assert set(frames['interaction_diagnostics'].model_id).isdisjoint(inv.model_id)
    assert heldout.gallery_count.eq(1600).all() and heldout.query_count.eq(3200).all()
    for _, row in inv.iterrows():
        t, v = tr[tr.model_id==row.model_id], val[val.model_id==row.model_id]
        assert len(t)==row.stop_update and len(v)==row.validation_count
        best, replay = independent_selection(v.to_dict('records'))
        assert best['epoch']==row.selected_epoch==row.recomputed_selected_epoch
        assert best['checkpoint_id']==row.checkpoint_id
        assert best['validation_retrieval_loss']==row.selected_validation_retrieval_loss
        assert best['validation_margin']==row.selected_validation_margin
        if row.early_stopping:
            assert replay[-1]['patience']==4 and v.early_stopping_trigger.sum()==1
        else:
            assert row.stop_epoch==200 and v.early_stopping_trigger.sum()==0
        assert t.selected_checkpoint.sum()==1 and v.selected_checkpoint.sum()==1
        assert t.source_payload_sha256.eq(row.source_payload_sha256).all()
        assert v.validation_query_count.eq(800).all() and v.validation_gallery_count.eq(400).all()
        # Check recorded IP arithmetic only where explicitly recorded. Never backfill missing IP.
        present = t.training_ip_loss_weighted.notna()
        assert np.allclose(t.loc[present,'training_total_loss'],
                           t.loc[present,'training_scene_loss']+t.loc[present,'training_ip_loss_weighted'], rtol=2e-7, atol=2e-6)
        both = present & t.training_ip_loss_raw.notna()
        assert np.allclose(t.loc[both,'training_ip_loss_weighted'], t.loc[both,'training_ip_loss_raw']*row.lambda_ip, rtol=2e-7, atol=2e-6)
        if row.lambda_ip==0:
            assert t.training_ip_loss_weighted.eq(0).all()
        if row.p10_evaluated:
            h = heldout[heldout.model_id==row.model_id].iloc[0]
            assert h.checkpoint_id==row.checkpoint_id and h.p9_acceptance_id==row.p9_acceptance_id
        else:
            assert row.p10_status=='P10_NOT_EVALUATED'
        expected = t.groupby('epoch')[list(TRAIN_FIELDS.values())].mean().reset_index()
        actual = frames['training_epoch_summary'].query('model_id == @row.model_id')[expected.columns].reset_index(drop=True)
        pd.testing.assert_frame_equal(expected, actual, check_dtype=False)
    assert not any('downstream' in k.lower() for k in frames)
    return {'status':'PASS', 'primary_models':20, 'p9a_models':13, 'p9b_variants':7,
        'comparison_models':8, 'training_history_rows':len(tr), 'validation_history_rows':len(val),
        'p10_metric_rows':len(heldout), 'secondary_models':2,
        'selection_agreements':20, 'duplicate_models':0, 'excluded_scope_rows':0,
        'p9_rank_trajectory_models':int(frames['metric_availability'].validation_mrr.eq('AVAILABLE').sum())}


def figures(frames, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure_rows = []
    metrics = [('A','training_total_loss','Training total loss'), ('B','training_scene_loss','Training scene loss'),
        ('C','training_ip_loss_raw','Training raw IP loss'), ('D','validation_retrieval_loss','P9 validation retrieval loss'),
        ('E','validation_margin','P9 validation margin'), ('F','validation_mrr','P9 validation MRR'),
        ('G','validation_hit1','P9 validation HIT@1 / HIT@5 / HIT@10')]
    inv = frames['model_inventory'].set_index('model_id')
    for group, models in [('p9a',list(MODELS)[:13]), ('p9b_fm',COMPARISON)]:
        for letter, metric, title in metrics:
            nrows = (len(models)+3)//4
            fig, axes = plt.subplots(nrows,4,figsize=(17,3*nrows),squeeze=False)
            for ax, model in zip(axes.flat, models):
                training = metric.startswith('training_')
                frame = frames['training_history' if training else 'validation_history']
                data = frame[frame.model_id==model]
                columns = ['validation_hit1','validation_hit5','validation_hit10'] if letter=='G' else [metric]
                for j,column in enumerate(columns):
                    valid = data[column].notna()
                    x = data.loc[valid,'epoch']-1+(data.loc[valid,'batch_index']+1)/76 if training else data.loc[valid,'epoch']
                    ax.scatter(x,data.loc[valid,column],s=1 if training else 10,alpha=.35 if training else .9,
                               color=['#087e8b','#d1495b','#38823c'][j],label=column.replace('validation_',''))
                    selected = data[data.selected_checkpoint & data[column].notna()]
                    if len(selected):
                        ax.scatter(selected.epoch,selected[column],s=65,marker='*',color='#ba352d',zorder=5)
                    figure_rows.append({'figure':f'{group}_{letter}.png','model_id':model,'metric':column,
                                        'observations':int(valid.sum()),'selected_marker_count':len(selected)})
                if data[columns].isna().all().all():
                    ax.text(.5,.5,'NA_NOT_RECORDED',transform=ax.transAxes,ha='center',fontsize=9)
                    ax.set_xlim(0,inv.loc[model,'stop_epoch'])
                    ax.set_yticks([])
                ax.axvline(inv.loc[model,'selected_epoch'],color='#ba352d',lw=.7,ls=':')
                ax.set_title(model,fontsize=10); ax.set_xlabel('Epoch'); ax.grid(alpha=.18)
                if letter=='G' and model==models[0]: ax.legend(fontsize=7)
            for ax in list(axes.flat)[len(models):]: ax.set_visible(False)
            fig.suptitle(f'{group.upper()}: {title}\nObserved points only; red star = selected checkpoint update, dotted line = selected epoch',fontsize=12)
            fig.tight_layout(rect=(0,0,1,.94))
            fig.savefig(out/f'{group}_{letter}.png',dpi=115,metadata={'Software':'Fuse read-only results report'})
            plt.close(fig)
    frames['figure_inputs'] = pd.DataFrame(figure_rows)


def fmt(value):
    if value is None or (isinstance(value,(float,np.floating)) and np.isnan(value)): return NA
    if isinstance(value,(float,np.floating)): return f'{value:.9f}'
    return str(value).replace('|','/').replace('\n',' ')


def mdtable(frame, columns):
    return '\n'.join(['| '+' | '.join(columns.values())+' |',
        '| '+' | '.join(['---']*len(columns))+' |']+
        ['| '+' | '.join(fmt(row[key]) for key in columns)+' |' for _,row in frame.iterrows()])


def render_report(frames, metadata, receipt, report_id, artifact, timestamp, commit):
    inv, tr, val, h = [frames[k] for k in ['model_inventory','training_history','validation_history','p10_heldout_summary']]
    indexed = inv.set_index('model_id')
    basic = {'model_id':'Model','selected_epoch':'Selected epoch','stop_epoch':'Stop epoch',
             'selected_validation_retrieval_loss':'P9 validation loss','selected_validation_margin':'P9 validation margin'}
    master = {'model_id':'Model','model_role':'Role','architecture':'Changed factor / architecture','d':'d',
        'effective_k':'K','intensity':'Intensity','ema':'EMA','lambda_ip':'lambda_IP','peak_learning_rate':'Peak LR',
        'selected_epoch':'Selected epoch','stop_epoch':'Stop epoch','selected_training_total_loss':'Train total (epoch mean)',
        'selected_training_scene_loss':'Train scene (epoch mean)','selected_training_ip_loss_raw':'Raw IP (epoch mean)',
        'selected_training_ip_loss_weighted':'Weighted IP (epoch mean)','selected_validation_retrieval_loss':'P9 val loss',
        'selected_validation_margin':'P9 margin','selected_validation_mrr':'P9 MRR','selected_validation_hit1':'P9 HIT1',
        'selected_validation_hit5':'P9 HIT5','selected_validation_hit10':'P9 HIT10', 'checkpoint_id':'Checkpoint',
        'p9_acceptance_id':'P9 acceptance','p10_status':'P10 evaluated?'}
    lines = [f'# P9-P10 Comprehensive Model Results\n\n`P9_P10_COMPREHENSIVE_MODEL_RESULTS_REPORT_PASS`',
        f'Created: {timestamp} Asia/Seoul. Input Fuse: `reduced@{commit}`. Report artifact: `{report_id}`.',
        '## 1. Purpose And Scope',
        'Read-only consolidation of exactly **20 primary configurations**: 13 P9-A observations and seven P9-B variants. '
        '`cfg_d128` is the selected full model (FM), not a 21st configuration. Two joint-interaction runs are secondary only. '
        'No training, inference, selection publication, or retrieval computation was executed. P11 is excluded.',
        'Input prompt: consolidate the full accepted P9 training/validation histories and canonical P10 held-out metrics; '
        'audit lineage, loss semantics, selection agreement and metric availability; publish only a report and small derived evidence.',
        '## 2. Experiment Lineage And Inventory',
        'Primary eligibility: `p9elig_250e0140d593f360f1368ef1`; original completed P9-A snapshot: '
        '`p9elig_8d017288b37c7c7a08734fa7`. Each primary model resolves uniquely through '
        '`AcceptedCheckpointResolver`: eligibility -> acceptance -> finalization -> immutable run bundle -> checkpoint locator and bytes. '
        'Terminal histories are read from the checkpoint matching the accepted bundle stopping boundary, never a filesystem latest file.',
        'The cfg_d64 observation is the explicitly accepted v2 historical import `p9accv2_d93b01ef13c3f26a22287ce7`. '
        'Its source configuration is `cfg_main`, v2 config identity `p9cfglegacy_fe87488eced8c54d852473d5`. '
        '`config/dissertation_authority_refresh.json` explicitly authorizes the reporting alias cfg_d64. '
        'Reading its v2-bound historical payload is not fallback to a v1 acceptance. Requested compact labels '
        'cfg_ema990/cfg_ip0/cfg_lr2/cfg_lr3/cfg_lr10 map explicitly to cfg_ema_990/cfg_ip_0/cfg_lr_2/cfg_lr_3/cfg_lr_10.',
        mdtable(inv, {'model_id':'Model','configuration_id':'Source configuration','p9_authority_id':'Authority','run_id':'v2 run','run_bundle_id':'Bundle'}),
        '## 3. P9 Training And Validation Methodology',
        'Population: 2,421 training scenes, 400 validation scenes, 1,600 held-out evaluation scenes. '
        'Validation uses 800 fixed augmented queries against 400 original scenes; canonical held-out uses 3,200 augmented queries against 1,600 originals. '
        'The validation and held-out main-intensity query sets are fixed independently of training-bank intensity.',
        'Accepted P9 selection contract `p9-selection-v2.1.0` / `p9selc_c9865aadb72174e79b57a030`: '
        'chronological committed checkpoints; minimize validation retrieval loss; treat an absolute binary64 loss difference '
        '**strictly < 1e-4** as equivalent; prefer larger mean source-separation margin, then earlier epoch. '
        'Validate every five epochs. Patience is four validation events; reset only for loss decrease >= 1e-4 relative to the previous selected best. '
        'A margin-only selection change does not reset patience. This report independently replays this rule without publishing a checkpoint or model decision.',
        'All 20 selected epochs, checkpoint IDs, losses and margins agree exactly with accepted resolver results. '
        'Early-stopping counter histories also agree with ledger events. Maximum training horizon is 200 epochs; '
        '76 updates/epoch, global batch 32 over two ranks of 16, AdamW, ten-epoch linear warmup then cosine decay to zero. '
        'Float32, AMP/TF32 off, gradient-norm clipping at 1, EMA and FIFO negative queue capacity 8,192. '
        'Effective bank/configuration values are resolved per model below. P9 contracts override prototype-only settings '
        'in `config/p7_deterministic_training.yml`, notably its older patience-reset wording and prototype population/schedule.',
        mdtable(frames['selection_contract_validation'], {'model_id':'Model','selected_epoch':'Accepted epoch',
            'selected_validation_retrieval_loss':'Accepted loss','selected_validation_margin':'Accepted margin',
            'recomputed_selected_epoch':'Independent epoch','selection_agreement':'Agreement'}),
        '## 4. Metric And Recording Semantics',
        '**Training total** is the optimized objective `scene_loss + lambda_IP * raw_IP_loss`. '
        '**Scene loss** is symmetric contrastive InfoNCE over augmented views and the accepted negative dictionary, '
        'temperature 0.1, training-negative geographic exclusion 750 m. **Raw IP** averages applicable modality-specific reconstruction terms '
        '(relative position, intrinsic geometry, semantics, environmental context) with globally normalized valid-target denominators. '
        '**Weighted IP** is the separately recorded lambda_IP contribution, not the raw loss.',
        'Per-update values in these checkpoint traces are the recorded rank-0, world-size-scaled local objectives whose DDP gradients optimize the global objective. '
        'They are not a newly reconstructed global two-rank mean. Master-table training values are arithmetic means of the 76 recorded updates '
        'in the selected epoch; raw per-update values remain in training_history. Epoch means are labeled derived summaries, never substituted for checkpoint validation values.',
        'Early native checkpoints do not explicitly record raw or weighted IP, while the historical d64 trace records weighted IP only. '
        'Missing fields remain NA_NOT_RECORDED; no total-minus-scene reconstruction or division by lambda is used to fill them. '
        'For lambda_IP=0 configurations that do record raw IP, that measured raw value is retained and weighted IP is separately zero. '
        'DS explicitly removes all IP modules and sets lambda_IP=0; its recorded raw/weighted zeros are empty-objective sentinels, not evidence of perfect reconstruction.',
        '**P9 validation / P10 held-out retrieval loss** is mean cross-entropy of correct-source cosine similarity '
        'against the complete split gallery, temperature 0.1, on final scene embeddings rather than the contrastive projection. '
        '**Margin** is mean correct-source cosine minus the strongest incorrect candidate cosine. **MRR** is mean reciprocal source rank; '
        '**HIT@K** is the fraction with source rank <= K. Larger MRR/HIT/margin and lower retrieval loss are favorable within their own split. '
        'P9 and P10 loss magnitudes are not directly comparable because gallery size and composition differ. P10 never explains P9 checkpoint choice.',
        '## 5. Twenty-Model Master Summary', mdtable(inv, master),
        '## 6. P9-A Hyperparameter Study',
        'The shared OFAT reference is historical cfg_d64: d=64, K=8, main 1.0x, EMA=0.999, lambda_IP=1, peak LR=0.001. '
        'cfg_d128 changes dimension only; it was not the common reference for the other factors. Each configuration has one executed seed, '
        'so these are descriptive sensitivity observations, not replicated significance tests.',
        mdtable(frames['p9a_summary'], {'model_id':'Model','changed_factor':'Historical factor', 'd':'d','effective_k':'K',
            'intensity':'Intensity','ema':'EMA','lambda_ip':'lambda_IP','peak_learning_rate':'Peak LR',
            **{k:v for k,v in basic.items() if k!='model_id'}})]
    reference = indexed.loc['cfg_d64','selected_validation_retrieval_loss']
    for title, group in [('Dimension',['cfg_d48','cfg_d64','cfg_d128']),('K',['cfg_k2','cfg_k4','cfg_d64','cfg_k16']),
                         ('Intensity',['cfg_intensity_05','cfg_d64','cfg_intensity_20']),('EMA',['cfg_ema990','cfg_d64']),
                         ('IP',['cfg_ip0','cfg_d64']),('LR',['cfg_d64','cfg_lr2','cfg_lr3','cfg_lr10'])]:
        values = indexed.loc[group,'selected_validation_retrieval_loss']
        lines.append(f'- **{title}:** '+', '.join(f'{m} {values[m]:.9f}' for m in group)+
            f'. Lowest observed loss: {values.idxmin()}; loss range {values.max()-values.min():.9f}.')
    lines += ['Dimension has the largest loss spread among these OFAT groups. Increasing d from 64 to 128 reduces loss by '
        f'{reference-indexed.loc["cfg_d128","selected_validation_retrieval_loss"]:.9f}. '
        'K=4 and weak augmentation improve on their d64 reference, but neither trend is monotonic across all tested settings. '
        'EMA=.999 is better than .990; removing IP modestly improves this d64 comparison. LR=.003 improves on .001, while .01 degrades. '
        'These factor-wise preferences are not additive predictions.',
        '## 7. Secondary Joint-Interaction Diagnostics',
        'Both runs combine d=128, K=4, weak 0.5x, EMA=.999, peak LR=.003, differing only in lambda_IP (0 or 1), '
        'with their predeclared shared seed namespace. They tested the joint factor-wise configuration and its IP interaction. '
        'Neither belongs to the primary 20. The bounded pair favored IP=1, but both had worse validation loss than the executed cfg_d128 FM. '
        'The final decision therefore retained cfg_d128 and explicitly rejected factor-wise additivity.',
        mdtable(frames['interaction_diagnostics'], {'model_id':'Diagnostic','effective_config_json':'Effective config',
            **{k:v for k,v in basic.items() if k!='model_id'},'checkpoint_id':'Checkpoint','p9_acceptance_id':'Acceptance'}),
        f'Final decision `{metadata["final_decision"]["decision_id"]}` evaluated the 13 P9-A observations plus two joint diagnostics; '
        f'pair decision `{metadata["interaction_decision"]["decision_id"]}` applies only within that diagnostic pair.',
        '## 8. P9-B Ablation And Baseline Comparison',
        'All seven variants inherit the selected cfg_d128 settings without variant-specific retuning, except the explicit DS IP removal. '
        'SSV and DS are controlled strategy-inspired variants, not claimed reproductions. Deltas are descriptive differences from FM, not new selection metrics.',
        mdtable(frames['p9b_summary'], {'model_id':'Model','architecture':'Difference',**{k:v for k,v in basic.items() if k!='model_id'},
            'delta_validation_retrieval_loss_from_fm':'Delta val loss vs FM','delta_validation_margin_from_fm':'Delta margin vs FM',
            'checkpoint_id':'Checkpoint','p9_acceptance_id':'Acceptance'}),
        '## 9. Training Curves',
        f'The primary training table contains **{len(tr):,} actual optimizer-update rows**. No unrecorded epoch or update is interpolated. '
        'Figures A/B/C show unsmoothed observed per-update total/scene/raw-IP values as small multiples; '
        'red stars mark the update producing the selected checkpoint and dotted lines mark its epoch. Missing raw-IP panels are explicit. '
        'Training objective values are not directly comparable across architectures with different active IP terms. '
        'The selected checkpoint need not minimize training loss, and continued training-loss improvement does not override validation stopping.',
        '## 10. Validation Curves',
        f'The primary validation table contains **{len(val):,} five-epoch checkpoint rows** with selected/terminal/early-stop flags. '
        'Figures D/E show every recorded retrieval-loss/margin observation; F/G show recorded MRR/HIT only. '
        'The non-monotonic validation trajectories and four-event patience explain terminal epochs later than selected epochs. '
        'A tolerated margin-based change can make the selected epoch differ from the absolute numeric loss minimum.',
    ]
    for group in ['p9a','p9b_fm']:
        for letter in 'ABCDEFG':
            lines.append(f'![{group} Figure {letter}](../{artifact.relative_to(ROOT)}/{group}_{letter}.png)')
    lines += ['## 11. Canonical P10 Held-Out Evaluation',
        'Only the frozen eight-model comparison set has accepted canonical P10 metrics. The other 12 primary models are '
        '**P10_NOT_EVALUATED**, not zero-performing. Canonical acceptance: `p10acc_6e5071beee7616750dec7907`; '
        'execution attempt: `p10exec_7fee193dac532190c79e02c6`. This report reads accepted evaluation.json metrics and '
        'checks the acceptance comparison, aggregate model-evaluation hash, and P9 checkpoint/acceptance bindings.',
        mdtable(h, {'model_id':'Model','retrieval_loss':'Held-out loss','mean_source_separation_margin':'Held-out margin',
            'MRR':'MRR','HIT@1':'HIT@1','HIT@5':'HIT@5','HIT@10':'HIT@10','query_count':'Queries','gallery_count':'Gallery',
            'checkpoint_id':'Checkpoint','p10_acceptance_id':'P10 acceptance','source_artifact_sha256':'Result SHA-256'}),
        '## 12. P9 Validation Versus P10 Held-Out',
        'FM retains the lowest held-out loss (0.589492917) and highest MRR (0.997060776). '
        'A4 is closest on held-out loss (0.622689188); A5 is closest on MRR (0.997052133), '
        'and ties FM on HIT@1/HIT@5/HIT@10 at stored precision. A4 also ties HIT@10. '
        'No model exceeds FM on MRR or HIT. A1, A2, A3 and SSV exceed FM on held-out mean margin; '
        'thus a larger margin alone does not establish better overall retrieval performance.',
        'P9 validation loss ordering (ascending): '+ ' < '.join(frames['p9b_summary'].sort_values('selected_validation_retrieval_loss').model_id)+'.',
        'P10 held-out loss ordering (ascending): '+' < '.join(h.sort_values('retrieval_loss').model_id)+'.',
        'The lowest-loss FM conclusion is consistent across splits, but the complete ordering need not be. '
        'A1-A5 do not show monotonic improvement in both loss and margin. Adding semantic/object context alone yields mixed changes; '
        'raster completion materially improves held-out rank metrics relative to A1-A3, and FM improves held-out loss over the generic-relation A5. '
        'These are conditional controlled-configuration contrasts, not evidence that any component is universally beneficial. '
        'DS has high rank metrics but the weakest held-out loss/margin in this set, illustrating that rank saturation and softmax concentration measure different properties.',
        'The later 10K gallery exists as a supplementary qualitative retrieval extension. It does not replace canonical P10 metrics; '
        'no 10K similarity values enter this report.',
        '## 13. Metric Availability And Limitations',
        mdtable(frames['metric_availability'], {'model_id':'Model','validation_retrieval_loss':'P9 val loss','validation_margin':'P9 margin',
            'validation_mrr':'P9 MRR','validation_hit1':'P9 HIT1','validation_hit5':'P9 HIT5','validation_hit10':'P9 HIT10',
            'training_ip_loss_raw':'Training raw IP','training_ip_loss_weighted':'Training weighted IP','p10_metrics':'P10 metrics'}),
        'The dissertation states that supplementary P9 ranks were recorded; the historical cfg_d64 payload does not contain those fields. '
        'This is a recording-coverage discrepancy, reported here without changing the manuscript or inventing missing metrics. '
        'Native records are audited individually; AVAILABLE means recorded at every validation checkpoint, not reconstructed at selection. '
        'Machine-readable metrics use float64 nullable columns plus explicit status columns; null means NA_NOT_RECORDED. '
        'Training rows between validation events also carry NOT_A_VALIDATION_INTERVAL. CSV exports spell missing cells NA_NOT_RECORDED. '
        'Stored binary floating-point precision is preserved in Parquet; Markdown uses nine decimal places. '
        'Recorded IP arithmetic is checked at rtol=2e-7, atol=2e-6 solely for float32 addition/multiplication rounding; '
        'all accepted selection/P10 source metric comparisons are exact binary64 equality.',
        'Historical import event timestamps are import times, not original training start/end timestamps. They are not relabeled as runtime. '
        'For cfg_d64, the v2-bound source attempt_state.json records its actual controller start and failure-classified terminal time. '
        'Their difference is reported only as controller elapsed time, including post-training termination, not an exact optimization duration. '
        'The accepted v2 import reconstructs scientific completion and patience stopping from the durable 125-epoch checkpoint despite that historical controller failure label. '
        'Native wall duration includes validation and interruptions between RUN_STARTED and TRAINING_COMPLETED; '
        'recorded per-update or validation-boundary-epoch operational intervals remain separately labeled. '
        'Boundary diagnostics measure the single epoch ending at each five-epoch validation boundary, not all five epochs. '
        'DS reaches the 200-epoch maximum without a patience trigger; the other 19 primary runs stop on patience. '
        'No missing elapsed time is estimated.',
        '## 14. Artifact Inventory',
        f'Artifact directory: `{artifact.relative_to(ROOT)}`. `manifest.json` binds source hashes, derived files, schema, '
        'model universe, implementation and verification. `source_hashes.json` records before hashes; validation.json records the after check. '
        'Complete training trajectories are in training_history.parquet, complete validation in validation_history.parquet. '
        'Per-model CSV appendices contain every recorded validation checkpoint. Secondary traces live only in interaction_* tables.',
        '\n'.join(f'- `{name}.parquet`: {len(frame):,} rows.' for name,frame in frames.items()),
        '## 15. Validation And Preservation',
        f'Assertions: {packed(receipt)}',
        'Checks include exact 20/13/7/8 counts, unique configuration mapping, 20 independent selection agreements, '
        'ledger patience/terminal agreement, checkpoint hash/locator validation, P10 metric/acceptance binding, '
        'per-update completeness, explicit missing-metric coverage, table roundtrip/schema, figure-input counts and Markdown numeric consistency. '
        'No targets were changed or executed; R target-manifest/network regeneration is not applicable.',
        'Prohibited work counts: training=0; fine-tuning=0; new inference=0; checkpoint reselection/publication=0; '
        'model reselection=0; P9 rerun=0; P10 rerun=0; excluded-stage execution=0; downstream fitting=0; '
        'data rematerialization=0; dissertation mutation=0. Independent replay is a verification calculation, not an acceptance change.',
        '## 16. Per-Model Appendix',
        'Each block binds full per-update trajectories by model_id and links a complete validation CSV. '
        'Selected and terminal training metrics below are epoch means. Full source identities and effective configuration remain in model_inventory.parquet.']
    for _,row in inv.iterrows():
        lines += [f'### {row.model_id}',
            f'Run `{row.run_id}`; source run `{row.source_run_id}`; authority `{row.p9_authority_id}`; bundle `{row.run_bundle_id}`. '
            f'Acceptance `{row.p9_acceptance_id}`; selected checkpoint `{row.checkpoint_id}`; terminal `{row.terminal_checkpoint_id}`.',
            f'Effective config: `{row.effective_config_json}`. Architecture: {row.architecture}.',
            f'Start {row.training_start}; end {row.training_end}; duration {fmt(row.training_duration_seconds)} seconds '
            f'({row.duration_semantics}). Stop reason `{row.stop_reason}`; early stopping {row.early_stopping}; '
            f'{row.stop_epoch} epochs / {row.stop_update} updates / {row.validation_count} validation checkpoints. '
            f'Selected epoch/update {row.selected_epoch}/{row.selected_update}. '
            f'Lowest recorded validation loss {row.minimum_recorded_validation_loss:.9f}.',
            mdtable(pd.DataFrame([{'stage':stage, **{metric:row[f'{stage}_{metric}'] for metric in ['training_total_loss','training_scene_loss','training_ip_loss_raw','training_ip_loss_weighted','validation_retrieval_loss','validation_margin','validation_mrr','validation_hit1','validation_hit5','validation_hit10']}} for stage in ['selected','terminal']]),
                {'stage':'Stage','training_total_loss':'Total','training_scene_loss':'Scene','training_ip_loss_raw':'Raw IP','training_ip_loss_weighted':'Weighted IP',
                 'validation_retrieval_loss':'P9 loss','validation_margin':'P9 margin','validation_mrr':'MRR','validation_hit1':'HIT1','validation_hit5':'HIT5','validation_hit10':'HIT10'}),
            f'[Complete validation trajectory](../{artifact.relative_to(ROOT)}/per_model/{row.model_id}_validation.csv). '
            f'Training filter: `model_id == "{row.model_id}"` in training_history.parquet. '
            f'P10: `{row.p10_result_path}`.']
        if row.model_id=='cfg_d64':
            lines.append(f'Historical controller terminal: {row.controller_terminal_time}; elapsed {row.controller_elapsed_seconds:.6f} seconds; '
                f'source status {row.controller_terminal_state}. Source `{row.controller_timing_source}` is hash-bound by the v2 source inventory. '
                f'Sum of recorded optimizer-update runtimes: {row.recorded_update_wall_seconds_sum:.6f} seconds, excluding validation and controller overhead. '
                'The exact end-of-optimization timestamp remains NA_NOT_RECORDED.')
    lines += ['## 17. Main Findings',
        '1. **FM:** cfg_d128 was selected from already executed candidates by the P9 validation rule, at epoch 85, '
        'loss 0.176506951 and margin 0.375468940. Neither joint diagnostic surpassed it.',
        '2. **Hyperparameters:** dimension showed the largest tested loss spread; aggressive LR=.01 and EMA=.990 degraded the d64-reference result. '
        'K=4, weak augmentation and LR=.003 had favorable individual contrasts, but their combination did not improve FM.',
        '3. **Held-out:** frozen FM retained the lowest canonical P10 loss and highest MRR, with tied best HIT values.',
        '4. **Architecture:** raster-complete models showed stronger held-out rank metrics than the object-only A1-A3/SSV variants; '
        'FM improved loss over A5, while margin did not improve monotonically with added components.',
        '5. **Consistency:** validation and held-out agree on the lowest-loss FM, not necessarily every secondary metric or full model ordering. '
        'No held-out value was used retrospectively for P9 selection.',
        '6. **Missing evidence:** historical cfg_d64 has no P9 MRR/HIT trajectory; early raw/weighted IP and some timing records are absent. '
        'Twelve primary configurations have no accepted P10 evaluation. These remain explicit missing/not-evaluated entries.']
    return '\n\n'.join(lines)+'\n'


def validate_output(out):
    manifest = json.loads((out/'manifest.json').read_text())
    for filename, digest in manifest['files'].items():
        assert sha(out/filename)==digest, f'Output hash mismatch: {filename}'
    frames = {name:pd.read_parquet(out/(name+'.parquet')) for name in manifest['table_rows']}
    result = validate_frames(frames)
    for name, frame in frames.items():
        assert len(frame)==manifest['table_rows'][name]
        assert {c:str(t) for c,t in frame.dtypes.items()}==manifest['schemas'][name]
    for _,row in frames['figure_inputs'].iterrows():
        source = frames['training_history' if row.metric.startswith('training_') else 'validation_history']
        selected = source[source.model_id==row.model_id]
        assert selected[row.metric].notna().sum()==row.observations
        assert (selected.selected_checkpoint & selected[row.metric].notna()).sum()==row.selected_marker_count
        assert (out/row.figure).stat().st_size>1000
    report = ROOT/manifest['report_path']
    assert sha(report)==manifest['report_sha256']
    text = report.read_text()
    for name, metrics in [('model_inventory',['selected_validation_retrieval_loss','selected_validation_margin']),
                          ('p10_heldout_summary',['retrieval_loss','mean_source_separation_margin','MRR','HIT@1','HIT@5','HIT@10'])]:
        for _,row in frames[name].iterrows():
            assert all(fmt(row[metric]) in text for metric in metrics)
    assert text.count('P11')==1
    assert not any(word in text for word in ['R²','RMSE','SGIS','ECOSTRESS','ridge probes','MLP probes'])
    assert 'P10_NOT_EVALUATED' in text and NA in text
    for model in MODELS:
        csv = pd.read_csv(out/'per_model'/f'{model}_validation.csv',keep_default_na=False)
        expected = frames['validation_history'].query('model_id == @model')
        assert len(csv)==len(expected)
        assert csv.checkpoint_id.tolist()==expected.checkpoint_id.tolist()
    return {**result,'output_hashes':'PASS','table_schemas':'PASS','figure_inputs':'PASS',
            'markdown_numeric_consistency':'PASS','scope_content':'PASS'}


def publish(frames, sources, metadata):
    import tempfile
    frames = enrich(frames, sources)
    receipt = validate_frames(frames)
    base = ROOT/'artifacts/p9-p10-results-report'
    base.mkdir(parents=True,exist_ok=True)
    code_digest = sha(Path(__file__))
    identity = {'contract':'p9-p10-readonly-results-v1','primary_models':MODELS,
                'sources':sources.hashes,'implementation_sha256':code_digest,
                'training_summary':'selected_epoch_arithmetic_mean','missing_metrics':'nullable_float64_with_explicit_status'}
    report_id = 'p9p10report_'+hashlib.sha256(packed(identity).encode()).hexdigest()[:24]
    out = base/report_id
    if out.exists():
        raise FileExistsError(f'Immutable report already exists: {out}')
    stage = Path(tempfile.mkdtemp(prefix='.staging-',dir=base))
    figures(frames,stage)
    for name, frame in frames.items():
        for column in frame.select_dtypes(include='object').columns:
            frame[column] = frame[column].where(frame[column].notna(),None)
        path = stage/(name+'.parquet')
        frame.to_parquet(path,index=False,compression='zstd')
        pd.testing.assert_frame_equal(frame,pd.read_parquet(path))
    small = ['model_inventory','selection_contract_validation','p9a_summary','p9b_summary','p10_heldout_summary',
             'metric_availability','interaction_diagnostics','validation_history']
    for name in small:
        frames[name].to_csv(stage/(name+'.csv'),index=False,na_rep=NA)
    (stage/'per_model').mkdir()
    for model in MODELS:
        frames['validation_history'].query('model_id == @model').to_csv(stage/'per_model'/f'{model}_validation.csv',index=False,na_rep=NA)
    (stage/'source_hashes.json').write_text(json.dumps(sources.hashes,sort_keys=True,indent=2)+'\n')
    preservation = sources.verify()
    receipt['source_preservation'] = preservation
    (stage/'validation.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    created = datetime.now(ZoneInfo('Asia/Seoul'))
    report = ROOT/'reports'/f'{created:%Y%m%d_%H%M}_p9_p10_comprehensive_model_results.md'
    assert not report.exists()
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report_text = render_report(frames,metadata,receipt,report_id,out,created.isoformat(),commit)
    report.write_text(report_text)
    manifest = {'report_id':report_id,'identity':identity,'report_path':str(report.relative_to(ROOT)),
        'report_sha256':sha(report), 'table_rows':{k:len(v) for k,v in frames.items()},
        'schemas':{k:{c:str(t) for c,t in v.dtypes.items()} for k,v in frames.items()},
        'files':{str(p.relative_to(stage)):sha(p) for p in sorted(stage.rglob('*')) if p.is_file()},
        'scientific_execution_counts':{k:0 for k in ['training','fine_tuning','inference','checkpoint_reselection',
            'model_reselection','p9_rerun','p10_rerun','excluded_stage_execution','downstream_fitting','data_rematerialization','dissertation_mutation']}}
    (stage/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    stage.rename(out)
    output_check = validate_output(out)
    print(json.dumps({'report':str(report),'artifact':str(out),'report_id':report_id,**output_check},sort_keys=True),flush=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate',type=Path,help='Validate an existing derived report without reading model tensors')
    args = parser.parse_args()
    if args.validate:
        print(json.dumps(validate_output(args.validate),sort_keys=True))
    else:
        publish(*collect())


if __name__=='__main__':
    main()
