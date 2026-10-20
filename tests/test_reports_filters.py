"""Tests for report exports and file filters."""

import csv
import json
from pathlib import Path

from dupe_sweep.filters import FileFilters, parse_extensions
from dupe_sweep.finder import DuplicateGroup
from dupe_sweep.hasher import full_hash
from dupe_sweep.reports import export_report


def test_filters_apply_size_and_extensions(tmp_path: Path) -> None:
    image = tmp_path / "photo.JPG"
    image.write_bytes(b"0123456789")
    filters = FileFilters(min_size=8, max_size=12, categories=frozenset({"images"}))
    assert filters.matches(image)
    assert not FileFilters(min_size=11).matches(image)
    assert parse_extensions(["jpg,.PNG", " .gif "]) == frozenset({".jpg", ".png", ".gif"})


def test_json_and_csv_exports_include_keep_role(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    group = DuplicateGroup(full_hash(first), (first, second), 4)

    json_path = export_report([group], tmp_path / "report.json")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["groups"] == 1
    assert {row["status"] for row in payload["files"]} == {"keep", "duplicate"}

    csv_path = export_report([group], tmp_path / "report.csv")
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"keep", "duplicate"}


def test_html_export_escapes_paths(tmp_path: Path) -> None:
    first = tmp_path / "<first>"
    second = tmp_path / "second"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    group = DuplicateGroup(full_hash(first), (first, second), 4)
    output = export_report([group], tmp_path / "report.html")
    markup = output.read_text(encoding="utf-8")
    assert "&lt;first&gt;" in markup
