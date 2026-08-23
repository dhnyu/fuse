#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from recover_prototype_training_acceptance import (  # noqa: E402
    OUTPUT_ROLES,
    atomic_publish,
    file_record,
    validate_output_records,
)


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
        for index, role in enumerate(OUTPUT_ROLES):
            path = root / f"output-{index}.json"
            path.write_text(json.dumps({"role": role}))
            records.append(file_record(path, role))
        return records

    def manifest(self):
        return {
            "schema_version": "1.0.0", "status": "PASS",
            "training_acceptance_id": "pta_" + "0" * 24,
            "plan_id": "ptp_19ce115adab48c4ff737a44d",
            "run_id": "ptr_35743175250eaa556102185c",
            "scientific_identity": {},
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

    def test_schema_accepts_current_and_rejects_old_plan_run(self):
        value = self.manifest()
        jsonschema.validate(value, self.schema)
        for key, old in (("plan_id", "ptp_05d5ce9143d6448516aa8c56"),
                         ("run_id", "ptr_679a52f3fa0c56cc28a31ae7")):
            foreign = dict(value)
            foreign[key] = old
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(foreign, self.schema)

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


if __name__ == "__main__":
    unittest.main()
