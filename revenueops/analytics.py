"""Deterministic Revenue Operations metrics and documented formulas."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, median
from typing import Any

from revenueops.models import Opportunity, RevenueDataset, ValidationError


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError("metric calculation produced a non-finite value")
    return round(result, digits)


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    result = numerator / denominator
    if not math.isfinite(result):
        raise ValidationError("metric calculation produced a non-finite ratio")
    return result


def _money(value: float | None) -> float | None:
    return _round(value, 2)


def calculate_funnel(dataset: RevenueDataset) -> dict[str, Any]:
    stages = []
    for index, stage in enumerate(dataset.funnel):
        previous = dataset.funnel[index - 1] if index else None
        conversion = None if previous is None else _ratio(stage.count, previous.count)
        stages.append(
            {
                "stage": stage.stage,
                "count": stage.count,
                "conversion_from_previous": _round(conversion),
            }
        )
    overall = _ratio(dataset.funnel[-1].count, dataset.funnel[0].count)
    return {
        "stages": stages,
        "overall_conversion": _round(overall),
        "formula": "next_stage_count / previous_stage_count",
    }


def _closed_cycles(opportunities: tuple[Opportunity, ...]) -> list[int]:
    return [cycle for opportunity in opportunities if (cycle := opportunity.cycle_days) is not None]


def calculate_sales(dataset: RevenueDataset) -> dict[str, Any]:
    won = [opportunity for opportunity in dataset.opportunities if opportunity.status == "won"]
    lost = [opportunity for opportunity in dataset.opportunities if opportunity.status == "lost"]
    open_deals = [
        opportunity for opportunity in dataset.opportunities if opportunity.status == "open"
    ]
    closed_count = len(won) + len(lost)
    win_rate = _ratio(len(won), closed_count)
    acv = mean(opportunity.acv for opportunity in won) if won else None
    cycles = _closed_cycles(dataset.opportunities)
    average_cycle = mean(cycles) if cycles else None
    median_cycle = median(cycles) if cycles else None
    funnel_counts = {stage.stage: stage.count for stage in dataset.funnel}
    velocity_opportunities = funnel_counts["Opportunity"]
    velocity_conversion = _ratio(dataset.funnel[-1].count, velocity_opportunities)
    velocity = None
    if velocity_conversion is not None and acv is not None and average_cycle:
        velocity = velocity_opportunities * velocity_conversion * acv / average_cycle

    return {
        "won_deals": len(won),
        "lost_deals": len(lost),
        "open_deals": len(open_deals),
        "closed_won_revenue": _money(sum(opportunity.acv for opportunity in won)),
        "win_rate": _round(win_rate),
        "average_contract_value": _money(acv),
        "average_sales_cycle_days": _round(average_cycle, 2),
        "median_sales_cycle_days": _round(median_cycle, 2),
        "sales_velocity_per_day": _money(velocity),
        "sales_velocity_opportunity_to_won_rate": _round(velocity_conversion),
        "formulas": {
            "win_rate": "won / (won + lost)",
            "average_contract_value": "closed_won_revenue / won_deals",
            "sales_cycle": "mean(close_date - created_date) across closed deals",
            "sales_velocity": "funnel opportunities * opportunity-to-won rate * ACV / cycle",
        },
    }


def _in_period_open(dataset: RevenueDataset) -> list[Opportunity]:
    return [
        opportunity
        for opportunity in dataset.opportunities
        if opportunity.status == "open"
        and opportunity.expected_close_date is not None
        and opportunity.expected_close_date <= dataset.metadata.period_end
    ]


def calculate_pipeline_and_forecast(
    dataset: RevenueDataset, sales: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    all_open = [
        opportunity for opportunity in dataset.opportunities if opportunity.status == "open"
    ]
    in_period = _in_period_open(dataset)
    out_of_period = [opportunity for opportunity in all_open if opportunity not in in_period]
    actual = float(sales["closed_won_revenue"])
    target = dataset.metadata.revenue_target
    remaining_target = max(target - actual, 0.0)
    in_period_pipeline = sum(opportunity.acv for opportunity in in_period)
    coverage = _ratio(in_period_pipeline, remaining_target) if remaining_target else None

    commit_open = sum(
        opportunity.acv for opportunity in in_period if opportunity.forecast_category == "commit"
    )
    best_case_open = sum(
        opportunity.acv for opportunity in in_period if opportunity.forecast_category == "best_case"
    )
    weighted_open = sum(opportunity.acv * opportunity.probability for opportunity in in_period)
    forecasts = {
        "actual": actual,
        "commit": actual + commit_open,
        "best_case": actual + commit_open + best_case_open,
        "weighted": actual + weighted_open,
    }
    forecast = {
        "target": _money(target),
        **{name: _money(value) for name, value in forecasts.items()},
        "gaps_to_target": {
            name: _money(max(target - value, 0.0)) for name, value in forecasts.items()
        },
        "attainment": {name: _round(_ratio(value, target)) for name, value in forecasts.items()},
        "formula_notes": {
            "commit": "actual + full ACV of in-period commit opportunities",
            "best_case": "actual + in-period commit + in-period best_case ACV",
            "weighted": "actual + sum(in-period open ACV * probability)",
        },
    }
    pipeline = {
        "all_open_pipeline": _money(sum(opportunity.acv for opportunity in all_open)),
        "in_period_open_pipeline": _money(in_period_pipeline),
        "out_of_period_open_pipeline": _money(
            sum(opportunity.acv for opportunity in out_of_period)
        ),
        "in_period_open_deals": len(in_period),
        "remaining_target": _money(remaining_target),
        "coverage": _round(coverage),
        "coverage_target": _round(dataset.metadata.pipeline_coverage_target),
        "coverage_gap_amount": _money(
            max(
                remaining_target * dataset.metadata.pipeline_coverage_target - in_period_pipeline,
                0.0,
            )
        ),
        "formula": "in_period_open_pipeline / max(target - actual, 0)",
        "coverage_status": "target_already_met" if remaining_target == 0 else "measured",
    }
    return pipeline, forecast


def calculate_marketing(dataset: RevenueDataset) -> dict[str, Any]:
    attributed_revenue: defaultdict[str, float] = defaultdict(float)
    won_deals: defaultdict[str, int] = defaultdict(int)
    opportunity_counts: defaultdict[str, int] = defaultdict(int)
    for opportunity in dataset.opportunities:
        opportunity_counts[opportunity.marketing_source] += 1
        if opportunity.status == "won":
            attributed_revenue[opportunity.marketing_source] += opportunity.acv
            won_deals[opportunity.marketing_source] += 1

    margin = dataset.unit_economics.gross_margin_rate

    def roi_values(revenue: float, spend: float) -> tuple[float | None, float | None, str | None]:
        if margin is None:
            return None, None, "gross margin unavailable"
        gross_profit = revenue * margin
        if spend == 0:
            return gross_profit, None, "channel spend is zero"
        return gross_profit, (gross_profit - spend) / spend, None

    channels = []
    for channel in dataset.marketing_channels:
        revenue = attributed_revenue[channel.channel]
        wins = won_deals[channel.channel]
        gross_profit, roi, roi_unavailable_reason = roi_values(revenue, channel.spend)
        channels.append(
            {
                "channel": channel.channel,
                "spend": _money(channel.spend),
                "leads": channel.leads,
                "opportunities": opportunity_counts[channel.channel],
                "won_deals": wins,
                "attributed_revenue": _money(revenue),
                "attributed_gross_profit": _money(gross_profit),
                "roi": _round(roi),
                "roi_unavailable_reason": roi_unavailable_reason,
                "roas": _round(_ratio(revenue, channel.spend)),
                "cost_per_lead": _money(_ratio(channel.spend, channel.leads)),
                "channel_cac": _money(_ratio(channel.spend, wins)),
            }
        )

    total_spend = sum(channel.spend for channel in dataset.marketing_channels)
    total_revenue = sum(attributed_revenue.values())
    total_leads = sum(channel.leads for channel in dataset.marketing_channels)
    total_wins = sum(won_deals.values())
    total_gross_profit, total_roi, total_roi_unavailable_reason = roi_values(
        total_revenue, total_spend
    )
    roi_formula = (
        "ROI = (closed-won attributed ACV * gross margin rate - channel spend) / channel spend"
    )
    return {
        "attribution_model": "synthetic first-touch marketing_source",
        "gross_margin_rate": _round(margin),
        "total_spend": _money(total_spend),
        "attributed_revenue": _money(total_revenue),
        "attributed_gross_profit": _money(total_gross_profit),
        "roi": _round(total_roi),
        "roi_unavailable_reason": total_roi_unavailable_reason,
        "roas": _round(_ratio(total_revenue, total_spend)),
        "cost_per_lead": _money(_ratio(total_spend, total_leads)),
        "marketing_cac": _money(_ratio(total_spend, total_wins)),
        "channels": channels,
        "formula": roi_formula,
    }


def calculate_unit_economics(
    dataset: RevenueDataset,
    sales: dict[str, Any],
    marketing: dict[str, Any],
) -> dict[str, Any]:
    new_customers = int(sales["won_deals"])
    acquisition_spend = (
        float(marketing["total_spend"]) + dataset.unit_economics.sales_acquisition_spend
    )
    blended_cac = _ratio(acquisition_spend, new_customers)
    acv = sales["average_contract_value"]
    margin = dataset.unit_economics.gross_margin_rate
    churn = dataset.unit_economics.annual_logo_churn_rate

    payback = None
    estimated_ltv = None
    ltv_to_cac = None
    if blended_cac is not None and acv is not None and margin is not None:
        monthly_gross_profit = float(acv) * margin / 12
        payback = _ratio(blended_cac, monthly_gross_profit)
        if churn is not None:
            estimated_ltv = float(acv) * margin / churn
            ltv_to_cac = _ratio(estimated_ltv, blended_cac)

    unavailable = []
    if not new_customers:
        unavailable.append("no closed-won customers")
    if acv is None:
        unavailable.append("ACV unavailable")
    if margin is None:
        unavailable.append("gross margin unavailable")
    if churn is None:
        unavailable.append("annual logo churn unavailable")

    return {
        "new_customers": new_customers,
        "marketing_spend": marketing["total_spend"],
        "sales_acquisition_spend": _money(dataset.unit_economics.sales_acquisition_spend),
        "total_acquisition_spend": _money(acquisition_spend),
        "blended_cac": _money(blended_cac),
        "cac_payback_months": _round(payback, 2),
        "estimated_ltv": _money(estimated_ltv),
        "ltv_to_cac": _round(ltv_to_cac, 2),
        "gross_margin_rate": _round(margin),
        "annual_logo_churn_rate": _round(churn),
        "unavailable_reasons": unavailable,
        "formula_notes": {
            "blended_cac": "(marketing spend + sales acquisition spend) / new customers",
            "cac_payback": "blended CAC / (ACV * gross margin / 12)",
            "estimated_ltv": "ACV * gross margin / annual logo churn",
            "ltv_to_cac": "estimated LTV / blended CAC",
        },
    }


def calculate_metrics(dataset: RevenueDataset) -> dict[str, Any]:
    funnel = calculate_funnel(dataset)
    sales = calculate_sales(dataset)
    pipeline, forecast = calculate_pipeline_and_forecast(dataset, sales)
    marketing = calculate_marketing(dataset)
    unit_economics = calculate_unit_economics(dataset, sales, marketing)
    return {
        "funnel": funnel,
        "sales": sales,
        "pipeline": pipeline,
        "forecast": forecast,
        "marketing": marketing,
        "unit_economics": unit_economics,
    }
