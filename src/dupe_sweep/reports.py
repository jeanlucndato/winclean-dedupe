"""CSV, JSON, and standalone HTML duplicate reports."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .finder import DuplicateGroup
from .rules import KeepStrategy, choose_keep


def export_report(
    groups: list[DuplicateGroup],
    output: Path,
    *,
    format: str | None = None,
    strategy: KeepStrategy | str = KeepStrategy.OLDEST,
    preferred_folder: Path | None = None,
) -> Path:
    """Export duplicate groups with kept/duplicate roles in CSV, JSON, or HTML."""
    report_format = (format or output.suffix.lstrip(".")).lower()
    if report_format not in {"csv", "json", "html"}:
        raise ValueError("Report format must be csv, json, or html")
    records: list[dict[str, object]] = []
    for group in groups:
        keep = choose_keep(group, strategy, preferred_folder)
        for path in group.files:
            records.append(
                {
                    "group_sha256": group.digest,
                    "size_bytes": group.size,
                    "path": str(path),
                    "status": "keep" if path == keep else "duplicate",
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "json":
        output.write_text(json.dumps({"groups": len(groups), "files": records}, indent=2), encoding="utf-8")
    elif report_format == "csv":
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=["group_sha256", "size_bytes", "path", "status"])
            writer.writeheader()
            writer.writerows(records)
    else:
        rows = "\n".join(
            "<tr>" + "".join(f"<td>{html.escape(str(record[key]))}</td>" for key in record) + "</tr>"
            for record in records
        )
        output.write_text(
            "<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>dupe-sweep report</title><style>body{font:15px system-ui;margin:2rem;color:#18212f}"
            "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:.65rem;border-bottom:1px solid #ddd}"
            "th{background:#f2f5f8;position:sticky;top:0}</style><h1>dupe-sweep scan report</h1>"
            f"<p>{len(groups)} duplicate groups · {len(records)} files</p>"
            "<table><thead><tr><th>SHA-256</th><th>Size (bytes)</th><th>Path</th><th>Status</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></html>",
            encoding="utf-8",
        )
    return output
