"""Fail-closed provenance and payload tests for the new verifier-only path."""
import json
from pathlib import Path
import pytest
from s11_revalidation import snapshot_tree, verify_manifest_tree
from representation_analysis import file_sha256


def fixture(root):
    directory=root/'fixture'/'one';directory.mkdir(parents=True)
    payload=directory/'data.json';payload.write_text('{"value":1}\n')
    context={'generation':'old','runtime':{'sources':{'old':'bytes'}}}
    manifest={'status':'PASS','kind':'fixture','context':context,
              'files':{'data.json':file_sha256(payload)},'parents':{}}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    return context, payload


def test_read_only_original_context(tmp_path):
    ctx,_=fixture(tmp_path);before=snapshot_tree(tmp_path)
    assert len(verify_manifest_tree(tmp_path,ctx,before))==1
    assert snapshot_tree(tmp_path)==before
    with pytest.raises(ValueError,match='CONTEXT'):
        verify_manifest_tree(tmp_path,{'generation':'new'},before)


def test_modified_payload_rejected(tmp_path):
    ctx,p=fixture(tmp_path);p.write_text('modified')
    with pytest.raises(ValueError,match='PAYLOAD_HASH'):
        verify_manifest_tree(tmp_path,ctx,snapshot_tree(tmp_path))


def test_unregistered_and_symlink_rejected(tmp_path):
    ctx,p=fixture(tmp_path);extra=tmp_path/'unregistered';extra.write_text('extra')
    with pytest.raises(ValueError,match='UNREGISTERED'):
        verify_manifest_tree(tmp_path,ctx,snapshot_tree(tmp_path))
    extra.unlink();extra.symlink_to(p)
    with pytest.raises(ValueError,match='SYMLINK'):
        snapshot_tree(tmp_path)


def test_pass_schema_requires_all_checks_and_immutability():
    import jsonschema
    root=Path(__file__).resolve().parents[2]
    schema=json.loads((root/'config/schemas/s11_revalidation.schema.json').read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({'status':'PASS','scientific_payloads_unchanged':False},schema)
