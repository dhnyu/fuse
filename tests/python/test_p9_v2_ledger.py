from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import canonical_json_bytes  # noqa: E402
from p9_v2_ledger import (  # noqa: E402
    GENESIS_HASH,
    LedgerClosedError,
    LedgerCorruptionError,
    LedgerWriter,
    UncommittedStagingError,
    read_ledger,
    read_tail_hint,
)
from p9_v2_test_support import (  # noqa: E402
    RUN_ID,
    append_event,
    append_start,
    initialized_writer,
)


def test_initialize_creates_empty_canonical_ledger(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    committed = read_ledger(writer.root)
    assert committed.header["run_id"] == RUN_ID
    assert committed.events == ()
    assert committed.last_sequence == 0
    assert committed.last_event_hash == GENESIS_HASH
    assert not committed.closed
    assert read_tail_hint(writer.root, committed) is None


def test_append_reopen_append_preserves_chain_continuity(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    append_event(writer, "RUN_AUTHORIZED")
    reopened = LedgerWriter(writer.root)
    append_event(reopened, "RUN_STARTING")
    committed = read_ledger(writer.root)
    assert [event["event_sequence"] for event in committed.events] == [1, 2]
    assert committed.events[1]["previous_event_hash"] == committed.events[0]["event_hash"]
    assert read_tail_hint(writer.root, committed)["last_sequence"] == 2


def test_one_event_segment_filename_and_trailing_newline(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    append_start(writer)
    paths = sorted((writer.root / "segments").iterdir())
    assert [path.name for path in paths] == [
        "000000000001-000000000001.jsonl",
        "000000000002-000000000002.jsonl",
        "000000000003-000000000003.jsonl",
    ]
    assert all(path.read_bytes().endswith(b"\n") for path in paths)
    assert all(path.read_bytes().count(b"\n") == 1 for path in paths)


def test_close_is_create_or_validate_and_prevents_append(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    append_start(writer)
    first = writer.close()
    first_bytes = first.read_bytes()
    assert writer.close() == first
    assert first.read_bytes() == first_bytes
    assert read_ledger(writer.root).closed
    with pytest.raises(LedgerClosedError):
        append_event(writer, "EPOCH_STARTED")


def test_existing_header_is_create_or_validate(tmp_path):
    root = tmp_path / "ledger"
    initialized_writer(root)
    same = LedgerWriter.initialize(root, run_id=RUN_ID, created_at="2026-08-31T00:00:00Z")
    assert same.header["run_id"] == RUN_ID
    with pytest.raises(LedgerCorruptionError, match="header differs"):
        LedgerWriter.initialize(root, run_id=RUN_ID, created_at="2026-09-01T00:00:00Z")


def test_staging_debris_is_non_authoritative_and_quarantined(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    append_event(writer, "RUN_AUTHORIZED")
    debris = writer.root / ".staging" / "000000000002-000000000002.jsonl.incomplete"
    debris.write_bytes(b'{"torn":')
    assert read_ledger(writer.root).last_sequence == 1
    with pytest.raises(UncommittedStagingError):
        append_event(writer, "RUN_STARTING")
    reopened = LedgerWriter.reopen_after_crash(writer.root)
    assert not debris.exists()
    assert list((writer.root / ".debris").iterdir())
    append_event(reopened, "RUN_STARTING")
    assert read_ledger(writer.root).last_sequence == 2


@pytest.mark.parametrize("tail_bytes", [b'{"torn":', b'{}', canonical_json_bytes({"stale": True})])
def test_stale_or_corrupt_tail_never_changes_canonical_replay(tmp_path, tail_bytes):
    writer = initialized_writer(tmp_path / "ledger")
    append_start(writer)
    expected = read_ledger(writer.root)
    (writer.root / "tail.json").write_bytes(tail_bytes)
    assert read_tail_hint(writer.root, expected) is None
    actual = read_ledger(writer.root)
    assert actual.events == expected.events


def test_unexpected_entry_in_committed_segment_directory_is_corruption(tmp_path):
    writer = initialized_writer(tmp_path / "ledger")
    append_event(writer, "RUN_AUTHORIZED")
    (writer.root / "segments" / "README").write_text("not evidence", encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="unexpected committed segment"):
        read_ledger(writer.root)
