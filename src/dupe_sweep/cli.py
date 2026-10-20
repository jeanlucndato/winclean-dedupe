"""Command-line interface for dupe-sweep."""

from __future__ import annotations

import argparse
import logging
import string
import sys
from collections.abc import Sequence
from pathlib import Path

from .cleaner import clean_duplicates, restore_manifest
from .finder import find_duplicates
from .filters import CATEGORIES, FileFilters, parse_extensions
from .folders import discover_user_folders, protected_paths
from .logging_config import configure_logging
from .reports import export_report
from .rules import KeepStrategy, choose_keep

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the dupe-sweep command parser."""
    parser = argparse.ArgumentParser(prog="dupe-sweep", description="Find duplicate files by content.")
    parser.add_argument("--version", action="version", version="dupe-sweep 0.1.0")
    commands = parser.add_subparsers(dest="command")
    for command in ("scan", "clean"):
        subparser = commands.add_parser(command, help=f"{command.title()} for duplicate files")
        _add_scan_arguments(subparser)
        if command == "clean":
            subparser.add_argument("--delete", action="store_true", help="Move confirmed duplicates to the Recycle Bin")
            subparser.add_argument("--permanent", action="store_true", help="Permanently delete after an extra typed confirmation")
            subparser.add_argument("--manifest", type=Path, help="Undo manifest path")
    restore = commands.add_parser("restore", help="Restore original paths using an undo manifest")
    restore.add_argument("manifest", type=Path)
    return parser


def _add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--default-folders", action="store_true", help="Scan the six standard user folders")
    parser.add_argument("--path", action="append", type=Path, default=[], help="Additional folder to scan (repeatable)")
    parser.add_argument("--all-drives", action="store_true", help="Scan mounted drive roots")
    parser.add_argument("--exclude", action="append", type=Path, default=[], help="Additional excluded path")
    parser.add_argument("--include-empty", action="store_true", help="Include zero-byte files")
    parser.add_argument("--keep", choices=[strategy.value for strategy in KeepStrategy], default="oldest")
    parser.add_argument("--preferred-folder", type=Path, help="Preferred location when --keep preferred-folder is used")
    parser.add_argument("--min-size", type=_size_argument, help="Minimum file size, e.g. 10MB")
    parser.add_argument("--max-size", type=_size_argument, help="Maximum file size, e.g. 2GB")
    parser.add_argument("--ext", action="append", help="Include extension(s), comma-separated (e.g. .jpg,.png)")
    parser.add_argument("--exclude-ext", action="append", help="Exclude extension(s), comma-separated")
    for category in CATEGORIES:
        parser.add_argument(f"--{category}", action="store_true", help=f"Only scan {category}")
    parser.add_argument("--report", choices=("csv", "json", "html"), help="Export scan results")
    parser.add_argument("--output", type=Path, help="Report destination")
    parser.add_argument("--workers", type=int, help="Hashing thread count")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line application."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "restore":
        try:
            restored = restore_manifest(args.manifest)
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))
        print(f"Restored {len(restored)} file(s).")
        return 0
    if args.command == "clean" and args.permanent and not args.delete:
        parser.error("--permanent requires --delete")
    if args.keep == KeepStrategy.PREFERRED_FOLDER.value and not args.preferred_folder:
        parser.error("--keep preferred-folder requires --preferred-folder")
    if args.min_size is not None and args.max_size is not None and args.min_size > args.max_size:
        parser.error("--min-size cannot exceed --max-size")
    log_path = configure_logging()
    roots = _resolve_roots(args, parser)
    exclusions = tuple(protected_paths() + [path.expanduser() for path in args.exclude])
    filters = FileFilters(
        min_size=args.min_size,
        max_size=args.max_size,
        extensions=parse_extensions(args.ext),
        excluded_extensions=parse_extensions(args.exclude_ext),
        categories=frozenset(name for name in CATEGORIES if getattr(args, name)),
    )
    scan_count = 0

    def progress(_path: Path) -> None:
        nonlocal scan_count
        scan_count += 1
        print(f"\rFiles scanned: {scan_count:,}", end="", flush=True)

    print(f"Scanning {len(roots)} location(s)…")
    try:
        groups = find_duplicates(
            roots,
            exclusions=exclusions,
            include_empty=args.include_empty,
            workers=args.workers,
            file_filter=filters.matches if _has_filters(filters) else None,
            on_file=progress,
        )
    except KeyboardInterrupt:
        print("\nScan cancelled.")
        return 130
    print()
    for index, group in enumerate(groups, start=1):
        kept = choose_keep(group, args.keep, args.preferred_folder)
        print(f"\nGroup {index}: {len(group.files)} copies · {group.size:,} bytes · SHA-256 {group.digest}")
        for path in group.files:
            role = "KEEP" if path == kept else "DUPLICATE"
            print(f"  [{role}] {path}")

    if args.report:
        destination = args.output or Path(f"dupe-sweep-report.{args.report}")
        export_report(groups, destination, format=args.report, strategy=args.keep, preferred_folder=args.preferred_folder)
        print(f"Report: {destination.resolve()}")

    if args.command == "clean":
        preview = clean_duplicates(groups, strategy=args.keep, preferred_folder=args.preferred_folder)
        print(
            f"\nCleanup summary: {preview.groups} groups, {preview.files_removed} files to remove, "
            f"{preview.bytes_freed:,} bytes recoverable."
        )
        if not args.delete:
            print("Dry run only. Pass --delete to move files to the Recycle Bin.")
        else:
            if args.permanent:
                answer = input("Type PERMANENT to permanently delete these files: ")
                if answer != "PERMANENT":
                    print("Cancelled.")
                    return 0
            else:
                answer = input("Move these duplicate files to the Recycle Bin? [y/N] ")
                if answer.strip().lower() != "y":
                    print("Cancelled.")
                    return 0
            try:
                result = clean_duplicates(
                    groups,
                    strategy=args.keep,
                    preferred_folder=args.preferred_folder,
                    delete=True,
                    confirmed=True,
                    permanent=args.permanent,
                    manifest_path=args.manifest,
                )
            except (RuntimeError, OSError, ValueError) as error:
                LOGGER.exception("Cleanup failed")
                print(f"Cleanup failed: {error}", file=sys.stderr)
                return 1
            print(f"Moved {result.files_removed} file(s). Undo manifest: {result.manifest}")
    print(f"\nSummary: {scan_count:,} files scanned, {len(groups)} duplicate group(s), "
          f"{sum(group.size * (len(group.files) - 1) for group in groups):,} bytes recoverable.")
    print(f"Log: {log_path}")
    return 0


def _resolve_roots(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Path]:
    roots = [path.expanduser() for path in args.path]
    if args.default_folders or (not args.path and not args.all_drives):
        roots.extend(discover_user_folders())
    if args.all_drives:
        if sys.platform == "win32":
            roots.extend(Path(f"{drive}:\\") for drive in string.ascii_uppercase if Path(f"{drive}:\\").exists())
        else:
            parser.error("--all-drives is supported on Windows only")
    roots = list(dict.fromkeys(roots))
    roots = [path for path in roots if path.exists() and path.is_dir()]
    if not roots:
        parser.error("No readable scan locations found. Use --path, --default-folders, or --all-drives.")
    return roots


def _size_argument(value: str) -> int:
    """Parse a byte size supporting KB, MB, GB, and TB suffixes."""
    normalized = value.strip().upper().replace("IB", "B")
    units = {"B": 1, "K": 1024, "KB": 1024, "M": 1024**2, "MB": 1024**2,
             "G": 1024**3, "GB": 1024**3, "T": 1024**4, "TB": 1024**4}
    suffix = next((unit for unit in sorted(units, key=len, reverse=True) if normalized.endswith(unit)), "B")
    number = normalized[: -len(suffix)] if suffix != "B" else normalized
    try:
        result = int(float(number.strip())) * units[suffix]
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Invalid size: {value}") from error
    if result < 0:
        raise argparse.ArgumentTypeError("Size cannot be negative")
    return result


def _has_filters(filters: FileFilters) -> bool:
    return bool(filters.min_size is not None or filters.max_size is not None or filters.extensions
                or filters.excluded_extensions or filters.categories)


if __name__ == "__main__":
    raise SystemExit(main())
