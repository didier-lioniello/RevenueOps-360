"""Build a self-contained static dashboard from a deterministic report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from revenueops.reporting import write_reports

ASSET_DIRECTORY = Path(__file__).parent / "web"


def build_site(report: dict[str, Any], output_directory: str | Path) -> dict[str, Path]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    report_paths = write_reports(report, output)

    template = (ASSET_DIRECTORY / "index.html").read_text(encoding="utf-8")
    if template.count("{{REPORT_JSON}}") != 1:
        raise RuntimeError("site template must contain exactly one report placeholder")
    embedded_json = json.dumps(report, allow_nan=False, ensure_ascii=False, sort_keys=True)
    for character, escape in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e")):
        embedded_json = embedded_json.replace(character, escape)
    html = template.replace("{{REPORT_JSON}}", embedded_json)

    index_path = output / "index.html"
    style_path = output / "styles.css"
    script_path = output / "app.js"
    index_path.write_text(html, encoding="utf-8")
    style_path.write_text(
        (ASSET_DIRECTORY / "styles.css").read_text(encoding="utf-8"), encoding="utf-8"
    )
    script_path.write_text(
        (ASSET_DIRECTORY / "app.js").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return {
        **report_paths,
        "index": index_path,
        "styles": style_path,
        "script": script_path,
    }
