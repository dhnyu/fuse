#!/usr/bin/env python3
"""Build or publish the cfg_d128 overall decision and non-executed P9-B plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_final_model_selection import (  # noqa: E402
    FINAL_ACCEPTANCE_ID, build_final_model_decision, materialize_p9_b_plan,
    publish_final_model_materialization,
)
from p9_selected_fm_campaign import _resolver  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default="config/p9_v2_training_controller.yml")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    contract = yaml.safe_load((ROOT / args.contract).read_text(encoding="utf-8"))
    canonical = Path(contract["roots"]["canonical_publication"])
    lifecycle = Path(contract["roots"]["lifecycle_records"])
    acceptance = json.loads((canonical / "acceptances" / FINAL_ACCEPTANCE_ID / "acceptance.json").read_text())
    bundle_record = lifecycle / acceptance["authority_id"] / "bundle.json"
    eligibility = canonical / "eligibility" / "p9elig_8d017288b37c7c7a08734fa7.json"
    resolver = _resolver(canonical, eligibility, [{"bundle_record": str(bundle_record)}])
    resolved = resolver.resolve_accepted_checkpoint(FINAL_ACCEPTANCE_ID)
    interaction_id = "p9sfm_dca5569ef50bd9bfb1940032"
    interaction = json.loads((canonical / "selected_fm" / f"{interaction_id}.json").read_text())
    decision = build_final_model_decision(
        resolved,
        p9_a_eligibility_id="p9elig_8d017288b37c7c7a08734fa7",
        interaction_decision_id=interaction_id,
        interaction_acceptance_ids=(
            interaction["results"]["cfg_selected_fm_ip0"]["acceptance_id"],
            interaction["results"]["cfg_selected_fm_ip1"]["acceptance_id"],
        ),
    )
    templates = json.loads(
        (Path(contract["roots"]["p8_bundle"]) / "comparison_variant_template_matrix.json").read_text()
    )["templates"]
    plan = materialize_p9_b_plan(decision, resolved, templates)
    output = {"decision_id": decision["decision_id"], "plan_id": plan["plan_id"]}
    if args.publish:
        decision_path, plan_path = publish_final_model_materialization(decision, plan, canonical)
        output.update({"decision_path": str(decision_path), "plan_path": str(plan_path)})
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
