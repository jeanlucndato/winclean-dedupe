"""Find duplicate files using size, quick hash, then full SHA-256."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .hasher import full_hash, hash_paths, quick_hash
from .scanner import walk_files

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DuplicateGroup:
    """A set of distinct files with identical content."""

    digest: str
    files: tuple[Path, ...]
    size: int


def find_duplicates(
    roots: list[Path],
    *,
    exclusions: tuple[Path, ...] = (),
    include_empty: bool = False,
    workers: int | None = None,
    on_error: Callable[[Path, OSError], None] | None = None,
    file_filter: Callable[[Path], bool] | None = None,
    on_file: Callable[[Path], None] | None = None,
) -> list[DuplicateGroup]:
    """Find duplicate files by content, skipping empty files and hardlink aliases."""
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in walk_files(roots, exclusions=exclusions):
        if on_file is not None:
            on_file(path)
        if file_filter is not None and not file_filter(path):
            continue
        try:
            stat = path.stat(follow_symlinks=False)
        except OSError as error:
            _handle_error(path, error, on_error)
            continue
        if stat.st_size == 0 and not include_empty:
            continue
        by_size[stat.st_size].append(path)

    groups: list[DuplicateGroup] = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        quick_groups = hash_paths(paths, quick_hash, workers=workers, on_error=on_error)
        for candidates in quick_groups.values():
            if len(candidates) < 2:
                continue
            full_groups = hash_paths(candidates, full_hash, workers=workers, on_error=on_error)
            for digest, matching in full_groups.items():
                distinct = _remove_hardlink_aliases(matching, on_error)
                if len(distinct) > 1:
                    groups.append(DuplicateGroup(digest, tuple(sorted(distinct)), size))
    return sorted(groups, key=lambda group: (str(group.files[0]).casefold(), group.digest))


def _remove_hardlink_aliases(
    paths: list[Path], on_error: Callable[[Path, OSError], None] | None
) -> list[Path]:
    """Keep one representative for each filesystem identity (device, inode)."""
    unique: dict[tuple[int, int], Path] = {}
    for path in paths:
        try:
            stat = path.stat(follow_symlinks=False)
        except OSError as error:
            _handle_error(path, error, on_error)
            continue
        unique.setdefault((stat.st_dev, stat.st_ino), path)
    return list(unique.values())


def _handle_error(
    path: Path, error: OSError, on_error: Callable[[Path, OSError], None] | None
) -> None:
    if on_error:
        on_error(path, error)
    else:
        LOGGER.warning("Could not inspect %s: %s", path, error)
