import json
import math
from copy import deepcopy

import pytest

from revenueops.analytics import calculate_metrics
from revenueops.models import MAX_MONEY, RevenueDataset
from revenueops.recommendations import build_recommendations
from revenueops.reporting import build_report, report_json
from revenueops.scenario import compare_scenario


def test_scenario_changes_conversion_acv_cycle_and_spend(dataset):
    metrics = calculate_metrics(dataset)
    comparison = compare_scenario(dataset, metrics, dataset.default_scenario)
    baseline = comparison["baseline"]
    modeled = comparison["modeled"]

    assert baseline["modeled_revenue"] == 390000
    assert baseline["modeled_wins"] == 6
    assert baseline["sales_velocity_per_day"] == metrics["sales"]["sales_velocity_per_day"]
    assert modeled["modeled_wins"] > baseline["modeled_wins"]
    assert modeled["acv"] == baseline["acv"] * 1.05
    assert modeled["cycle_days"] == pytest.approx(baseline["cycle_days"] * 0.9, abs=0.01)
    assert modeled["marketing_spend"] == baseline["marketing_spend"] * 1.05
    assert baseline["marketing_roi"] == pytest.approx(
        (baseline["modeled_revenue"] * 0.78 - baseline["marketing_spend"])
        / baseline["marketing_spend"],
        abs=0.0001,
    )
    assert modeled["marketing_roi"] == pytest.approx(
        (modeled["modeled_revenue"] * 0.78 - modeled["marketing_spend"])
        / modeled["marketing_spend"],
        abs=0.0001,
    )
    assert comparison["delta"]["modeled_revenue"]["relative_pct"] > 0


def test_recommendations_are_rule_traced_and_evidence_linked(dataset):
    metrics = calculate_metrics(dataset)
    scenario = compare_scenario(dataset, metrics, dataset.default_scenario)
    recommendations = build_recommendations(metrics, scenario)
    rule_ids = {recommendation["rule_id"] for recommendation in recommendations}

    assert "FORECAST_WEIGHTED_GAP" in rule_ids
    assert "PIPELINE_COVERAGE_SHORTFALL" in rule_ids
    assert "FUNNEL_WEAKEST_STAGE" in rule_ids
    assert "CHANNEL_ROI_EVENTS" in rule_ids
    assert all(
        recommendation["engine"] == "deterministic-threshold-rules-v1"
        for recommendation in recommendations
    )
    assert all(recommendation["evidence"] for recommendation in recommendations)
    assert all(
        evidence["source"]
        for recommendation in recommendations
        for evidence in recommendation["evidence"]
    )
    channel_rule = next(
        recommendation
        for recommendation in recommendations
        if recommendation["rule_id"] == "CHANNEL_ROI_EVENTS"
    )
    assert any(
        evidence["source"] == "metrics.marketing.gross_margin_rate"
        for evidence in channel_rule["evidence"]
    )


def test_missing_margin_produces_traceable_roi_recommendation(payload):
    candidate = deepcopy(payload)
    candidate["unit_economics"]["gross_margin_rate"] = None
    dataset = RevenueDataset.from_dict(candidate)
    metrics = calculate_metrics(dataset)
    scenario = compare_scenario(dataset, metrics, dataset.default_scenario)

    recommendation = next(
        item
        for item in build_recommendations(metrics, scenario)
        if item["rule_id"] == "MARKETING_ROI_UNAVAILABLE"
    )

    assert recommendation["evidence"] == [
        {
            "metric": "gross_margin_rate",
            "value": None,
            "comparison": "is unavailable",
            "source": "metrics.marketing.gross_margin_rate",
        }
    ]


def test_report_is_byte_deterministic_and_contains_no_generated_timestamp(dataset):
    first = report_json(build_report(dataset))
    second = report_json(build_report(dataset))

    assert first == second
    assert "generated_at" not in first
    assert json.loads(first)["dataset"]["synthetic"] is True
    assert "customer promise" in first


def test_json_serialization_rejects_nonfinite_report_values(dataset):
    report = build_report(dataset)
    report["metrics"]["sales"]["closed_won_revenue"] = float("inf")

    with pytest.raises(ValueError, match="Out of range float values"):
        report_json(report)


def test_maximum_bounded_input_produces_only_finite_report_numbers(payload):
    candidate = deepcopy(payload)
    candidate["metadata"]["revenue_target"] = MAX_MONEY
    for opportunity in candidate["opportunities"]:
        opportunity["acv"] = MAX_MONEY
    for channel in candidate["marketing_channels"]:
        channel["spend"] = MAX_MONEY
    candidate["unit_economics"]["sales_acquisition_spend"] = MAX_MONEY

    report = build_report(RevenueDataset.from_dict(candidate))

    def assert_finite(value):
        if isinstance(value, dict):
            for nested in value.values():
                assert_finite(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_finite(nested)
        elif isinstance(value, float):
            assert math.isfinite(value)

    assert_finite(report)
    assert json.loads(report_json(report))["metrics"]["sales"]["won_deals"] == 6
