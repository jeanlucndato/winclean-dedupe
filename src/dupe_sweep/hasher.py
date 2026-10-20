"""Memory-bounded staged content hashing."""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from pathlib import Path

LOGGER = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024
QUICK_HASH_SIZE = 64 * 1024
HashResult = tuple[Path, str]


def quick_hash(path: Path, sample_size: int = QUICK_HASH_SIZE) -> str:
    """Hash the first sample_size bytes for a fast candidate comparison."""
    digest = hashlib.blake2b(digest_size=16)
    with path.open("rb") as file:
        digest.update(file.read(sample_size))
    return digest.hexdigest()


def full_hash(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    """Hash a file with SHA-256 without loading it into memory at once."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def hash_paths(
    paths: list[Path],
    hasher: Callable[[Path], str],
    *,
    workers: int | None = None,
    on_error: Callable[[Path, OSError], None] | None = None,
) -> dict[str, list[Path]]:
    """Hash paths concurrently, logging and skipping inaccessible files."""
    groups: dict[str, list[Path]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(hasher, path): path for path in paths}
        try:
            for future in as_completed(futures):
                path = futures[future]
                try:
                    value = future.result()
                except OSError as error:
                    if on_error:
                        on_error(path, error)
                    else:
                        LOGGER.warning("Could not hash %s: %s", path, error)
                    continue
                groups.setdefault(value, []).append(path)
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            raise
    return groups
