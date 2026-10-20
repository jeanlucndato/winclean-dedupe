"""Tests for file discovery and staged duplicate detection."""

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from dupe_sweep.finder import find_duplicates
from dupe_sweep.scanner import walk_files


def test_identical_content_with_different_names_is_duplicate(tmp_path: Path) -> None:
    first = tmp_path / "one.bin"
    second = tmp_path / "renamed.dat"
    first.write_bytes(b"same content")
    second.write_bytes(b"same content")

    groups = find_duplicates([tmp_path])

    assert len(groups) == 1
    assert set(groups[0].files) == {first, second}
    assert groups[0].size == len(b"same content")


def test_same_size_different_content_is_not_duplicate(tmp_path: Path) -> None:
    (tmp_path / "one").write_bytes(b"alpha")
    (tmp_path / "two").write_bytes(b"bravo")

    assert find_duplicates([tmp_path]) == []


def test_empty_files_skipped_by_default_and_optionally_included(tmp_path: Path) -> None:
    (tmp_path / "one").touch()
    (tmp_path / "two").touch()

    assert find_duplicates([tmp_path]) == []
    assert len(find_duplicates([tmp_path], include_empty=True)) == 1


def test_nested_files_are_scanned(tmp_path: Path) -> None:
    nested = tmp_path / "folder" / "nested"
    nested.mkdir(parents=True)
    (tmp_path / "copy").write_text("nested content", encoding="utf-8")
    (nested / "source").write_text("nested content", encoding="utf-8")

    assert len(find_duplicates([tmp_path])) == 1


def test_exclusions_are_not_scanned(tmp_path: Path) -> None:
    included = tmp_path / "included"
    excluded = tmp_path / "excluded"
    included.mkdir()
    excluded.mkdir()
    (included / "a").write_text("content", encoding="utf-8")
    (excluded / "b").write_text("content", encoding="utf-8")

    files = list(walk_files([tmp_path], exclusions=[excluded]))

    assert files == [included / "a"]


def test_permission_errors_are_reported_and_scan_continues(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("content", encoding="utf-8")
    errors: list[OSError] = []

    def fail_on_walk(error: OSError) -> None:
        errors.append(error)

    real_walk = os.walk

    def mocked_walk(*args: object, **kwargs: object) -> Iterator[tuple[str, list[str], list[str]]]:
        onerror = kwargs["onerror"]
        onerror(PermissionError("mocked access denied"))
        yield from real_walk(*args, **kwargs)

    with patch("dupe_sweep.scanner.os.walk", side_effect=mocked_walk):
        files = list(walk_files([tmp_path], on_error=fail_on_walk))

    assert files == [tmp_path / "a"]
    assert isinstance(errors[0], PermissionError)


def test_hardlinks_are_not_reported_as_duplicates(tmp_path: Path) -> None:
    original = tmp_path / "original"
    alias = tmp_path / "alias"
    original.write_bytes(b"content")
    try:
        alias.hardlink_to(original)
    except OSError as error:
        pytest.skip(f"Hardlinks unavailable: {error}")

    assert find_duplicates([tmp_path]) == []
