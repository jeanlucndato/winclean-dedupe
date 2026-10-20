"""Guarded duplicate cleanup and copy-based undo-manifest restoration."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from .finder import DuplicateGroup
from .hasher import full_hash
from .rules import KeepStrategy, choose_keep

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupResult:
    """Summary of a cleanup attempt."""

    groups: int
    files_removed: int
    bytes_freed: int
    removed: tuple[Path, ...]
    manifest: Path | None


def clean_duplicates(
    groups: list[DuplicateGroup],
    *,
    strategy: KeepStrategy | str = KeepStrategy.OLDEST,
    preferred_folder: Path | None = None,
    delete: bool = False,
    confirmed: bool = False,
    permanent: bool = False,
    manifest_path: Path | None = None,
    selected_removals: set[Path] | None = None,
) -> CleanupResult:
    """Preview cleanup by default; remove only confirmed, verified copies."""
    plans: list[tuple[DuplicateGroup, Path, list[Path]]] = []
    for group in groups:
        if len(group.files) < 2:
            continue
        keep = choose_keep(group, strategy, preferred_folder)
        remove = [path for path in group.files if path != keep]
        if selected_removals is not None:
            remove = [path for path in remove if path in selected_removals]
        plans.append((group, keep, remove))

    files = [path for _, _, removal in plans for path in removal]
    total_size = sum(_file_size(path) for path in files)
    if not delete:
        return CleanupResult(len(plans), len(files), total_size, (), None)
    if not confirmed:
        raise ValueError("Deletion requires explicit confirmation")
    if permanent and not confirmed:
        raise ValueError("Permanent deletion requires explicit confirmation")

    try:
        trash = None
        if not permanent:
            from send2trash import send2trash as trash
    except ImportError as error:
        raise RuntimeError("Recycle Bin cleanup requires the send2trash package") from error

    manifest = manifest_path or Path.cwd() / "dupe-sweep-undo.json"
    manifest_payload: dict[str, object] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "permanent": permanent,
        "removed_files": [],
    }
    if files:
        if manifest.exists():
            raise FileExistsError(f"Undo manifest already exists; choose another path: {manifest}")
        _write_manifest(manifest, manifest_payload)

    entries: list[dict[str, str | int]] = []
    removed: list[Path] = []
    removed_bytes = 0
    for group, keep, candidates in plans:
        if not keep.exists() or full_hash(keep) != group.digest:
            LOGGER.warning("Skipping group because retained copy changed: %s", keep)
            continue
        for path in candidates:
            try:
                if not path.is_file() or full_hash(path) != group.digest:
                    LOGGER.warning("Skipping changed or missing duplicate: %s", path)
                    continue
                size = path.stat().st_size
                entry = {
                    "original_path": str(path.resolve(strict=False)),
                    "sha256": group.digest,
                    "kept_copy": str(keep.resolve(strict=False)),
                    "size": size,
                }
                if permanent:
                    path.unlink()
                else:
                    assert trash is not None
                    trash(str(path))
                entries.append(entry)
                removed.append(path)
                removed_bytes += size
                manifest_payload["removed_files"] = entries
                _write_manifest(manifest, manifest_payload)
            except OSError as error:
                LOGGER.warning("Could not remove %s: %s", path, error)

    if not entries and files:
        manifest.unlink(missing_ok=True)
    return CleanupResult(len(plans), len(removed), removed_bytes, tuple(removed), manifest if entries else None)


def restore_manifest(manifest_path: Path) -> list[Path]:
    """Restore removed paths by copying verified bytes from each kept copy."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[Path] = []
    for entry in payload.get("removed_files", []):
        original = Path(entry["original_path"])
        kept = Path(entry["kept_copy"])
        expected = str(entry["sha256"])
        if original.exists():
            raise FileExistsError(f"Refusing to overwrite existing path: {original}")
        if not kept.is_file() or full_hash(kept) != expected:
            raise OSError(f"Kept copy is missing or has changed: {kept}")
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(kept, original)
        if full_hash(original) != expected:
            original.unlink(missing_ok=True)
            raise OSError(f"Restored copy failed hash verification: {original}")
        restored.append(original)
    return restored


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    """Atomically persist the undo record before and during cleanup."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)
