"""Synthetic fixtures only; never build or copy a scientific P8 artifact."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("p8_plan_replay", ROOT / "python/p8_plan_replay.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p8-replay-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config/schemas").mkdir(parents=True)
        self.bundle_dir = self.root / "bundle"
        self.bundle_dir.mkdir()
        parents = {name: name + "-fixture" for name in (
            "p6_acceptance_id", "p7_acceptance_id", "p7_runtime_acceptance_id",
            "p4_bank_id", "p4_acceptance_id", "p4_index_id", "p5_validation_acceptance_id",
        )}
        self.config = {
            "parents": parents, "methodology": {"dissertation_commit": "thesis-fixture"},
            "run_accounting": dict(checker.COUNTS),
            "execution_prohibitions": {"evaluation_ancestry": False, "optimizer_updates": 0},
        }
        self.anchor = {
            "schema_version": "1.0.0", "policy": "fail_closed_read_only_no_fallback",
            "bundle_root": str(self.bundle_dir), "source_commit": "producer-fixture",
            "dissertation_commit": "thesis-fixture", "authority_id": "authority-fixture",
            "acceptance_id": "identity-8", "artifacts": [],
        }
        self.bundle = {
            name: {"status": "PASS", field: "identity-" + str(i)}
            for i, (name, field) in enumerate(zip(checker.ARTIFACTS, checker.IDENTITY_FIELDS))
        }
        comp, hyper, a5, ds, matrix, bank, plan, material, accept = self.bundle.values()
        comp.update(source_commit="producer-fixture", dissertation_commit="thesis-fixture",
                    p0_p7_main_semantics_changed=False,
                    preserved_acceptances={"p6": parents["p6_acceptance_id"], "p7": parents["p7_acceptance_id"]})
        a5["parent_p7_acceptance_id"] = ds["parent_p7_acceptance_id"] = parents["p7_acceptance_id"]
        bank.update(bank_id=parents["p4_bank_id"], bank_acceptance_id=parents["p4_acceptance_id"],
                    logical_index_id=parents["p4_index_id"])
        rows = [{
            "configuration_id": "cfg_main" if i == 0 else "fixture-" + str(i),
            "scientific_hash": "hash-" + str(i), "evaluation_ancestry": False,
            "evaluation_query_identity": None, "validation_acceptance_id": parents["p5_validation_acceptance_id"],
            "parent_p7_acceptance_id": parents["p7_acceptance_id"],
            "runtime_acceptance_id": parents["p7_runtime_acceptance_id"],
            "bank_binding": {"physical_bank_id": bank["bank_id"],
                             "bank_acceptance_id": bank["bank_acceptance_id"],
                             "logical_index_id": bank["logical_index_id"]},
        } for i in range(13)]
        hyper.update(rows=rows, count=13, main_count=1, factor_count=6, duplicate_hashes=0)
        templates = [{
            "template_id": "template-" + str(i), "comparison_class": "ablation" if i < 5 else "controlled_baseline",
            "evaluation_ancestry": False, "evaluation_query_identity": None,
            "validation_acceptance_id": parents["p5_validation_acceptance_id"],
            "required_bank_identity": bank["bank_id"], "hyperparameter_selection_eligible": False,
            "final_config_hash_status": "UNRESOLVED_UNTIL_P9_A_SELECTION",
        } for i in range(7)]
        matrix.update(templates=templates, count=7, ablation_count=5, controlled_baseline_count=2,
                      materialized_count=0)
        plan.update(configuration_matrix_id=hyper["matrix_id"], attempt_count=13,
                    configuration_ids=[r["configuration_id"] for r in rows],
                    configuration_hashes=[r["scientific_hash"] for r in rows],
                    validation_acceptance_id=parents["p5_validation_acceptance_id"], evaluation_ancestry=False)
        material.update(template_matrix_id=matrix["matrix_id"], expected_materialization_count=7,
                        template_ids=[r["template_id"] for r in templates], materializable_before_selection=0,
                        hyperparameter_selection_eligible=False, evaluation_ancestry=False)
        for document in (matrix, material):
            document.update(a5_generic_relation_contract_id=a5["contract_id"],
                            ds_raster_materialization_contract_id=ds["contract_id"])
        for name, field, link in zip(checker.ARTIFACTS, checker.IDENTITY_FIELDS, checker.ACCEPTANCE_LINKS):
            accept[link] = self.bundle[name][field]
        accept.update(authority_id="authority-fixture", parents=parents, counts=dict(checker.COUNTS),
                      evaluation_ancestry_count=0, optimizer_update_count=0, checkpoint_creation_count=0,
                      p9_p10_p11_execution_count=0,
                      dimension_compatibility={"status": "PASS", "legacy_d128_artifact_adopted": False,
                                               "rows": [{"d": d, "construction": "PASS"} for d in (48, 64, 128)]})
        for name, field in zip(checker.ARTIFACTS, checker.IDENTITY_FIELDS):
            schema = "config/schemas/p8_" + name + ".schema.json"
            (self.root / schema).write_text(json.dumps({
                "type": "object", "required": ["status", field],
                "properties": {"status": {"type": "string"}, field: {"type": "string"}},
            }))
            self.anchor["artifacts"].append({
                "basename": name + ".json", "schema": schema,
                "identity_field": field, "identity": self.bundle[name][field],
            })
        (self.root / "config/p8_formal_experiment_plan.yml").write_text(yaml.safe_dump(self.config))
        self.anchor["scientific_config_sha256"] = hashlib.sha256(
            (self.root / "config/p8_formal_experiment_plan.yml").read_bytes()).hexdigest()
        self.persist()

    def persist(self):
        for name, spec in zip(checker.ARTIFACTS, self.anchor["artifacts"]):
            raw = json.dumps(self.bundle[name]).encode()
            (self.bundle_dir / (name + ".json")).write_bytes(raw)
            spec.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.save_anchor()

    def save_anchor(self):
        (self.root / "config/p8_refactor_replay.yml").write_text(yaml.safe_dump(self.anchor))

    def test_success_and_no_execution_or_writes(self):
        paths = list(self.bundle_dir.iterdir())
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess forbidden")), \
             mock.patch.object(Path, "write_bytes", side_effect=AssertionError("writer forbidden")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("writer forbidden")):
            first = checker.replay(self.root)
            self.assertEqual(first, checker.replay(self.root))
        self.assertEqual(first, [str(self.bundle_dir / (name + ".json")) for name in checker.ARTIFACTS])
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths})
        tree = ast.parse((ROOT / "python/p8_plan_replay.py").read_text())
        imports = {node.module if isinstance(node, ast.ImportFrom) else alias.name
                   for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        self.assertEqual(imports, {"argparse", "hashlib", "json", "pathlib", "jsonschema", "yaml"})
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id in {"eval", "exec", "__import__", "open"}
                             for n in ast.walk(tree)))

    def test_missing(self):
        (self.bundle_dir / (checker.ARTIFACTS[0] + ".json")).unlink()
        with self.assertRaises(FileNotFoundError):
            checker.replay(self.root)

    def test_wrong_hash(self):
        self.anchor["artifacts"][0]["sha256"] = "0" * 64
        self.save_anchor()
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            checker.replay(self.root)

    def test_wrong_size(self):
        self.anchor["artifacts"][0]["size"] += 1
        self.save_anchor()
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            checker.replay(self.root)

    def test_malformed_json(self):
        raw = b"{broken"
        (self.bundle_dir / (checker.ARTIFACTS[0] + ".json")).write_bytes(raw)
        self.anchor["artifacts"][0].update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.save_anchor()
        with self.assertRaises(json.JSONDecodeError):
            checker.replay(self.root)

    def test_schema_mismatch(self):
        self.bundle[checker.ARTIFACTS[0]]["compatibility_id"] = 123
        self.persist()
        with self.assertRaises(checker.jsonschema.ValidationError):
            checker.replay(self.root)

    def test_wrong_identity(self):
        self.bundle[checker.ARTIFACTS[0]]["compatibility_id"] = "wrong"
        self.persist()
        with self.assertRaisesRegex(ValueError, "artifact identity"):
            checker.replay(self.root)

    def test_failed_acceptance(self):
        self.bundle[checker.ARTIFACTS[-1]]["status"] = "FAIL"
        self.persist()
        with self.assertRaisesRegex(ValueError, "not PASS"):
            checker.replay(self.root)

    def test_order_mismatch(self):
        self.anchor["artifacts"].reverse()
        self.save_anchor()
        with self.assertRaisesRegex(ValueError, "ordering mismatch"):
            checker.replay(self.root)

    def test_cross_identity_mismatch(self):
        self.bundle[checker.ARTIFACTS[-1]]["hyperparameter_matrix_id"] = "wrong"
        self.persist()
        with self.assertRaisesRegex(ValueError, "cross-artifact identity"):
            checker.replay(self.root)

    def test_accounting_mismatch(self):
        self.bundle[checker.ARTIFACTS[-1]]["counts"]["total_attempts"] = 21
        self.persist()
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            checker.replay(self.root)

    def test_evaluation_ancestry(self):
        self.bundle[checker.ARTIFACTS[1]]["rows"][0]["evaluation_ancestry"] = True
        self.persist()
        with self.assertRaisesRegex(ValueError, "evaluation ancestry"):
            checker.replay(self.root)

    def test_producer_commit(self):
        self.bundle[checker.ARTIFACTS[0]]["source_commit"] = "current-head-is-not-authority"
        self.persist()
        with self.assertRaisesRegex(ValueError, "producer commit"):
            checker.replay(self.root)

    def test_schema_mapping(self):
        self.anchor["artifacts"][0]["schema"] = self.anchor["artifacts"][1]["schema"]
        self.save_anchor()
        with self.assertRaisesRegex(ValueError, "schema mapping"):
            checker.replay(self.root)

    def test_scientific_config_drift(self):
        path = self.root / "config/p8_formal_experiment_plan.yml"
        path.write_text(path.read_text() + "\n# changed config\n")
        with self.assertRaisesRegex(ValueError, "scientific config anchor"):
            checker.replay(self.root)


if __name__ == "__main__":
    unittest.main()
