"""Transparent what-if scenarios built from validated aggregate metrics."""

from __future__ import annotations

import math
from typing import Any

from revenueops.models import RevenueDataset, ScenarioInputs, ValidationError


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError("scenario calculation produced a non-finite value")
    return round(result, digits)


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    result = numerator / denominator
    if not math.isfinite(result):
        raise ValidationError("scenario calculation produced a non-finite ratio")
    return result


def _project(
    dataset: RevenueDataset,
    metrics: dict[str, Any],
    inputs: ScenarioInputs,
) -> dict[str, Any]:
    funnel = metrics["funnel"]["stages"]
    acv = metrics["sales"]["average_contract_value"]
    average_cycle = metrics["sales"]["average_sales_cycle_days"]
    if acv is None or average_cycle is None:
        return {
            "available": False,
            "reason": "Scenario requires at least one won deal and one closed-deal cycle.",
        }
    if any(stage["conversion_from_previous"] is None for stage in funnel[1:]):
        return {
            "available": False,
            "reason": "Scenario requires non-zero denominators for every funnel conversion.",
        }

    spend_multiplier = 1 + inputs.marketing_spend_change_pct / 100
    conversion_multiplier = 1 + inputs.conversion_lift_pct / 100
    acv_multiplier = 1 + inputs.acv_change_pct / 100
    cycle_multiplier = 1 + inputs.cycle_change_pct / 100

    stage_counts = [float(funnel[0]["count"]) * spend_multiplier]
    modeled_conversions = []
    for stage in funnel[1:]:
        baseline_conversion = float(stage["conversion_from_previous"])
        modeled_conversion = min(max(baseline_conversion * conversion_multiplier, 0.0), 1.0)
        modeled_conversions.append(modeled_conversion)
        stage_counts.append(stage_counts[-1] * modeled_conversion)

    stage_names = [stage["stage"] for stage in funnel]
    opportunity_index = stage_names.index("Opportunity")
    projected_opportunities = stage_counts[opportunity_index]
    projected_wins = stage_counts[-1]
    projected_win_rate = _ratio(projected_wins, projected_opportunities)
    projected_acv = float(acv) * acv_multiplier
    projected_cycle = float(average_cycle) * cycle_multiplier
    projected_revenue = projected_wins * projected_acv
    projected_spend = float(metrics["marketing"]["total_spend"]) * spend_multiplier
    projected_velocity = (
        projected_opportunities * projected_win_rate * projected_acv / projected_cycle
        if projected_win_rate is not None and projected_cycle
        else None
    )
    margin = dataset.unit_economics.gross_margin_rate
    projected_gross_profit = projected_revenue * margin if margin is not None else None
    projected_roi = (
        _ratio(projected_gross_profit - projected_spend, projected_spend)
        if projected_gross_profit is not None
        else None
    )
    roi_unavailable_reason = None
    if margin is None:
        roi_unavailable_reason = "gross margin unavailable"
    elif projected_spend == 0:
        roi_unavailable_reason = "modeled marketing spend is zero"

    acquisition_spend = projected_spend + dataset.unit_economics.sales_acquisition_spend
    projected_cac = _ratio(acquisition_spend, projected_wins)
    churn = dataset.unit_economics.annual_logo_churn_rate
    projected_payback = None
    projected_ltv = None
    projected_ltv_to_cac = None
    if projected_cac is not None and margin is not None:
        monthly_gross_profit = projected_acv * margin / 12
        projected_payback = _ratio(projected_cac, monthly_gross_profit)
        if churn is not None:
            projected_ltv = projected_acv * margin / churn
            projected_ltv_to_cac = _ratio(projected_ltv, projected_cac)

    return {
        "available": True,
        "stage_counts": [
            {"stage": name, "modeled_count": _round(count, 2)}
            for name, count in zip(stage_names, stage_counts, strict=True)
        ],
        "stage_conversions": [
            {
                "from": stage_names[index],
                "to": stage_names[index + 1],
                "modeled_conversion": _round(conversion),
            }
            for index, conversion in enumerate(modeled_conversions)
        ],
        "modeled_wins": _round(projected_wins, 2),
        "modeled_opportunities": _round(projected_opportunities, 2),
        "modeled_win_rate": _round(projected_win_rate),
        "acv": _round(projected_acv, 2),
        "cycle_days": _round(projected_cycle, 2),
        "marketing_spend": _round(projected_spend, 2),
        "modeled_revenue": _round(projected_revenue, 2),
        "attributed_gross_profit": _round(projected_gross_profit, 2),
        "sales_velocity_per_day": _round(projected_velocity, 2),
        "marketing_roi": _round(projected_roi),
        "marketing_roi_unavailable_reason": roi_unavailable_reason,
        "target_attainment": _round(_ratio(projected_revenue, dataset.metadata.revenue_target)),
        "blended_cac": _round(projected_cac, 2),
        "cac_payback_months": _round(projected_payback, 2),
        "estimated_ltv": _round(projected_ltv, 2),
        "ltv_to_cac": _round(projected_ltv_to_cac, 2),
    }


def _delta(base: dict[str, Any], modeled: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "modeled_wins",
        "acv",
        "cycle_days",
        "marketing_spend",
        "modeled_revenue",
        "sales_velocity_per_day",
        "marketing_roi",
        "target_attainment",
        "blended_cac",
        "cac_payback_months",
        "ltv_to_cac",
    )
    deltas = {}
    for field in fields:
        base_value = base.get(field)
        modeled_value = modeled.get(field)
        if base_value is None or modeled_value is None:
            deltas[field] = {"absolute": None, "relative_pct": None}
            continue
        absolute = float(modeled_value) - float(base_value)
        relative = _ratio(absolute, abs(float(base_value)))
        deltas[field] = {
            "absolute": _round(absolute, 4),
            "relative_pct": _round(relative * 100 if relative is not None else None, 2),
        }
    return deltas


def compare_scenario(
    dataset: RevenueDataset,
    metrics: dict[str, Any],
    inputs: ScenarioInputs,
) -> dict[str, Any]:
    baseline_inputs = ScenarioInputs(
        name="Baseline",
        conversion_lift_pct=0.0,
        acv_change_pct=0.0,
        cycle_change_pct=0.0,
        marketing_spend_change_pct=0.0,
    )
    baseline = _project(dataset, metrics, baseline_inputs)
    modeled = _project(dataset, metrics, inputs)
    return {
        "name": inputs.name,
        "inputs": inputs.to_dict(),
        "assumptions": [
            "Marketing lead volume changes linearly with marketing spend.",
            "The conversion change is relative and applied to every stage, capped at 100%.",
            "ACV and cycle changes are relative to observed synthetic baselines.",
            "Marketing ROI uses attributed modeled ACV multiplied by gross margin before spend.",
            "Fractional modeled deals are expected-value planning units, not customer promises.",
            "No causal effect is inferred; the scenario is arithmetic sensitivity analysis.",
        ],
        "baseline": baseline,
        "modeled": modeled,
        "delta": _delta(baseline, modeled)
        if baseline["available"] and modeled["available"]
        else {},
    }
