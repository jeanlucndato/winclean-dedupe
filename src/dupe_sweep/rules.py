"""Duplicate-group retention policies."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .finder import DuplicateGroup


class KeepStrategy(str, Enum):
    """Supported rules for choosing the retained copy."""

    OLDEST = "oldest"
    NEWEST = "newest"
    SHORTEST_PATH = "shortest-path"
    PREFERRED_FOLDER = "preferred-folder"


def choose_keep(
    group: DuplicateGroup,
    strategy: KeepStrategy | str = KeepStrategy.OLDEST,
    preferred_folder: Path | None = None,
) -> Path:
    """Select exactly one file to retain from a non-empty duplicate group."""
    if not group.files:
        raise ValueError("Cannot choose a retained file from an empty group")
    strategy = KeepStrategy(strategy)
    if strategy is KeepStrategy.OLDEST:
        return min(group.files, key=lambda path: (_mtime(path), str(path).casefold()))
    if strategy is KeepStrategy.NEWEST:
        return max(group.files, key=lambda path: (_mtime(path), str(path).casefold()))
    if strategy is KeepStrategy.SHORTEST_PATH:
        return min(group.files, key=lambda path: (len(str(path)), str(path).casefold()))
    if preferred_folder is None:
        raise ValueError("preferred_folder is required for preferred-folder strategy")
    preferred = preferred_folder.resolve(strict=False)
    return min(
        group.files,
        key=lambda path: (
            not _is_within(path, preferred),
            _mtime(path),
            str(path).casefold(),
        ),
    )


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return float("inf")


def _is_within(path: Path, folder: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(folder)
        return True
    except (OSError, ValueError):
        return False
