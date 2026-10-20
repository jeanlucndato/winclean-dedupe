"""Tests for keep rules and guarded cleanup."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from dupe_sweep.cleaner import clean_duplicates, restore_manifest
from dupe_sweep.finder import DuplicateGroup
from dupe_sweep.hasher import full_hash
from dupe_sweep.rules import KeepStrategy, choose_keep


@pytest.fixture
def duplicate_group(tmp_path: Path) -> DuplicateGroup:
    older = tmp_path / "older-copy"
    newer = tmp_path / "newer-copy"
    older.write_bytes(b"identical")
    newer.write_bytes(b"identical")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    return DuplicateGroup(full_hash(older), (older, newer), older.stat().st_size)


def test_keep_oldest_and_newest(duplicate_group: DuplicateGroup) -> None:
    assert choose_keep(duplicate_group, KeepStrategy.OLDEST) == duplicate_group.files[0]
    assert choose_keep(duplicate_group, KeepStrategy.NEWEST) == duplicate_group.files[1]


def test_keep_shortest_path(duplicate_group: DuplicateGroup) -> None:
    assert choose_keep(duplicate_group, KeepStrategy.SHORTEST_PATH) == min(
        duplicate_group.files, key=lambda path: (len(str(path)), str(path).casefold())
    )


def test_dry_run_never_deletes(duplicate_group: DuplicateGroup, tmp_path: Path) -> None:
    result = clean_duplicates([duplicate_group], manifest_path=tmp_path / "undo.json")

    assert result.files_removed == 1
    assert all(path.exists() for path in duplicate_group.files)
    assert not (tmp_path / "undo.json").exists()


def test_deletion_requires_explicit_confirmation(duplicate_group: DuplicateGroup) -> None:
    with pytest.raises(ValueError, match="confirmation"):
        clean_duplicates([duplicate_group], delete=True)


def test_confirmed_cleanup_never_removes_last_copy(
    duplicate_group: DuplicateGroup, tmp_path: Path
) -> None:
    removed_path = duplicate_group.files[1]
    with patch("send2trash.send2trash", side_effect=lambda value: Path(value).unlink()):
        result = clean_duplicates(
            [duplicate_group], delete=True, confirmed=True, manifest_path=tmp_path / "undo.json"
        )

    assert result.files_removed == 1
    assert duplicate_group.files[0].exists()
    assert not removed_path.exists()
    manifest = json.loads((tmp_path / "undo.json").read_text(encoding="utf-8"))
    assert manifest["removed_files"][0]["kept_copy"] == str(duplicate_group.files[0])


def test_restore_manifest_recreates_verified_copy(
    duplicate_group: DuplicateGroup, tmp_path: Path
) -> None:
    removed = duplicate_group.files[1]
    manifest = tmp_path / "undo.json"
    manifest.write_text(
        json.dumps({"removed_files": [{
            "original_path": str(removed),
            "kept_copy": str(duplicate_group.files[0]),
            "sha256": duplicate_group.digest,
        }]}),
        encoding="utf-8",
    )

    assert restore_manifest(manifest) == [removed]
    assert full_hash(removed) == duplicate_group.digest
