from copy import deepcopy

import pytest

from revenueops.analytics import calculate_metrics
from revenueops.models import RevenueDataset


def test_funnel_sales_and_velocity_formulas(dataset):
    metrics = calculate_metrics(dataset)

    assert [stage["conversion_from_previous"] for stage in metrics["funnel"]["stages"]] == [
        None,
        0.4,
        0.5,
        0.25,
        0.3,
    ]
    assert metrics["funnel"]["overall_conversion"] == 0.015
    assert metrics["sales"]["win_rate"] == 0.375
    assert metrics["sales"]["closed_won_revenue"] == 390000
    assert metrics["sales"]["average_contract_value"] == 65000
    assert metrics["sales"]["average_sales_cycle_days"] == 77.75
    expected_velocity = 20 * 0.3 * 65000 / 77.75
    assert metrics["sales"]["sales_velocity_per_day"] == pytest.approx(expected_velocity, abs=0.01)


def test_pipeline_and_forecast_exclude_out_of_period_deals(dataset):
    metrics = calculate_metrics(dataset)
    pipeline = metrics["pipeline"]
    forecast = metrics["forecast"]

    assert pipeline["all_open_pipeline"] == 365000
    assert pipeline["in_period_open_pipeline"] == 295000
    assert pipeline["out_of_period_open_pipeline"] == 70000
    assert pipeline["coverage"] == pytest.approx(295000 / 410000, abs=0.0001)
    assert forecast["actual"] == 390000
    assert forecast["commit"] == 605000
    assert forecast["best_case"] == 685000
    assert forecast["weighted"] == 607250
    assert forecast["gaps_to_target"]["weighted"] == 192750


def test_marketing_attribution_roi_and_unit_economics(dataset):
    metrics = calculate_metrics(dataset)
    marketing = metrics["marketing"]
    events = next(channel for channel in marketing["channels"] if channel["channel"] == "Events")

    assert marketing["total_spend"] == 175000
    assert marketing["attributed_revenue"] == 390000
    assert marketing["attributed_gross_profit"] == 304200
    assert marketing["roi"] == pytest.approx((390000 * 0.78 - 175000) / 175000, abs=0.0001)
    assert marketing["roas"] == pytest.approx(390000 / 175000, abs=0.0001)
    assert marketing["roi_unavailable_reason"] is None
    assert events["attributed_gross_profit"] == 51480
    assert events["roi"] == -0.142
    assert events["channel_cac"] == 60000
    assert metrics["unit_economics"]["blended_cac"] == 47500
    assert metrics["unit_economics"]["cac_payback_months"] == 11.24
    assert metrics["unit_economics"]["ltv_to_cac"] == 7.62


def test_target_already_met_and_missing_unit_inputs_are_safe(payload):
    candidate = deepcopy(payload)
    candidate["metadata"]["revenue_target"] = 300000
    candidate["unit_economics"]["gross_margin_rate"] = None
    candidate["unit_economics"]["annual_logo_churn_rate"] = None
    metrics = calculate_metrics(RevenueDataset.from_dict(candidate))

    assert metrics["pipeline"]["remaining_target"] == 0
    assert metrics["pipeline"]["coverage"] is None
    assert metrics["pipeline"]["coverage_status"] == "target_already_met"
    assert metrics["marketing"]["roi"] is None
    assert metrics["marketing"]["attributed_gross_profit"] is None
    assert metrics["marketing"]["roi_unavailable_reason"] == "gross margin unavailable"
    assert all(
        channel["roi_unavailable_reason"] == "gross margin unavailable"
        for channel in metrics["marketing"]["channels"]
    )
    assert metrics["unit_economics"]["cac_payback_months"] is None
    assert metrics["unit_economics"]["ltv_to_cac"] is None
    assert metrics["unit_economics"]["unavailable_reasons"] == [
        "gross margin unavailable",
        "annual logo churn unavailable",
    ]


def test_zero_marketing_spend_does_not_divide_by_zero(payload):
    candidate = deepcopy(payload)
    for channel in candidate["marketing_channels"]:
        channel["spend"] = 0
    candidate["unit_economics"]["sales_acquisition_spend"] = 0
    metrics = calculate_metrics(RevenueDataset.from_dict(candidate))

    assert metrics["marketing"]["roi"] is None
    assert all(channel["roi"] is None for channel in metrics["marketing"]["channels"])
    assert metrics["marketing"]["roi_unavailable_reason"] == "channel spend is zero"
    assert metrics["unit_economics"]["blended_cac"] == 0
    assert metrics["unit_economics"]["ltv_to_cac"] is None
