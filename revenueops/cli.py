"""Reproducible command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from revenueops import __version__
from revenueops.models import ScenarioInputs, ValidationError, load_dataset
from revenueops.reporting import build_report, write_reports
from revenueops.site import build_site

DEFAULT_INPUT = Path("data/synthetic_revenue.json")


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Validated, operator-attested synthetic JSON (default: data/synthetic_revenue.json).",
    )
    parser.add_argument("--scenario-name", help="Override the scenario label.")
    parser.add_argument(
        "--conversion-lift",
        type=float,
        help="Relative percent change applied to every funnel conversion.",
    )
    parser.add_argument("--acv-change", type=float, help="Relative ACV percent change.")
    parser.add_argument("--cycle-change", type=float, help="Relative cycle-time percent change.")
    parser.add_argument(
        "--spend-change",
        type=float,
        help="Relative marketing-spend and lead-volume percent change.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="revenueops",
        description="Deterministic RevenueOps analytics on operator-attested synthetic data.",
    )
    parser.add_argument("--version", action="version", version=f"RevenueOps-360 {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze", help="Write deterministic JSON and Markdown reports."
    )
    _add_common_arguments(analyze)
    analyze.add_argument("--output-dir", type=Path, default=Path("build/report"))

    site = subparsers.add_parser(
        "build-site", help="Write reports and a self-contained static dashboard."
    )
    _add_common_arguments(site)
    site.add_argument("--output-dir", type=Path, default=Path("docs"))
    return parser


def _scenario_from_args(defaults: ScenarioInputs, args: argparse.Namespace) -> ScenarioInputs:
    return defaults.with_overrides(
        name=args.scenario_name,
        conversion_lift_pct=args.conversion_lift,
        acv_change_pct=args.acv_change,
        cycle_change_pct=args.cycle_change,
        marketing_spend_change_pct=args.spend_change,
    )


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset = load_dataset(args.input)
        scenario_inputs = _scenario_from_args(dataset.default_scenario, args)
        report = build_report(dataset, scenario_inputs)
        if args.command == "analyze":
            paths = write_reports(report, args.output_dir)
        else:
            paths = build_site(report, args.output_dir)
    except (OSError, RuntimeError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summary = {
        "command": args.command,
        "dataset_id": report["dataset"]["dataset_id"],
        "synthetic": report["dataset"]["synthetic"],
        "scenario": report["scenario"]["name"],
        "outputs": {name: str(path) for name, path in sorted(paths.items())},
    }
    print(json.dumps(summary, allow_nan=False, indent=2, sort_keys=True))
    return 0


def main() -> None:
    raise SystemExit(run())
