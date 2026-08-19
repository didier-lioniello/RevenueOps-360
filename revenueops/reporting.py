"""Stable JSON and Markdown reports for the synthetic demonstration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from revenueops.analytics import calculate_metrics
from revenueops.models import RevenueDataset, ScenarioInputs
from revenueops.recommendations import build_recommendations
from revenueops.scenario import compare_scenario


def build_report(
    dataset: RevenueDataset, scenario_inputs: ScenarioInputs | None = None
) -> dict[str, Any]:
    selected_scenario = scenario_inputs or dataset.default_scenario
    metrics = calculate_metrics(dataset)
    scenario = compare_scenario(dataset, metrics, selected_scenario)
    recommendations = build_recommendations(metrics, scenario)
    return {
        "report_version": "1.0",
        "dataset": {
            "dataset_id": dataset.metadata.dataset_id,
            "label": dataset.metadata.label,
            "synthetic": dataset.metadata.synthetic,
            "currency": dataset.metadata.currency,
            "period_start": dataset.metadata.period_start.isoformat(),
            "period_end": dataset.metadata.period_end.isoformat(),
        },
        "metrics": metrics,
        "scenario": scenario,
        "recommendations": recommendations,
        "disclaimers": [
            "Input is operator-attested as synthetic; this report does not verify that claim.",
            "The synthetic marker is an operator attestation, not PII detection; never use real "
            "exports.",
            "Outputs are deterministic arithmetic, not AI-generated advice or a customer promise.",
            "Forecasts use supplied categories and probabilities; scenarios do not establish "
            "causality.",
            "This reference implementation is not production-ready and is not financial advice.",
        ],
    }


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _money(value: float | None, currency: str) -> str:
    return "n/a" if value is None else f"{currency} {value:,.0f}"


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}×"


def _number(value: float | int | None) -> str:
    return "n/a" if value is None else str(value)


def report_markdown(report: dict[str, Any]) -> str:
    currency = report["dataset"]["currency"]
    metrics = report["metrics"]
    sales = metrics["sales"]
    pipeline = metrics["pipeline"]
    forecast = metrics["forecast"]
    marketing = metrics["marketing"]
    units = metrics["unit_economics"]
    scenario = report["scenario"]

    lines = [
        "# RevenueOps-360 — Synthetic Revenue Brief",
        "",
        "> **SYNTHETIC ATTESTATION · DEMONSTRATION ONLY** — no PII verification or redaction.",
        "",
        f"Dataset: `{report['dataset']['dataset_id']}` · "
        f"Period: {report['dataset']['period_start']} → {report['dataset']['period_end']}",
        "",
        "## Executive scorecard",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Closed-won revenue | {_money(sales['closed_won_revenue'], currency)} |",
        f"| Win rate | {_percent(sales['win_rate'])} |",
        f"| ACV | {_money(sales['average_contract_value'], currency)} |",
        f"| Average sales cycle | {_number(sales['average_sales_cycle_days'])} days |",
        f"| Pipeline coverage | {_ratio(pipeline['coverage'])} |",
        f"| Weighted forecast | {_money(forecast['weighted'], currency)} |",
        f"| Marketing ROI | {_percent(marketing['roi'])} |",
        f"| CAC payback | {_number(units['cac_payback_months'])} months |",
        f"| LTV:CAC | {_ratio(units['ltv_to_cac'])} |",
        "",
        "## Funnel",
        "",
        "| Stage | Count | Conversion from previous |",
        "|---|---:|---:|",
    ]
    for stage in metrics["funnel"]["stages"]:
        lines.append(
            f"| {stage['stage']} | {stage['count']} | "
            f"{_percent(stage['conversion_from_previous'])} |"
        )

    lines.extend(
        [
            "",
            "## Forecast versus target",
            "",
            "| View | Forecast | Attainment | Gap |",
            "|---|---:|---:|---:|",
        ]
    )
    for view in ("actual", "commit", "best_case", "weighted"):
        lines.append(
            f"| {view.replace('_', ' ').title()} | {_money(forecast[view], currency)} | "
            f"{_percent(forecast['attainment'][view])} | "
            f"{_money(forecast['gaps_to_target'][view], currency)} |"
        )

    lines.extend(
        [
            "",
            "## Marketing attribution",
            "",
            f"Model: `{marketing['attribution_model']}`",
            f"ROI formula: `{marketing['formula']}`",
            (
                f"ROI unavailable: `{marketing['roi_unavailable_reason']}`"
                if marketing["roi_unavailable_reason"]
                else f"Gross margin applied: {_percent(marketing['gross_margin_rate'])}"
            ),
            "",
            "| Channel | Spend | Won ACV | Attributed gross profit | ROI | CAC |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for channel in marketing["channels"]:
        lines.append(
            f"| {channel['channel']} | {_money(channel['spend'], currency)} | "
            f"{_money(channel['attributed_revenue'], currency)} | "
            f"{_money(channel['attributed_gross_profit'], currency)} | "
            f"{_percent(channel['roi'])} | {_money(channel['channel_cac'], currency)} |"
        )

    lines.extend(
        [
            "",
            "## Scenario comparison",
            "",
            f"Scenario: **{scenario['name']}**",
            "",
            "| Metric | Baseline | Modeled | Delta |",
            "|---|---:|---:|---:|",
        ]
    )
    base = scenario["baseline"]
    modeled = scenario["modeled"]
    scenario_rows = (
        ("Modeled revenue", "modeled_revenue", "money"),
        ("Modeled wins", "modeled_wins", "number"),
        ("ACV", "acv", "money"),
        ("Cycle", "cycle_days", "days"),
        ("Marketing spend", "marketing_spend", "money"),
        ("Marketing ROI", "marketing_roi", "percent"),
        ("Sales velocity/day", "sales_velocity_per_day", "money"),
    )
    for label, key, value_type in scenario_rows:
        if value_type == "money":
            base_text = _money(base.get(key), currency)
            modeled_text = _money(modeled.get(key), currency)
        elif value_type == "percent":
            base_text = _percent(base.get(key))
            modeled_text = _percent(modeled.get(key))
        elif value_type == "days":
            base_text = f"{base.get(key, 'n/a')} days"
            modeled_text = f"{modeled.get(key, 'n/a')} days"
        else:
            base_text = str(base.get(key, "n/a"))
            modeled_text = str(modeled.get(key, "n/a"))
        relative = scenario["delta"].get(key, {}).get("relative_pct")
        delta_text = "n/a" if relative is None else f"{relative:+.1f}%"
        lines.append(f"| {label} | {base_text} | {modeled_text} | {delta_text} |")

    lines.extend(["", "## Rule-based recommendations", ""])
    for recommendation in report["recommendations"]:
        lines.extend(
            [
                f"### [{recommendation['priority'].upper()}] {recommendation['title']}",
                "",
                recommendation["finding"],
                "",
                f"**Testable action:** {recommendation['action']}",
                "",
                f"Rule: `{recommendation['rule_id']}`",
                "",
            ]
        )
        for evidence in recommendation["evidence"]:
            lines.append(
                f"- `{evidence['source']}` = `{evidence['value']}` ({evidence['comparison']})"
            )
        lines.append("")

    lines.extend(["## Boundaries", ""])
    lines.extend(f"- {disclaimer}" for disclaimer in report["disclaimers"])
    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: dict[str, Any], output_directory: str | Path) -> dict[str, Path]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "report.json"
    markdown_path = output / "report.md"
    json_path.write_text(report_json(report), encoding="utf-8")
    markdown_path.write_text(report_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
