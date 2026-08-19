from copy import deepcopy
from pathlib import Path

import pytest

from revenueops.models import (
    CANONICAL_FUNNEL_STAGES,
    MAX_CHANNELS,
    MAX_COUNT,
    MAX_MONEY,
    MAX_OPPORTUNITIES,
    MAX_TEXT_LENGTH,
    RevenueDataset,
    ScenarioInputs,
    ValidationError,
    load_dataset,
)


def test_valid_dataset_is_explicitly_synthetic_and_cross_totals_match(dataset):
    assert dataset.metadata.synthetic is True
    assert dataset.metadata.label.startswith("SYNTHETIC DATA")
    assert dataset.funnel[0].count == sum(channel.leads for channel in dataset.marketing_channels)
    assert len(dataset.opportunities) == 20


def test_rejects_any_dataset_not_explicitly_marked_synthetic(payload):
    candidate = deepcopy(payload)
    candidate["metadata"]["synthetic"] = False

    with pytest.raises(ValidationError, match="synthetic-data attestation"):
        RevenueDataset.from_dict(candidate)

    misleading_label = deepcopy(payload)
    misleading_label["metadata"]["label"] = "NOT SYNTHETIC"
    with pytest.raises(ValidationError, match="must begin with SYNTHETIC"):
        RevenueDataset.from_dict(misleading_label)


def test_requires_canonical_funnel_stage_names_and_order(payload):
    renamed = deepcopy(payload)
    renamed["funnel"][-1]["stage"] = "Activated"
    with pytest.raises(ValidationError, match="Lead → MQL → SQL → Opportunity → Won"):
        RevenueDataset.from_dict(renamed)

    reordered = deepcopy(payload)
    reordered["funnel"][1], reordered["funnel"][2] = (
        reordered["funnel"][2],
        reordered["funnel"][1],
    )
    with pytest.raises(ValidationError, match="ordered exactly"):
        RevenueDataset.from_dict(reordered)

    assert tuple(stage["stage"] for stage in payload["funnel"]) == CANONICAL_FUNNEL_STAGES


def test_rejects_increasing_funnel_and_inconsistent_totals(payload):
    increasing = deepcopy(payload)
    increasing["funnel"][2]["count"] = 999
    with pytest.raises(ValidationError, match="non-increasing"):
        RevenueDataset.from_dict(increasing)

    inconsistent = deepcopy(payload)
    inconsistent["funnel"][0]["count"] = 401
    with pytest.raises(ValidationError, match="channel leads"):
        RevenueDataset.from_dict(inconsistent)

    inconsistent_opportunities = deepcopy(payload)
    inconsistent_opportunities["funnel"][3]["count"] = 19
    with pytest.raises(ValidationError, match="Opportunity funnel count"):
        RevenueDataset.from_dict(inconsistent_opportunities)

    inconsistent_wins = deepcopy(payload)
    inconsistent_wins["funnel"][4]["count"] = 5
    with pytest.raises(ValidationError, match="Won funnel count"):
        RevenueDataset.from_dict(inconsistent_wins)


def test_rejects_invalid_dates_probability_category_and_duplicate_ids(payload):
    invalid_date = deepcopy(payload)
    invalid_date["opportunities"][0]["close_date"] = "2024-12-01"
    with pytest.raises(ValidationError, match="cannot precede"):
        RevenueDataset.from_dict(invalid_date)

    invalid_probability = deepcopy(payload)
    invalid_probability["opportunities"][0]["probability"] = 0.5
    with pytest.raises(ValidationError, match="must be 1.0"):
        RevenueDataset.from_dict(invalid_probability)

    invalid_category = deepcopy(payload)
    invalid_category["opportunities"][-1]["forecast_category"] = "upside"
    with pytest.raises(ValidationError, match="commit, best_case, or pipeline"):
        RevenueDataset.from_dict(invalid_category)

    duplicate = deepcopy(payload)
    duplicate["opportunities"][1]["id"] = duplicate["opportunities"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        RevenueDataset.from_dict(duplicate)


def test_scenario_input_bounds_and_overrides(dataset):
    updated = dataset.default_scenario.with_overrides(
        name="Custom",
        conversion_lift_pct=12,
        acv_change_pct=-5,
        cycle_change_pct=-20,
        marketing_spend_change_pct=0,
    )
    assert updated.name == "Custom"
    assert updated.conversion_lift_pct == 12
    with pytest.raises(ValidationError, match="greater than -100"):
        ScenarioInputs.from_dict(
            {
                "name": "Invalid",
                "conversion_lift_pct": -100,
                "acv_change_pct": 0,
                "cycle_change_pct": 0,
                "marketing_spend_change_pct": 0,
            }
        )


def test_non_finite_numbers_are_rejected(payload):
    non_finite_target = deepcopy(payload)
    non_finite_target["metadata"]["revenue_target"] = float("nan")
    with pytest.raises(ValidationError, match="must be finite"):
        RevenueDataset.from_dict(non_finite_target)

    non_finite_scenario = deepcopy(payload)
    non_finite_scenario["default_scenario"]["acv_change_pct"] = float("inf")
    with pytest.raises(ValidationError, match="must be finite"):
        RevenueDataset.from_dict(non_finite_scenario)


def test_rejects_unknown_fields_at_root_and_nested_boundaries(payload):
    root_extra = deepcopy(payload)
    root_extra["debug"] = True
    with pytest.raises(ValidationError, match="dataset contains unknown fields: debug"):
        RevenueDataset.from_dict(root_extra)

    opportunity_extra = deepcopy(payload)
    opportunity_extra["opportunities"][0]["customer_email"] = "not-ingested@example.invalid"
    with pytest.raises(ValidationError, match="contains unknown fields: customer_email"):
        RevenueDataset.from_dict(opportunity_extra)

    scenario_extra = deepcopy(payload)
    scenario_extra["default_scenario"]["unreviewed_lever"] = 1
    with pytest.raises(ValidationError, match="contains unknown fields: unreviewed_lever"):
        RevenueDataset.from_dict(scenario_extra)


def test_requires_synthetic_opportunity_identifiers(payload):
    candidate = deepcopy(payload)
    candidate["opportunities"][0]["id"] = "CRM-OPP-001"

    with pytest.raises(ValidationError, match=r"SYN-OPP-\*"):
        RevenueDataset.from_dict(candidate)


def test_rejects_excessive_cardinality_text_counts_and_money(payload):
    too_many_channels = deepcopy(payload)
    too_many_channels["marketing_channels"] = [
        deepcopy(payload["marketing_channels"][0]) for _ in range(MAX_CHANNELS + 1)
    ]
    with pytest.raises(ValidationError, match=f"at most {MAX_CHANNELS} items"):
        RevenueDataset.from_dict(too_many_channels)

    too_many_opportunities = deepcopy(payload)
    too_many_opportunities["opportunities"] = [
        deepcopy(payload["opportunities"][0]) for _ in range(MAX_OPPORTUNITIES + 1)
    ]
    with pytest.raises(ValidationError, match=f"at most {MAX_OPPORTUNITIES} items"):
        RevenueDataset.from_dict(too_many_opportunities)

    overlong = deepcopy(payload)
    overlong["metadata"]["label"] = "SYNTHETIC " + "x" * MAX_TEXT_LENGTH
    with pytest.raises(ValidationError, match=f"at most {MAX_TEXT_LENGTH} characters"):
        RevenueDataset.from_dict(overlong)

    excessive_count = deepcopy(payload)
    excessive_count["funnel"][0]["count"] = MAX_COUNT + 1
    with pytest.raises(ValidationError, match=f"at most {MAX_COUNT}"):
        RevenueDataset.from_dict(excessive_count)

    excessive_money = deepcopy(payload)
    excessive_money["opportunities"][0]["acv"] = MAX_MONEY * 2
    with pytest.raises(ValidationError, match=f"at most {MAX_MONEY}"):
        RevenueDataset.from_dict(excessive_money)

    integer_overflow = deepcopy(payload)
    integer_overflow["metadata"]["revenue_target"] = 10**1000
    with pytest.raises(ValidationError, match="must be finite"):
        RevenueDataset.from_dict(integer_overflow)


def test_loader_rejects_nonstandard_nonfinite_json(payload, tmp_path: Path):
    input_path = tmp_path / "nonfinite.json"
    input_path.write_text('{"metadata": {"revenue_target": Infinity}}', encoding="utf-8")

    with pytest.raises(ValidationError, match="non-standard value Infinity"):
        load_dataset(input_path)

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"metadata": {}, "metadata": {}}', encoding="utf-8")
    with pytest.raises(ValidationError, match="duplicate field metadata"):
        load_dataset(duplicate_path)
