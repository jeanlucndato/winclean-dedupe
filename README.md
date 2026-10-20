# dupe-sweep

**A safety-first duplicate file finder for Windows.** Find identical content, review what would be removed, and keep control of cleanup.

`dupe-sweep` scans common Windows user folders or locations you choose. It detects identical files by content rather than by filename and is designed to keep large scans resilient when files are locked, inaccessible, or changing.

## Highlights

- **Content-based matching:** size, a 64 KiB quick hash, then full-file SHA-256.
- **Windows-aware discovery:** resolves the six Known Folders, including OneDrive redirection.
- **Safe by default:** scans and `clean` previews never delete files. Cleanup requires `--delete` and a confirmation.
- **Recycle Bin cleanup:** selected copies go to the Recycle Bin; permanent deletion requires an additional typed confirmation.
- **Undo manifest:** each removed path records its SHA-256 and retained copy; `restore` can recreate a verified copy at its original path.
- **One copy always stays:** oldest, newest, shortest-path, or preferred-folder retention rules.
- **Useful exports:** CSV, JSON, and self-contained HTML reports with kept/duplicate labels.
- **Two interfaces:** a command-line tool and a Tkinter desktop app.
- **Resilient scans:** chunked hashing, thread-pool workers, symlink/junction skipping, hard-link handling, protected system locations, and logged I/O errors.

## Install

Requires Python 3.10 or newer. Windows 10/11 is the primary target; the scanning and reporting core is cross-platform-friendly.

```powershell
git clone <repository-url>
cd winclean-dedupe
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The editable install provides `dupe-sweep` and `dupe-sweep-gui` commands. The GUI requires a Python distribution that includes Tkinter.

## Use the CLI

```powershell
# Scan the six standard user folders (the default when no scope is specified)
dupe-sweep scan --default-folders

# Scan a chosen folder and export an HTML report
dupe-sweep scan --path "D:\Photos" --report html --output photos-report.html

# Include only large images, excluding thumbnails
dupe-sweep scan --path "D:\Photos" --images --min-size 1MB --exclude-ext .thumb

# Dry-run cleanup preview; this does not delete anything
dupe-sweep clean --default-folders --keep oldest

# Review a summary, then move duplicates to the Recycle Bin after confirmation
dupe-sweep clean --path "D:\Archive" --keep preferred-folder `
  --preferred-folder "D:\Archive\Master" --delete --report csv

# Scan mounted drives (system locations remain excluded)
dupe-sweep scan --all-drives --exclude "D:\Backups"

# Restore a removed copy from its verified kept copy using the manifest
dupe-sweep restore .\dupe-sweep-undo.json
```

`--path`, `--exclude`, `--ext`, and `--exclude-ext` can be repeated. Size suffixes include `KB`, `MB`, `GB`, and `TB`. `--include-empty` opts into matching zero-byte files. Keep rules are `oldest` (default), `newest`, `shortest-path`, and `preferred-folder`.

## Use the desktop app

Run `dupe-sweep-gui` or `python -m dupe_sweep.gui`. Add folders, scan, then use the checkboxes to select duplicate copies. The app marks the retained copy in each group and asks for confirmation before moving selected files to the Recycle Bin.

## How duplicate detection works

1. **Group by size.** Files with unique sizes cannot be duplicates and are skipped.
2. **Compare a quick hash.** Candidates are grouped by a hash of their first 64 KiB.
3. **Confirm the full contents.** Remaining candidates are read in bounded chunks and checked with SHA-256.

Names and extensions do not determine a match. Empty files are skipped by default. Symbolic links and junctions are not followed, and multiple paths to the same hard-linked file are collapsed to one filesystem identity.

## Safety and recovery

- Scanning only reads files. `clean` without `--delete` is a dry run.
- Before cleanup, the CLI prints groups, files to remove, and estimated recoverable bytes, then asks for confirmation.
- The cleaner verifies that both the retained copy and each candidate still match the duplicate digest immediately before removal.
- System locations (Windows, Program Files, ProgramData, AppData, Recycle Bin, and System Volume Information) are excluded, along with paths supplied through `--exclude`.
- Normal cleanup uses `send2trash`; permanent removal is an explicit opt-in requiring `--permanent` and typing `PERMANENT`.
- The JSON manifest records each removed file's original path, SHA-256, size, and kept copy. `dupe-sweep restore <manifest>` restores bytes from that verified kept copy and refuses to overwrite an existing path.
- Rotating logs are written to `logs/dupe-sweep.log`.

## Project structure

| Module | Responsibility |
| --- | --- |
| `folders.py`, `scanner.py` | Known Folders, protected paths, resilient traversal |
| `hasher.py`, `finder.py` | Staged hashing and duplicate groups |
| `rules.py`, `cleaner.py` | Retention choices, guarded removal, restore manifests |
| `filters.py`, `reports.py` | Scan filters and CSV/JSON/HTML output |
| `cli.py`, `gui.py` | Command-line and Tkinter interfaces |

## Screenshots

_Add a screenshot of the Tkinter results view here after a release build._

## Development and tests

```powershell
python -m pip install -e ".[dev]"
ruff check .
pytest -q
```

The test suite uses temporary directories and covers duplicate matching, non-matches, empty files, nesting, exclusions, mocked I/O errors, hard links, keep rules, dry-run safety, the one-copy guarantee, manifest restoration, filters, and report exports. GitHub Actions runs Ruff and pytest on Windows with Python 3.10, 3.11, and 3.12.

## License

MIT. See [LICENSE](LICENSE).
