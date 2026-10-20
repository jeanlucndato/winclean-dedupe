# dupe-sweep

**Find duplicate files by their contents. Keep control of every cleanup.**

`dupe-sweep` is a Windows-first Python utility for locating duplicate files in common user folders. It compares file contents rather than names, so renamed copies are still found. The project is being built in safety-first phases; the current release implements folder discovery and duplicate detection. Cleanup and the graphical interface are on the roadmap.

## Why this project

Duplicate files quietly consume storage and are easy to remove incorrectly. `dupe-sweep` is designed around a simple principle: make matches explainable, keep scans resilient, and require deliberate user action before cleanup is introduced.

## Current capabilities

- Resolves Windows Known Folders (including redirected folders such as OneDrive) with sensible home-directory fallbacks.
- Scans the standard user folders: Downloads, Pictures, Documents, Desktop, Music, and Videos.
- Skips symbolic links, excluded paths, and hard-link aliases.
- Finds matches through three stages: file size, a 64 KiB quick hash, then a full SHA-256 digest.
- Hashes files in bounded chunks using a thread pool; inaccessible files are logged and skipped.
- Skips empty files by default, with an option in the core API to include them.
- Includes pytest coverage for renamed copies, same-size non-matches, nested files, empty files, exclusions, mocked permission errors, and hard links.

> **Project status:** Phase 1 (discovery and duplicate-finding foundation) is implemented. There is not yet a CLI, deletion workflow, report exporter, or GUI. Those are planned phases, not current features.

## Quick start

Requires Python 3.10 or newer. Phase 1 exposes a Python API; the command-line entry point will arrive in a later phase.

```powershell
git clone <repository-url>
cd dupe-sweep
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install pytest
$env:PYTHONPATH = "src"
pytest
```

Example from Python:

```python
from pathlib import Path

from dupe_sweep.finder import find_duplicates
from dupe_sweep.folders import discover_user_folders, protected_paths

groups = find_duplicates(
    discover_user_folders(),
    exclusions=tuple(protected_paths()),
)

for group in groups:
    print(f"{len(group.files)} copies · {group.size:,} bytes · SHA-256 {group.digest}")
    for path in group.files:
        print(f"  {path}")
```

## How matching works

1. **Size:** files are grouped by byte length. Unique sizes need no hashing.
2. **Quick comparison:** candidates are compared using a hash of their first 64 KiB.
3. **Confirmation:** remaining candidates are read in chunks and compared by full SHA-256.

Every reported group therefore contains files with identical full-file content. File names do not affect matching. The scanner does not follow symbolic links, and files sharing the same device and inode are treated as hard-link aliases rather than separate copies.

## Safety design

The current phase only reads and hashes files; it does not delete or modify them. Later cleanup work is planned to default to dry-run, move selected files to the Recycle Bin, require confirmation, preserve at least one copy per group, and write a JSON undo manifest. Those protections will be implemented and tested before cleanup is exposed.

System locations are excluded through the `protected_paths()` helper. The scanner also accepts explicit exclusions, enabling callers to avoid additional directories.

## Screenshots

_GUI screenshots will be added after the Tkinter interface is implemented._

## Roadmap

- [x] Phase 1 — known-folder discovery, resilient scanner, staged hashing, duplicate groups, tests
- [ ] Phase 2 — keep rules, safe cleanup, undo manifest, and CLI
- [ ] Phase 3 — CSV, JSON, and HTML reports; rotating logs; size and type filters
- [ ] Phase 4 — Tkinter interface with grouped results and cleanup controls
- [ ] Phase 5 — packaging, Windows CI, final documentation and release polish

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
