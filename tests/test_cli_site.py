import json
import re
from copy import deepcopy
from pathlib import Path

from revenueops.cli import run
from revenueops.reporting import build_report, report_markdown


def test_analyze_cli_writes_reports_and_accepts_scenario_overrides(tmp_path: Path, capsys):
    output = tmp_path / "report"
    exit_code = run(
        [
            "analyze",
            "--output-dir",
            str(output),
            "--scenario-name",
            "CLI scenario",
            "--conversion-lift",
            "4",
            "--acv-change",
            "2",
            "--cycle-change",
            "-5",
            "--spend-change",
            "3",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["synthetic"] is True
    assert summary["scenario"] == "CLI scenario"
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["scenario"]["inputs"]["conversion_lift_pct"] == 4
    assert "SYNTHETIC ATTESTATION" in (output / "report.md").read_text(encoding="utf-8")


def test_cli_rejects_non_synthetic_input(payload, tmp_path: Path, capsys):
    candidate = deepcopy(payload)
    candidate["metadata"]["synthetic"] = False
    input_path = tmp_path / "unsafe.json"
    input_path.write_text(json.dumps(candidate), encoding="utf-8")

    exit_code = run(["analyze", "--input", str(input_path), "--output-dir", str(tmp_path)])

    assert exit_code == 2
    assert "synthetic-data attestation" in capsys.readouterr().err


def test_static_site_build_is_self_contained_and_deterministic(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert run(["build-site", "--output-dir", str(first)]) == 0
    assert run(["build-site", "--output-dir", str(second)]) == 0

    expected = {"index.html", "styles.css", "app.js", "report.json", "report.md"}
    assert {path.name for path in first.iterdir()} == expected
    for filename in expected:
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

    html = (first / "index.html").read_text(encoding="utf-8")
    css = (first / "styles.css").read_text(encoding="utf-8")
    script = (first / "app.js").read_text(encoding="utf-8")
    assert "SYNTHETIC ATTESTATION · DEMONSTRATION ONLY" in html
    assert '"synthetic": true' in html
    assert "{{REPORT_JSON}}" not in html
    csp = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; base-uri 'none'; form-action 'none'"
    )
    assert f'http-equiv="Content-Security-Policy" content="{csp}"' in html
    embedded_match = re.search(r'<template id="report-data">(.*?)</template>', html, re.DOTALL)
    assert embedded_match is not None
    assert json.loads(embedded_match.group(1))["dataset"]["synthetic"] is True
    assert 'name="viewport"' in html
    assert "@media (max-width: 720px)" in css
    assert "reportNode.content.textContent" in script
    assert "channel.roi_unavailable_reason" in script
    assert 'dataset.ready = "true"' in script
    assert ".style" not in script
    assert not re.search(r"https?://", html + css + script)


def test_markdown_preserves_zero_measurements(dataset):
    report = build_report(dataset)
    report["metrics"]["sales"]["average_sales_cycle_days"] = 0
    report["metrics"]["unit_economics"]["cac_payback_months"] = 0

    markdown = report_markdown(report)

    assert "| Average sales cycle | 0 days |" in markdown
    assert "| CAC payback | 0 months |" in markdown
