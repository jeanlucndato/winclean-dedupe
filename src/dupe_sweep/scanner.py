"""Resilient, symlink-safe file discovery."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

LOGGER = logging.getLogger(__name__)
ErrorHandler = Callable[[OSError], None]


def _log_walk_error(error: OSError) -> None:
    LOGGER.warning("Could not scan %s: %s", getattr(error, "filename", "<unknown>"), error)


def walk_files(
    roots: Iterable[Path],
    *,
    exclusions: Iterable[Path] = (),
    on_error: ErrorHandler | None = None,
) -> Iterator[Path]:
    """Yield regular files under roots, skipping links and excluded directories."""
    excluded = tuple(exclusions)
    error_handler = on_error or _log_walk_error
    visited: set[tuple[int, int]] = set()
    for root in roots:
        if any(_is_within(root, exclusion) for exclusion in excluded):
            continue
        try:
            root_stat = root.stat(follow_symlinks=False)
            if _is_link_or_junction(root) or not root.is_dir():
                continue
            identity = (root_stat.st_dev, root_stat.st_ino)
            if identity in visited:
                continue
            visited.add(identity)
        except OSError as error:
            error_handler(error)
            continue
        for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False, onerror=error_handler):
            current_path = Path(current)
            filtered: list[str] = []
            for dirname in dirnames:
                candidate = current_path / dirname
                try:
                    if _is_link_or_junction(candidate) or any(
                        _is_within(candidate, exclusion) for exclusion in excluded
                    ):
                        continue
                    filtered.append(dirname)
                except OSError as error:
                    error_handler(error)
            dirnames[:] = filtered
            if any(_is_within(current_path, exclusion) for exclusion in excluded):
                continue
            for filename in filenames:
                candidate = current_path / filename
                try:
                    if _is_link_or_junction(candidate) or not candidate.is_file():
                        continue
                    yield candidate
                except OSError as error:
                    error_handler(error)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _is_link_or_junction(path: Path) -> bool:
    """Check for symbolic links and, on newer Python, Windows junctions."""
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except OSError:
        return True
