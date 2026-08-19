"""Deterministic, evidence-linked recommendations without an LLM."""

from __future__ import annotations

from typing import Any

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _evidence(metric: str, value: Any, comparison: str, source: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "comparison": comparison,
        "source": source,
    }


def build_recommendations(
    metrics: dict[str, Any], scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    def add(
        rule_id: str,
        priority: str,
        title: str,
        finding: str,
        action: str,
        evidence: list[dict[str, Any]],
    ) -> None:
        recommendations.append(
            {
                "rule_id": rule_id,
                "priority": priority,
                "title": title,
                "finding": finding,
                "action": action,
                "evidence": evidence,
                "engine": "deterministic-threshold-rules-v1",
            }
        )

    weighted_gap = metrics["forecast"]["gaps_to_target"]["weighted"]
    if weighted_gap and weighted_gap > 0:
        add(
            "FORECAST_WEIGHTED_GAP",
            "high",
            "Build a quantified target-gap plan",
            "The probability-weighted in-period forecast remains below the synthetic target.",
            "Separate the gap into pipeline creation, deal progression, and ACV experiments; "
            "assign an owner and review date to each assumption.",
            [
                _evidence(
                    "weighted_gap_to_target",
                    weighted_gap,
                    "> 0",
                    "metrics.forecast.gaps_to_target.weighted",
                )
            ],
        )

    coverage = metrics["pipeline"]["coverage"]
    coverage_target = metrics["pipeline"]["coverage_target"]
    if coverage is not None and coverage < coverage_target:
        add(
            "PIPELINE_COVERAGE_SHORTFALL",
            "high",
            "Increase qualified in-period coverage",
            "Open pipeline expected inside the reporting period is below the configured coverage "
            "multiple.",
            "Audit stage-entry criteria and test source-specific pipeline creation against the "
            "measured coverage gap; do not count out-of-period deals as current coverage.",
            [
                _evidence(
                    "pipeline_coverage",
                    coverage,
                    f"< target {coverage_target}",
                    "metrics.pipeline.coverage",
                ),
                _evidence(
                    "coverage_gap_amount",
                    metrics["pipeline"]["coverage_gap_amount"],
                    "> 0",
                    "metrics.pipeline.coverage_gap_amount",
                ),
            ],
        )

    conversion_rows = [
        stage
        for stage in metrics["funnel"]["stages"][1:]
        if stage["conversion_from_previous"] is not None
    ]
    if conversion_rows:
        weakest = min(conversion_rows, key=lambda stage: stage["conversion_from_previous"])
        weakest_index = metrics["funnel"]["stages"].index(weakest)
        previous_stage = metrics["funnel"]["stages"][weakest_index - 1]["stage"]
        if weakest["conversion_from_previous"] < 0.35:
            add(
                "FUNNEL_WEAKEST_STAGE",
                "medium",
                f"Instrument the {previous_stage} → {weakest['stage']} handoff",
                "This is the lowest observed stage-to-stage conversion in the synthetic funnel.",
                "Review entry/exit definitions, loss reasons, response time, and enablement at "
                "this handoff; run one controlled change before scaling spend.",
                [
                    _evidence(
                        "stage_conversion",
                        weakest["conversion_from_previous"],
                        "< 0.35 rule threshold",
                        f"metrics.funnel.stages[{weakest_index}].conversion_from_previous",
                    )
                ],
            )

    cycle = metrics["sales"]["average_sales_cycle_days"]
    if cycle is not None and cycle > 75:
        add(
            "SALES_CYCLE_REVIEW",
            "medium",
            "Test one cycle-time constraint",
            "The observed closed-deal cycle exceeds the rule's 75-day review threshold.",
            "Segment cycle time by stage and outcome, then test one reversible intervention "
            "such as mutual action plans or earlier technical validation.",
            [
                _evidence(
                    "average_sales_cycle_days",
                    cycle,
                    "> 75 days",
                    "metrics.sales.average_sales_cycle_days",
                )
            ],
        )

    low_roi_channels = [
        channel
        for channel in metrics["marketing"]["channels"]
        if channel["roi"] is not None and channel["roi"] < 0.2
    ]
    for channel in low_roi_channels:
        add(
            f"CHANNEL_ROI_{channel['channel'].upper().replace(' ', '_')}",
            "medium",
            f"Review {channel['channel']} economics before adding spend",
            "Attributed gross profit produces less than 20% ROI over synthetic channel spend.",
            "Validate attribution, gross margin, and downstream quality, then cap, redesign, or "
            "retest the channel before increasing its budget.",
            [
                _evidence(
                    "channel_roi",
                    channel["roi"],
                    "< 0.20 rule threshold",
                    f"metrics.marketing.channels[{metrics['marketing']['channels'].index(channel)}].roi",
                ),
                _evidence(
                    "gross_margin_rate",
                    metrics["marketing"]["gross_margin_rate"],
                    "applied to attributed ACV",
                    "metrics.marketing.gross_margin_rate",
                ),
            ],
        )

    if metrics["marketing"]["roi_unavailable_reason"] == "gross margin unavailable":
        add(
            "MARKETING_ROI_UNAVAILABLE",
            "medium",
            "Supply a reviewed gross-margin assumption",
            "Marketing ROI is unavailable because gross margin was not supplied.",
            "Validate and document a gross-margin rate before comparing channel ROI; use ROAS "
            "only as a revenue-efficiency view until then.",
            [
                _evidence(
                    "gross_margin_rate",
                    metrics["marketing"]["gross_margin_rate"],
                    "is unavailable",
                    "metrics.marketing.gross_margin_rate",
                )
            ],
        )

    payback = metrics["unit_economics"]["cac_payback_months"]
    ltv_to_cac = metrics["unit_economics"]["ltv_to_cac"]
    if payback is not None and payback > 12:
        add(
            "CAC_PAYBACK_LONG",
            "high",
            "Reduce acquisition payback exposure",
            "Modeled CAC payback exceeds the 12-month review threshold.",
            "Test pricing, gross-margin, conversion, or acquisition-cost levers independently and "
            "recalculate payback before scaling acquisition.",
            [
                _evidence(
                    "cac_payback_months",
                    payback,
                    "> 12 months",
                    "metrics.unit_economics.cac_payback_months",
                )
            ],
        )
    if ltv_to_cac is not None and ltv_to_cac < 3:
        add(
            "LTV_CAC_LOW",
            "high",
            "Recheck unit economics before scaling",
            "The simplified LTV:CAC estimate is below the rule's 3.0 review threshold.",
            "Validate retention and margin assumptions, then prioritize the most sensitive lever "
            "in a controlled scenario rather than treating this estimate as a forecast.",
            [
                _evidence(
                    "ltv_to_cac",
                    ltv_to_cac,
                    "< 3.0",
                    "metrics.unit_economics.ltv_to_cac",
                )
            ],
        )

    modeled = scenario.get("modeled", {})
    if modeled.get("available") and modeled.get("target_attainment", 0) < 1:
        add(
            "SCENARIO_TARGET_GAP",
            "low",
            "Treat the scenario as sensitivity, not a plan",
            "Even the configured arithmetic scenario remains below full target attainment.",
            "Use the scenario to rank assumptions, then require operational evidence before "
            "adopting any conversion, ACV, spend, or cycle change in a plan.",
            [
                _evidence(
                    "modeled_target_attainment",
                    modeled["target_attainment"],
                    "< 1.0",
                    "scenario.modeled.target_attainment",
                )
            ],
        )

    return sorted(
        recommendations,
        key=lambda item: (PRIORITY_ORDER[item["priority"]], item["rule_id"]),
    )
