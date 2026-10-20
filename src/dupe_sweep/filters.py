"""Composable file-size, extension, and category filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"}
MUSIC_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".xls", ".xlsx", ".ppt", ".pptx"
}
CATEGORIES = {
    "images": IMAGE_EXTENSIONS,
    "videos": VIDEO_EXTENSIONS,
    "music": MUSIC_EXTENSIONS,
    "documents": DOCUMENT_EXTENSIONS,
}


@dataclass(frozen=True)
class FileFilters:
    """Optional file selection constraints used during scanning."""

    min_size: int | None = None
    max_size: int | None = None
    extensions: frozenset[str] = field(default_factory=frozenset)
    excluded_extensions: frozenset[str] = field(default_factory=frozenset)
    categories: frozenset[str] = field(default_factory=frozenset)

    def matches(self, path: Path) -> bool:
        """Return whether path passes extension and category constraints."""
        extension = path.suffix.lower()
        if self.extensions and extension not in self.extensions:
            return False
        if extension in self.excluded_extensions:
            return False
        if self.categories:
            allowed = set().union(*(CATEGORIES[name] for name in self.categories))
            if extension not in allowed:
                return False
        try:
            size = path.stat().st_size
        except OSError:
            return False
        return (self.min_size is None or size >= self.min_size) and (
            self.max_size is None or size <= self.max_size
        )


def parse_extensions(values: list[str] | None) -> frozenset[str]:
    """Normalize comma-separated or repeated extensions."""
    result: set[str] = set()
    for value in values or []:
        for item in value.split(","):
            extension = item.strip().lower()
            if extension and not extension.startswith("."):
                extension = "." + extension
            if extension:
                result.add(extension)
    return frozenset(result)
