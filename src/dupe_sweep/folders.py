"""Windows known-folder discovery and protected scan locations."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

KNOWN_FOLDER_NAMES: tuple[str, ...] = (
    "Downloads",
    "Pictures",
    "Documents",
    "Desktop",
    "Music",
    "Videos",
)


def _windows_known_folder(name: str) -> Path | None:
    """Resolve a Windows Known Folder, including redirected/OneDrive folders."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        identifiers = {
            "Desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
            "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
            "Downloads": "374DE290-123F-4565-9164-39C4925E467B",
            "Music": "4BD8D571-6D19-48D3-BE97-422220080E43",
            "Pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
            "Videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
        }
        guid = GUID.from_buffer_copy(_guid_bytes(identifiers[name]))
        result = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(result)):
            return None
        try:
            return Path(result.value) if result.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(result)
    except (AttributeError, OSError, ValueError, KeyError):
        return None


def _guid_bytes(value: str) -> bytes:
    """Convert a GUID string to the Windows in-memory GUID byte layout."""
    import uuid

    return uuid.UUID(value).bytes_le


def discover_user_folders(home: Path | None = None) -> list[Path]:
    """Return existing default user folders, resolving Windows known folders first."""
    home_dir = (home or Path.home()).expanduser()
    paths: list[Path] = []
    for name in KNOWN_FOLDER_NAMES:
        candidate = _windows_known_folder(name) or home_dir / name
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            resolved = candidate
        if resolved.is_dir() and resolved not in paths:
            paths.append(resolved)
    return paths


def protected_paths() -> list[Path]:
    """Return locations that must never be traversed on Windows."""
    if os.name != "nt":
        return []
    drive = os.environ.get("SystemDrive", "C:")
    system_drive = Path(drive + "\\" if drive.endswith(":") else drive)
    windows = Path(os.environ.get("WINDIR", str(system_drive / "Windows")))
    program_files = Path(os.environ.get("ProgramFiles", str(system_drive / "Program Files")))
    program_files_x86 = Path(
        os.environ.get("ProgramFiles(x86)", str(system_drive / "Program Files (x86)"))
    )
    program_data = Path(os.environ.get("ProgramData", str(system_drive / "ProgramData")))
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    candidates = [
        windows,
        program_files,
        program_files_x86,
        program_data,
        user_profile / "AppData",
        system_drive / "$Recycle.Bin",
        system_drive / "System Volume Information",
    ]
    return [path for path in candidates]


def is_excluded(path: Path, exclusions: Iterable[Path]) -> bool:
    """Return whether path is equal to or nested under an excluded location."""
    try:
        resolved_path = path.resolve(strict=False)
    except OSError:
        resolved_path = path
    for exclusion in exclusions:
        try:
            resolved_exclusion = exclusion.resolve(strict=False)
            resolved_path.relative_to(resolved_exclusion)
            return True
        except (OSError, ValueError):
            continue
    return False
