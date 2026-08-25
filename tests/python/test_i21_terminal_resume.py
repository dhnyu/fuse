#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import run_prototype_training_ddp as runner  # noqa: E402
from prototype_training_runtime import (  # noqa: E402
    ProfilerPolicy, ResumeSelection, checkpoint_completed_epoch,
    select_resume_checkpoint, terminal_checkpoint_decision,
)
from prototype_validation import NEW_SELECTION_RULE, replay_early_stopping  # noqa: E402


class TerminalResumeContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="fuse-i21-terminal-")
        self.root = Path(self.temporary.name)
        self.parents = {name: str(index) * 64 for index, name in enumerate(
            ("dataset", "loader", "gate", "encoder", "augmentation", "joint", "distributed_joint"), 1)}
        self.spec = {
            "plan_id": "ptp_" + "1" * 24, "run_id": "ptr_" + "2" * 24, "seed": 1729,
            "validation": {"early_stopping_patience_evaluations": 2},
            "optimizer": {"maximum_epochs": 30},
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def state(self, epoch: int, patience: int, history: list[dict] | None = None, **updates):
        value = {
            "plan_id": self.spec["plan_id"], "run_id": self.spec["run_id"], "seed": self.spec["seed"],
            "scientific_parents": self.parents, "world_size": 2, "optimizer_step": epoch * 8,
            "scene_consumptions": epoch * 256, "early_stopping_patience_state": patience,
            "validation_history": history or [],
            "distributed_rank_states": [{"rank": rank, "sampler_epoch": epoch - 1} for rank in (0, 1)],
        }
        value.update(updates)
        return value

    def ledger(self, epochs: int = 40) -> Path:
        path = self.root / "optimizer_steps.jsonl"
        rows = [{"optimizer_step": step, "epoch": (step - 1) // 8 + 1} for step in range(1, epochs * 8 + 1)]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def save(self, epoch: int, state: dict) -> Path:
        path = self.root / f"epoch-{epoch:03d}.pt"; torch.save(state, path); return path

    def test_terminal_early_stopping_selects_first_and_excludes_later_evidence(self):
        history = [{"epoch": 5, "MRR": 1.0, "HIT@1": 1.0},
                   {"epoch": 10, "MRR": 0.9, "HIT@1": 0.9},
                   {"epoch": 15, "MRR": 0.8, "HIT@1": 0.8}]
        terminal = self.save(15, self.state(15, 2, history))
        later = self.save(20, self.state(20, 3, history + [{"epoch": 20, "MRR": 0.7, "HIT@1": 0.7}]))
        selected = select_resume_checkpoint((later, terminal), self.spec, self.parents, self.ledger())
        self.assertEqual(selected.path, terminal)
        self.assertEqual(selected.post_termination_paths, (later,))
        self.assertEqual(selected.decision.reason, "early_stopping")

    def test_nonterminal_resumes_next_epoch_and_maximum_epoch_blocks(self):
        nonterminal = self.save(10, self.state(10, 0, [{"epoch": 10, "MRR": 1.0, "HIT@1": 1.0}]))
        selected = select_resume_checkpoint((nonterminal,), self.spec, self.parents, self.ledger())
        self.assertFalse(selected.decision.terminal)
        self.assertEqual(checkpoint_completed_epoch(selected.state) + 1, 11)
        maximum = self.state(30, 0, [{"epoch": 30, "MRR": 1.0, "HIT@1": 1.0}])
        self.assertEqual(terminal_checkpoint_decision(maximum, self.spec).reason, "maximum_epochs")

    def test_new_saturated_loss_contract_replays_patience_and_metric_state(self):
        validation = {
            "early_stopping_patience_evaluations": 2,
            "checkpoint_selection": NEW_SELECTION_RULE,
            "patience_reset": "higher_MRR_or_saturated_retrieval_loss_min_delta",
            "retrieval_loss_min_delta": 1e-4,
            "floating_point_tolerance": 1e-12,
            "mrr_saturation_value": 1.0,
        }
        history = [
            {"epoch": 5, "MRR": 1.0, "HIT@1": 1.0, "validation_retrieval_loss": 0.5,
             "mean_positive_hardest_negative_margin": 0.1},
            {"epoch": 10, "MRR": 1.0, "HIT@1": 1.0, "validation_retrieval_loss": 0.49995,
             "mean_positive_hardest_negative_margin": 0.2},
            {"epoch": 15, "MRR": 1.0, "HIT@1": 1.0, "validation_retrieval_loss": 0.4998,
             "mean_positive_hardest_negative_margin": 0.3},
            {"epoch": 20, "MRR": 1.0, "HIT@1": 1.0, "validation_retrieval_loss": 0.49975,
             "mean_positive_hardest_negative_margin": 0.4},
            {"epoch": 25, "MRR": 1.0, "HIT@1": 1.0, "validation_retrieval_loss": 0.49974,
             "mean_positive_hardest_negative_margin": 0.5},
        ]
        patience, selected, metric_state = replay_early_stopping(history, validation)
        self.assertEqual(patience, 2)
        self.assertEqual(selected["epoch"], 25)
        spec = {**self.spec, "validation": validation}
        state = self.state(25, patience, history, early_stopping_metric_state=metric_state)
        self.assertEqual(terminal_checkpoint_decision(state, spec).reason, "early_stopping")
        state["early_stopping_metric_state"] = {"best_mrr": 1.0, "saturated_retrieval_loss_reference": 0.5}
        with self.assertRaisesRegex(ValueError, "metric-state"):
            terminal_checkpoint_decision(state, spec)

    def test_foreign_lineage_and_rank_disagreement_are_rejected(self):
        foreign = self.state(5, 0); foreign["run_id"] = "ptr_" + "f" * 24
        path = self.save(5, foreign)
        with self.assertRaisesRegex(ValueError, "run_id"):
            select_resume_checkpoint((path,), self.spec, self.parents, self.ledger())
        mismatched = self.state(5, 0); mismatched["distributed_rank_states"][1]["sampler_epoch"] = 5
        with self.assertRaisesRegex(ValueError, "agree"):
            terminal_checkpoint_decision(mismatched, self.spec)

    def test_terminal_main_returns_before_spawn_cuda_or_training(self):
        state = self.state(15, 2, [{"epoch": 5, "MRR": 1.0, "HIT@1": 1.0},
                                  {"epoch": 10, "MRR": 0.9, "HIT@1": 0.9},
                                  {"epoch": 15, "MRR": 0.8, "HIT@1": 0.8}])
        checkpoint = self.save(15, state)
        selection = ResumeSelection(checkpoint, state, terminal_checkpoint_decision(state, self.spec), ())
        parent_keys = ("dataset_manifest", "dataloader_manifest", "no_op_gate_manifest", "encoder_manifest",
                       "augmentation_manifest", "joint_model_manifest", "distributed_joint_model_manifest")
        run_value = {**self.spec, "output_root": str(self.root),
                     **{key: {"sha256": value} for key, value in zip(parent_keys, self.parents.values(), strict=True)}}
        spec_path = self.root / "spec.json"; spec_path.write_text(json.dumps(run_value))
        training_path = self.root / "training.yml"; training_path.write_text(
            "output:\n  steps_name: optimizer_steps.jsonl\n  manifest_name: manifest.json\n"
            "  qc_name: prototype_training_qc.json\n  validation_name: validation_history.json\n")
        schema_path = self.root / "schema.json"; schema_path.write_text("{}")
        argv = ["runner", "--run-spec", str(spec_path), "--training-config", str(training_path)]
        for name in ("joint-config", "encoder-config", "augmentation-config", "tensor-contract", "i19-manifest"):
            argv.extend((f"--{name}", str(schema_path)))
        argv.extend(("--schema", str(schema_path)))
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(runner, "select_resume_checkpoint", return_value=selection), \
             mock.patch.object(runner, "find_existing_acceptance", return_value=self.root / "accepted"), \
             mock.patch.object(runner.mp, "spawn") as spawn, \
             mock.patch.object(runner.torch.cuda, "set_device") as cuda:
            runner.main()
        spawn.assert_not_called(); cuda.assert_not_called()

    def test_profiler_policy_is_disabled_by_default_and_sampling_is_bounded(self):
        self.assertFalse(ProfilerPolicy.from_config(None).should_profile(10))
        policy = ProfilerPolicy.from_config({"enabled": True, "warmup_steps": 2,
            "sampled_steps": [3, 8, 20], "interval_steps": 0, "max_sampled_steps": 2})
        self.assertEqual([step for step in range(1, 21) if policy.should_profile(step)], [3, 8])

    def test_terminal_without_acceptance_uses_cpu_recovery_not_training(self):
        state = self.state(15, 2, [{"epoch": 5, "MRR": 1.0, "HIT@1": 1.0},
                                  {"epoch": 10, "MRR": 0.9, "HIT@1": 0.9},
                                  {"epoch": 15, "MRR": 0.8, "HIT@1": 0.8}])
        checkpoint = self.save(15, state)
        selection = ResumeSelection(checkpoint, state, terminal_checkpoint_decision(state, self.spec), ())
        parent_keys = ("dataset_manifest", "dataloader_manifest", "no_op_gate_manifest", "encoder_manifest",
                       "augmentation_manifest", "joint_model_manifest", "distributed_joint_model_manifest")
        run_value = {**self.spec, "output_root": str(self.root),
                     **{key: {"sha256": value} for key, value in zip(parent_keys, self.parents.values(), strict=True)}}
        spec_path = self.root / "spec-recovery.json"; spec_path.write_text(json.dumps(run_value))
        training_path = self.root / "training-recovery.yml"; training_path.write_text(
            "output:\n  steps_name: optimizer_steps.jsonl\n  manifest_name: manifest.json\n"
            "  qc_name: prototype_training_qc.json\n  validation_name: validation_history.json\n")
        schema_path = self.root / "schema-recovery.json"; schema_path.write_text("{}")
        argv = ["runner", "--run-spec", str(spec_path), "--training-config", str(training_path)]
        for name in ("joint-config", "encoder-config", "augmentation-config", "tensor-contract", "i19-manifest"):
            argv.extend((f"--{name}", str(schema_path)))
        argv.extend(("--schema", str(schema_path)))
        recovered = {"status": "PASS", "cuda_operations": 0, "additional_optimizer_steps": 0, "output_files": []}
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(runner, "select_resume_checkpoint", return_value=selection), \
             mock.patch.object(runner, "find_existing_acceptance", return_value=None), \
             mock.patch("recover_prototype_training_acceptance.publish_preserved_terminal_stage", return_value=recovered) as publisher, \
             mock.patch.object(runner.mp, "spawn") as spawn, \
             mock.patch.object(runner, "train_group") as train:
            runner.main()
        publisher.assert_called_once(); spawn.assert_not_called(); train.assert_not_called()

    def test_disabled_profiler_allocates_no_cuda_events_and_is_identity_excluded(self):
        timer = runner._CudaPhaseTimer(False)
        with mock.patch.object(runner.torch.cuda, "Event") as event, \
             mock.patch.object(runner.torch.cuda, "synchronize") as synchronize:
            self.assertIsNone(timer.start()); timer.stop("unused", None); self.assertEqual(timer.values(), {})
        event.assert_not_called(); synchronize.assert_not_called()
        training = {"execution": {"workers": 40, "archive_source_root": "/authority",
                                  "archive_runtime_root": "/runtime", "profiler": {"enabled": False}}}
        baseline = runner.training_contract_sha256(training)
        training["execution"]["profiler"] = {"enabled": True, "sampled_steps": [3]}
        self.assertEqual(runner.training_contract_sha256(training), baseline)


if __name__ == "__main__":
    unittest.main()
