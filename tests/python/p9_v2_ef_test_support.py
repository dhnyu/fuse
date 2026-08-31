from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_acceptance import AcceptancePublication, publish_acceptance  # noqa: E402
from p9_v2_bundle import BundlePublication, build_run_bundle, publish_run_bundle  # noqa: E402
from p9_v2_bundle_test_support import BundleFixture, make_bundle_fixture  # noqa: E402
from p9_v2_downstream import AcceptedCheckpointResolver, make_acceptance_eligibility  # noqa: E402
from p9_v2_finalization import finalize_run_bundle  # noqa: E402


@dataclass(frozen=True)
class SyntheticChain:
    fixture: BundleFixture
    bundle: BundlePublication
    finalization: dict[str, Any]
    acceptance: AcceptancePublication | None
    resolver: AcceptedCheckpointResolver | None


def make_synthetic_chain(root: Path, *, terminal: str = "complete", publish: bool = True) -> SyntheticChain:
    fixture = make_bundle_fixture(root / "fixture", terminal=terminal)
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle = publish_run_bundle(candidate, root / "bundles", fixture.locator_roots)
    finalization = finalize_run_bundle(bundle.path, fixture.locator_roots)
    if not publish:
        return SyntheticChain(fixture, bundle, finalization, None, None)
    authority = fixture.inputs.authority
    acceptance = publish_acceptance(
        finalization,
        bundle.path,
        fixture.locator_roots,
        root / "acceptances",
        authority_id=authority["identity"],
        authority_hash=authority["content_sha256"],
    )
    eligibility = make_acceptance_eligibility([
        {
            "acceptance_id": acceptance.acceptance_id,
            "eligibility": "ELIGIBLE",
            "authority_id": authority["identity"],
            "authority_hash": authority["content_sha256"],
        }
    ], namespace="synthetic-v2-ef")
    resolver = AcceptedCheckpointResolver(
        acceptance.path.parent,
        bundle.path.parent,
        fixture.locator_roots,
        eligibility,
    )
    return SyntheticChain(fixture, bundle, finalization, acceptance, resolver)
