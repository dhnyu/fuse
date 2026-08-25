#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from recover_prototype_training_acceptance import (  # noqa: E402
    OUTPUT_ROLES,
    audit_existing_accepted_bundle,
    atomic_publish,
    file_record,
    validate_post_termination_evidence,
    validate_output_records,
)
from prototype_training_runtime import validate_acceptance_manifest  # noqa: E402


class PrototypeTrainingAcceptanceRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="fuse-i21-recovery-test-")
        self.root = Path(self.temporary.name)
        self.schema = json.loads((ROOT / "config/schemas/prototype_training_acceptance.schema.json").read_text())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def output_records(self, root: Path | None = None):
        root = root or self.root
        records = []
        for name, role in zip(("prototype_training_qc.json", "validation_history.json"), OUTPUT_ROLES, strict=True):
            path = root / name
            path.write_text(json.dumps({"role": role}))
            records.append(file_record(path, role))
        return records

    def manifest(self):
        parents = {name: str(index) * 64 for index, name in enumerate(
            ("dataset", "loader", "gate", "encoder", "augmentation", "joint", "distributed_joint"), 1)}
        return {
            "schema_version": "1.0.0", "status": "PASS",
            "training_acceptance_id": "pta_" + "0" * 24,
            "plan_id": "ptp_b26daa03f4fdc6717d53cc33",
            "run_id": "ptr_50be4e6c09161b4c3aae940e",
            "scientific_identity": {"plan_id": "ptp_b26daa03f4fdc6717d53cc33",
                                    "run_id": "ptr_50be4e6c09161b4c3aae940e", "parents": parents,
                                    "run_spec_sha256": "8" * 64, "training_contract_sha256": "9" * 64,
                                    "training_implementation_sha256": "a" * 64, "seed": 1729,
                                    "numerical_policy": "two_process_ddp_float32_no_tf32", "world_size": 2},
            "completion": {"epochs_completed": 55, "optimizer_steps": 440,
                           "training_scene_consumptions": 14080, "termination": "early_stopping",
                           "additional_optimizer_steps": 0},
            "validation_history": [{"epoch": epoch, "MRR": 1.0, "HIT@1": 1.0, "HIT@5": 1.0,
                                    "HIT@10": 1.0, "population": 32,
                                    "embedding_digest": "a", "retrieval_digest": "b", "scene_ids_digest": "c"}
                                   for epoch in range(5, 56, 5)],
            "best_checkpoint": {"path": "/best.pt", "size_bytes": 1, "sha256": "0" * 64,
                                "optimizer_step": 40, "scene_consumptions": 1280, "epoch": 5, "role": "best"},
            "final_checkpoint": {"path": "/final.pt", "size_bytes": 1, "sha256": "1" * 64,
                                 "optimizer_step": 440, "scene_consumptions": 14080, "epoch": 55, "role": "final"},
            "exact_resume": {"status": "PASS", "checkpoint_step": 1, "comparison_steps": 1,
                             "direct_state_digest": "x", "replay_state_digest": "x"},
            "fresh_process_validation": {"status": "PASS", "mode": "fixture", "best_epoch": 5,
                                         "metrics": {}, "embedding_digest": "a", "retrieval_digest": "b"},
            "resources": {"optimizer_step_performed": True, "world_size": 2,
                          "worker_count": 40, "workers_per_rank": 20},
            "outputs": [
                {"relative_path": "prototype_training_qc.json", "size_bytes": 1, "sha256": "2" * 64},
                {"relative_path": "validation_history.json", "size_bytes": 1, "sha256": "3" * 64},
            ],
        }

    def test_schema_accepts_payload_and_dynamic_contract_rejects_foreign_plan_run_parent(self):
        value = self.manifest()
        jsonschema.validate(value, self.schema)
        run = {"plan_id": value["plan_id"], "run_id": value["run_id"]}
        parents = value["scientific_identity"]["parents"]
        validate_acceptance_manifest(value, self.schema, run, parents)
        for key, old in (("plan_id", "ptp_05d5ce9143d6448516aa8c56"),
                         ("run_id", "ptr_679a52f3fa0c56cc28a31ae7")):
            foreign = json.loads(json.dumps(value))
            foreign[key] = old
            with self.assertRaisesRegex(ValueError, key):
                validate_acceptance_manifest(foreign, self.schema, run, parents)
        foreign = json.loads(json.dumps(value)); foreign["scientific_identity"]["parents"]["dataset"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "parents"):
            validate_acceptance_manifest(foreign, self.schema, run, parents)

    def test_new_validation_contract_requires_v2_metrics_and_implementation_hashes(self):
        value = self.manifest(); value["schema_version"] = "2.0.0"
        value["scientific_identity"]["validation_implementation_sha256"] = "b" * 64
        value["scientific_identity"]["scheduler_implementation_sha256"] = "c" * 64
        metric_defaults = {
            "mean_rank": 1.0, "median_rank": 1.0, "validation_retrieval_loss": 0.2,
            "mean_positive_similarity": 0.8, "mean_hardest_negative_similarity": 0.5,
            "mean_positive_hardest_negative_margin": 0.3, "mean_top1_top2_similarity_gap": 0.3,
        }
        for row in value["validation_history"]: row.update(metric_defaults)
        run = {"plan_id": value["plan_id"], "run_id": value["run_id"], "validation": {
            "checkpoint_selection": "highest_MRR_then_lowest_validation_retrieval_loss_then_highest_mean_positive_hardest_negative_margin_then_earliest_epoch"
        }, "optimizer": {"learning_rate": 1e-4}}
        value["scientific_identity"]["validation_contract"] = run["validation"]
        value["scientific_identity"]["optimizer_contract"] = run["optimizer"]
        parents = value["scientific_identity"]["parents"]
        validate_acceptance_manifest(value, self.schema, run, parents)
        del value["validation_history"][0]["validation_retrieval_loss"]
        with self.assertRaisesRegex(ValueError, "validation_retrieval_loss"):
            validate_acceptance_manifest(value, self.schema, run, parents)

    def test_missing_duplicate_and_foreign_outputs_fail(self):
        records = self.output_records()
        validate_output_records(records, self.root)
        with self.assertRaises(ValueError):
            validate_output_records(records[:-1], self.root)
        duplicate = records[:-1] + [records[0]]
        with self.assertRaises(ValueError):
            validate_output_records(duplicate, self.root)
        foreign_root = self.root / "foreign"
        foreign_root.mkdir()
        foreign = self.output_records(foreign_root)
        with self.assertRaises(ValueError):
            validate_output_records(foreign, self.root)

    def test_immutable_reuse_and_collision(self):
        names = ("one.json", "two.json")
        final = self.root / "final"
        first = self.root / "stage-first"
        first.mkdir()
        for name in names:
            (first / name).write_text(name)
        self.assertEqual(atomic_publish(first, final, names), "new_publish")
        second = self.root / "stage-second"
        shutil.copytree(final, second)
        self.assertEqual(atomic_publish(second, final, names), "identical_reuse")
        collision = self.root / "stage-collision"
        shutil.copytree(final, collision)
        (collision / names[0]).write_text("different")
        with self.assertRaises(FileExistsError):
            atomic_publish(collision, final, names)

    def test_clean_current_acceptance_rejects_any_post_termination_evidence(self):
        self.assertIsNone(validate_post_termination_evidence("pta_" + "1" * 24, [], [], [], []))
        with self.assertRaisesRegex(ValueError, "post-termination evidence"):
            validate_post_termination_evidence(
                "pta_" + "1" * 24, [self.root / "epoch-060.pt"], [], [], []
            )
        with self.assertRaisesRegex(ValueError, "post-termination evidence"):
            validate_post_termination_evidence(
                "pta_" + "1" * 24, [], [self.root / "optimizer.interrupted"], [], []
            )

    def test_existing_accepted_bundle_remains_schema_valid_and_unchanged(self):
        root = Path("/mnt/hdd002/dhnyu/fusedata/training_data/v1/prototype/pro_b77dc79d854800dbe5a82e42/"
                    "serialization/psd_aa295747ee7814efbd1d177c/acceptance/ptd_8b3359690ea2d0bef52d63e3/"
                    "runs/ptr_50be4e6c09161b4c3aae940e/acceptance/pta_d97bcaf3178d05690600cd31")
        manifest_path = root / "prototype_training_acceptance_manifest.json"
        if not manifest_path.is_file(): self.skipTest("accepted I21 fixture is unavailable")
        before = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        self.assertEqual(before, "33ddcc669ca4dd0ccf6f896e10dbac5001a3e5dd2fbe3017535c3db5c9da7891")
        manifest = json.loads(manifest_path.read_text())
        run_spec = json.loads(Path("/mnt/hdd002/dhnyu/fusedata/training_data/v1/prototype/plans/prototype_train/"
                                   "ptp_b26daa03f4fdc6717d53cc33/run-spec.json").read_text())
        validate_acceptance_manifest(manifest, self.schema, run_spec, manifest["scientific_identity"]["parents"])
        validate_output_records(manifest["outputs"], root)
        self.assertEqual(hashlib.sha256(manifest_path.read_bytes()).hexdigest(), before)

    def test_existing_terminal_bundle_recovery_is_zero_compute_and_read_only(self):
        run_spec_path = Path(
            "/mnt/hdd002/dhnyu/fusedata/training_data/v1/prototype/plans/prototype_train/"
            "ptp_b26daa03f4fdc6717d53cc33/run-spec.json"
        )
        bundle = Path(
            "/mnt/hdd002/dhnyu/fusedata/training_data/v1/prototype/pro_b77dc79d854800dbe5a82e42/"
            "serialization/psd_aa295747ee7814efbd1d177c/acceptance/ptd_8b3359690ea2d0bef52d63e3/"
            "runs/ptr_50be4e6c09161b4c3aae940e/acceptance/pta_d97bcaf3178d05690600cd31"
        )
        if not run_spec_path.is_file() or not bundle.is_dir():
            self.skipTest("accepted I21 terminal bundle fixture is unavailable")
        run = json.loads(run_spec_path.read_text())
        run["_run_spec_path"] = str(run_spec_path)
        config = copy.deepcopy(yaml.safe_load((ROOT / "config/prototype_training.yml").read_text()))
        config["identity"].update({
            "plan_id": "ptp_b26daa03f4fdc6717d53cc33",
            "run_id": "ptr_50be4e6c09161b4c3aae940e",
            "joint_model_acceptance_id": "pjm_2c43bef0ecb99c26eba58bbf",
            "distributed_joint_acceptance_id": "pjd_394f70f85445591ad7ad930c",
        })
        result = audit_existing_accepted_bundle(
            run, config, self.schema, bundle, ROOT / "python/run_prototype_training_ddp.py",
            "9d36c4aa1bc46de1f14984aac6d374ddab156ce41a18d9983870f5dfeff6ea9c",
            hashlib.sha256((ROOT / "python/run_prototype_training_ddp.py").read_bytes()).hexdigest(),
        )
        counters = (
            "formal_training_process_count", "cuda_operation_count", "optimizer_step_count",
            "dataloader_worker_spawn_count", "new_checkpoint_count", "ledger_append_count",
            "publication_count", "artifact_mutation_count",
        )
        self.assertEqual(result["training_acceptance_id"], "pta_d97bcaf3178d05690600cd31")
        self.assertEqual(result["terminal_optimizer_step"], 440)
        self.assertTrue(all(result[name] == 0 for name in counters))


if __name__ == "__main__":
    unittest.main()
