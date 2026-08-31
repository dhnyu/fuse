from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import canonical_json_bytes, canonical_json_line, canonical_sha256, deterministic_id  # noqa: E402
from p9_v2_ledger import LedgerCorruptionError, LedgerError, LedgerWriter, read_ledger  # noqa: E402
from p9_v2_replay import replay_ledger  # noqa: E402
from p9_v2_test_support import (  # noqa: E402
    RUN_ID,
    append_event,
    append_start,
    initialized_writer,
    payload,
)


PRECOMMIT_FAULTS = [
    "before_staging_file_creation",
    "after_staging_creation_before_write",
    "during_stage_write",
    "after_write_before_file_fsync",
    "after_file_fsync_before_verification",
    "after_verification_before_rename",
]
COMMITTED_FAULTS = [
    "after_rename_before_directory_fsync",
    "after_directory_fsync_before_tail_cache",
    "during_tail_cache_replacement",
]


def _raising_fault(point):
    def fault(actual):
        if actual == point:
            raise RuntimeError(point)
    return fault


@pytest.mark.parametrize("point", PRECOMMIT_FAULTS + COMMITTED_FAULTS)
def test_append_crash_boundary_is_zero_or_one_commit(tmp_path, point):
    writer = initialized_writer(tmp_path / point)
    append_start(writer)
    with pytest.raises(RuntimeError, match=point):
        writer.append(
            event_type="EPOCH_STARTED",
            occurred_at="2026-08-31T00:00:04Z",
            writer_id="synthetic-rank0",
            writer_role="rank0",
            payload=payload("EPOCH_STARTED"),
            fault=_raising_fault(point),
        )
    after_crash = read_ledger(writer.root)
    expected = 3 if point in PRECOMMIT_FAULTS else 4
    assert after_crash.last_sequence == expected
    assert len(after_crash.events) == expected
    reopened = LedgerWriter.reopen_after_crash(writer.root)
    if expected == 3:
        append_event(reopened, "EPOCH_STARTED")
    else:
        append_event(reopened, "UPDATE_COMMITTED")
    final = read_ledger(writer.root)
    assert final.last_sequence == expected + 1
    assert len({event["event_id"] for event in final.events}) == len(final.events)


@pytest.mark.parametrize(
    ("point", "closed_after_crash"),
    [("during_closed_manifest_publication", False), ("after_manifest_rename_before_directory_fsync", True)],
)
def test_closed_manifest_crash_boundary_is_zero_or_one_commit(tmp_path, point, closed_after_crash):
    writer = initialized_writer(tmp_path / point)
    append_start(writer)
    with pytest.raises(RuntimeError, match=point):
        writer.close(fault=_raising_fault(point))
    assert read_ledger(writer.root).closed is closed_after_crash
    reopened = LedgerWriter.reopen_after_crash(writer.root)
    manifest = reopened.close()
    assert manifest.is_file()
    assert read_ledger(writer.root).closed


def _segment(root: Path, sequence: int) -> Path:
    return root / "segments" / f"{sequence:012d}-{sequence:012d}.jsonl"


def _read_event(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rehash(event):
    envelope = {key: value for key, value in event.items() if key not in {"event_id", "event_hash"}}
    event["event_id"] = deterministic_id("p9evt_", envelope)
    event["event_hash"] = canonical_sha256({key: value for key, value in event.items() if key != "event_hash"})
    return event


def _rewrite(path: Path, event):
    path.write_bytes(canonical_json_line(_rehash(event)))


@pytest.mark.parametrize("mutation", ["truncate", "noncanonical", "random_byte"])
def test_torn_or_corrupt_committed_segment_is_rejected(tmp_path, mutation):
    writer = initialized_writer(tmp_path / mutation)
    append_start(writer)
    path = _segment(writer.root, 2)
    raw = path.read_bytes()
    if mutation == "truncate":
        path.write_bytes(raw[: len(raw) // 2])
    elif mutation == "noncanonical":
        path.write_text(json.dumps(_read_event(path), indent=2) + "\n", encoding="utf-8")
    else:
        changed = bytearray(raw)
        changed[len(changed) // 2] ^= 1
        path.write_bytes(bytes(changed))
    with pytest.raises(LedgerError):
        read_ledger(writer.root)


def test_missing_duplicate_and_reordered_sequences_are_rejected(tmp_path):
    for mutation in ("missing", "duplicate", "reordered"):
        root = tmp_path / mutation
        writer = initialized_writer(root)
        append_start(writer)
        one, two, three = (_segment(root, index) for index in (1, 2, 3))
        if mutation == "missing":
            two.unlink()
        elif mutation == "duplicate":
            shutil.copyfile(one, two)
        else:
            left, right = two.read_bytes(), three.read_bytes()
            two.write_bytes(right)
            three.write_bytes(left)
        with pytest.raises(LedgerCorruptionError):
            read_ledger(root)


@pytest.mark.parametrize(
    "mutation",
    ["previous_hash", "event_hash", "another_run", "writer_role", "schema_version", "payload"],
)
def test_structural_single_field_corruption_is_rejected(tmp_path, mutation):
    writer = initialized_writer(tmp_path / mutation)
    append_start(writer)
    path = _segment(writer.root, 2)
    event = _read_event(path)
    if mutation == "previous_hash":
        event["previous_event_hash"] = "0" * 64
        _rewrite(path, event)
    elif mutation == "event_hash":
        event["event_hash"] = "0" * 64
        path.write_bytes(canonical_json_line(event))
    elif mutation == "another_run":
        event["run_id"] = "p9runv2_" + "f" * 24
        _rewrite(path, event)
    elif mutation == "writer_role":
        event["writer"]["role"] = "publisher"
        _rewrite(path, event)
    elif mutation == "schema_version":
        event["schema_version"] = "3.0.0"
        _rewrite(path, event)
    else:
        event["payload"].pop("owner_id")
        _rewrite(path, event)
    with pytest.raises(LedgerError):
        read_ledger(writer.root)


def test_manifest_segment_hash_mismatch_is_canonical_corruption(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    append_start(writer)
    manifest_path = writer.close()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["segments"][0]["sha256"] = "0" * 64
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(LedgerCorruptionError, match="manifest does not match"):
        read_ledger(writer.root)


def test_extra_staging_and_corrupt_tail_are_ignored_by_canonical_replay(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    append_start(writer)
    (writer.root / ".staging" / "unknown.incomplete").write_bytes(b"torn")
    (writer.root / "tail.json").write_bytes(b'{"broken":')
    result = replay_ledger(writer.root)
    assert result.last_committed_sequence == 3
    assert result.operational_state == "RUNNING"


def test_fixed_seed_random_single_field_corruption_is_always_rejected(tmp_path):
    randomizer = random.Random(20260831)
    for case in range(100):
        root = tmp_path / f"case-{case:03d}"
        writer = initialized_writer(root)
        append_start(writer)
        sequence = randomizer.randint(1, 3)
        path = _segment(root, sequence)
        event = _read_event(path)
        field = randomizer.choice(["event_sequence", "run_id", "previous_event_hash", "occurred_at"])
        if field == "event_sequence":
            event[field] += randomizer.randint(1, 7)
        elif field == "run_id":
            event[field] = "p9runv2_" + "e" * 24
        elif field == "previous_event_hash":
            event[field] = "f" * 64
        else:
            event[field] = "2026-08-31T00:00:00+09:00"
        _rewrite(path, event)
        with pytest.raises(LedgerCorruptionError):
            read_ledger(root)
