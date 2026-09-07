from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v1_retirement import (
    FORMAL_AUTHORITY_IDS,
    HISTORICAL_STORE_NAMES,
    RECOVERY_AUTHORITY_IDS,
    RETIREMENT_ERROR_CODE,
    build_retirement_manifest,
    inspect_retirement_sources,
    publish_retirement_manifest,
)
from training_schema import validate_instance


@pytest.mark.parametrize("relative", (
    "scripts/p9_checkpoint_recovery_authorization.py",
    "scripts/p9_formal_authorization.py",
))
def test_retired_clis_fail_before_argument_parsing(relative):
    result = subprocess.run([sys.executable, "-B", str(ROOT / relative), "--help"],
                            cwd=ROOT, text=True, capture_output=True, timeout=20)
    assert result.returncode == 78
    assert RETIREMENT_ERROR_CODE in result.stderr


def test_retirement_manifest_is_read_only_and_complete():
    value = build_retirement_manifest(ROOT)
    validate_instance("v1_retirement_manifest", value)
    assert [item["identity"] for item in value["formal_authorities"]] == list(FORMAL_AUTHORITY_IDS)
    assert [item["identity"] for item in value["recovery_authorities"]] == list(RECOVERY_AUTHORITY_IDS)
    assert [item["name"] for item in value["historical_stores"]] == list(HISTORICAL_STORE_NAMES)
    assert all(item["status"] == "RETIRED_INELIGIBLE"
               for item in [*value["formal_authorities"], *value["recovery_authorities"]])
    assert all(item["status"] == "HISTORICAL_READ_ONLY" for item in value["historical_stores"])
    assert "source_hashes" not in value
    assert value["retirement_publication_identity"] == "current-lineage-p9-v1-retirement-v2"
    assert inspect_retirement_sources(ROOT) == inspect_retirement_sources(ROOT)


def test_retirement_publication_is_idempotent_and_collision_safe(tmp_path):
    manifest = build_retirement_manifest(ROOT)
    first = publish_retirement_manifest(manifest, tmp_path)
    before = first.read_bytes()
    assert publish_retirement_manifest(manifest, tmp_path).read_bytes() == before
    corrupt = copy.deepcopy(manifest)
    corrupt["status"] = "V1_RETIRED_READ_ONLY"
    first.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="collision"):
        publish_retirement_manifest(corrupt, tmp_path)


def test_retired_target_entrypoints_fail_closed():
    expression = r'''
manifest <- targets::tar_manifest(script = "_targets.R")
if (any(grepl("^p9_v1_.*retired$", manifest$name))) stop("retired node remains")
for (script in c("_targets_p9_formal.R", "_targets_p9_recovery.R")) {
  failed <- tryCatch({targets::tar_manifest(script = script); FALSE}, error = function(e) {
    grepl("TRAINING_V1_EXECUTION_RETIRED", conditionMessage(e), fixed = TRUE)
  })
  if (!failed) stop(script)
}
'''
    result = subprocess.run(["Rscript", "-e", expression], cwd=ROOT,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
