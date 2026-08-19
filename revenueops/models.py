"""Validated input model for synthetic RevenueOps datasets."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

CANONICAL_FUNNEL_STAGES = ("Lead", "MQL", "SQL", "Opportunity", "Won")
MAX_CHANNELS = 100
MAX_COUNT = 10_000_000
MAX_DATASET_BYTES = 10 * 1024 * 1024
MAX_MONEY = 1_000_000_000_000.0
MAX_OPPORTUNITIES = 10_000
MAX_PIPELINE_COVERAGE_TARGET = 100.0
MAX_TEXT_LENGTH = 160


class ValidationError(ValueError):
    """Raised when an input dataset violates the public data contract."""


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{path} must be an object")
    return value


def _reject_unknown_fields(raw: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(str(field) for field in set(raw) - allowed)
    if unknown:
        fields = ", ".join(unknown)
        raise ValidationError(f"{path} contains unknown fields: {fields}")


def _list(
    value: Any,
    path: str,
    *,
    maximum_items: int | None = None,
) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{path} must be an array")
    if maximum_items is not None and len(value) > maximum_items:
        raise ValidationError(f"{path} must contain at most {maximum_items} items")
    return value


def _string(value: Any, path: str, *, maximum_length: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{path} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum_length:
        raise ValidationError(f"{path} must contain at most {maximum_length} characters")
    return result


def _number(
    value: Any,
    path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{path} must be a number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValidationError(f"{path} must be finite") from exc
    if not math.isfinite(result):
        raise ValidationError(f"{path} must be finite")
    if minimum is not None and result < minimum:
        raise ValidationError(f"{path} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValidationError(f"{path} must be at most {maximum}")
    return result


def _integer(
    value: Any,
    path: str,
    *,
    minimum: int = 0,
    maximum: int = MAX_COUNT,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{path} must be an integer")
    if value < minimum:
        raise ValidationError(f"{path} must be at least {minimum}")
    if value > maximum:
        raise ValidationError(f"{path} must be at most {maximum}")
    return value


def _money(value: Any, path: str, *, allow_zero: bool = True) -> float:
    result = _number(value, path, minimum=0 if allow_zero else 0.01, maximum=MAX_MONEY)
    if allow_zero and 0 < result < 0.01:
        raise ValidationError(f"{path} must be zero or at least 0.01")
    return result


def _date(value: Any, path: str) -> date:
    raw = _string(value, path)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(f"{path} must be an ISO date (YYYY-MM-DD)") from exc


def _optional_date(value: Any, path: str) -> date | None:
    return None if value is None else _date(value, path)


def _reject_nonstandard_json_number(value: str) -> None:
    raise ValidationError(f"dataset is not valid JSON: non-standard value {value}")


def _reject_duplicate_json_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, value in pairs:
        if field in result:
            raise ValidationError(f"dataset is not valid JSON: duplicate field {field}")
        result[field] = value
    return result


@dataclass(frozen=True)
class Metadata:
    dataset_id: str
    label: str
    synthetic: bool
    currency: str
    period_start: date
    period_end: date
    revenue_target: float
    pipeline_coverage_target: float


@dataclass(frozen=True)
class FunnelStage:
    stage: str
    count: int


@dataclass(frozen=True)
class Opportunity:
    id: str
    created_date: date
    close_date: date | None
    expected_close_date: date | None
    status: str
    stage: str
    acv: float
    forecast_category: str
    probability: float
    marketing_source: str

    @property
    def cycle_days(self) -> int | None:
        if self.close_date is None:
            return None
        return (self.close_date - self.created_date).days


@dataclass(frozen=True)
class MarketingChannel:
    channel: str
    spend: float
    leads: int


@dataclass(frozen=True)
class UnitEconomics:
    sales_acquisition_spend: float
    gross_margin_rate: float | None
    annual_logo_churn_rate: float | None


@dataclass(frozen=True)
class ScenarioInputs:
    name: str
    conversion_lift_pct: float
    acv_change_pct: float
    cycle_change_pct: float
    marketing_spend_change_pct: float

    @classmethod
    def from_dict(cls, raw: dict[str, Any], path: str = "default_scenario") -> ScenarioInputs:
        _reject_unknown_fields(
            raw,
            {
                "name",
                "conversion_lift_pct",
                "acv_change_pct",
                "cycle_change_pct",
                "marketing_spend_change_pct",
            },
            path,
        )

        def change(field: str) -> float:
            value = _number(raw.get(field), f"{path}.{field}")
            if value <= -100 or value > 500:
                raise ValidationError(f"{path}.{field} must be greater than -100 and at most 500")
            return value

        return cls(
            name=_string(raw.get("name"), f"{path}.name"),
            conversion_lift_pct=change("conversion_lift_pct"),
            acv_change_pct=change("acv_change_pct"),
            cycle_change_pct=change("cycle_change_pct"),
            marketing_spend_change_pct=change("marketing_spend_change_pct"),
        )

    def with_overrides(
        self,
        *,
        name: str | None = None,
        conversion_lift_pct: float | None = None,
        acv_change_pct: float | None = None,
        cycle_change_pct: float | None = None,
        marketing_spend_change_pct: float | None = None,
    ) -> ScenarioInputs:
        candidate = replace(
            self,
            name=name if name is not None else self.name,
            conversion_lift_pct=(
                conversion_lift_pct if conversion_lift_pct is not None else self.conversion_lift_pct
            ),
            acv_change_pct=acv_change_pct if acv_change_pct is not None else self.acv_change_pct,
            cycle_change_pct=(
                cycle_change_pct if cycle_change_pct is not None else self.cycle_change_pct
            ),
            marketing_spend_change_pct=(
                marketing_spend_change_pct
                if marketing_spend_change_pct is not None
                else self.marketing_spend_change_pct
            ),
        )
        return ScenarioInputs.from_dict(candidate.to_dict(), path="scenario")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "conversion_lift_pct": self.conversion_lift_pct,
            "acv_change_pct": self.acv_change_pct,
            "cycle_change_pct": self.cycle_change_pct,
            "marketing_spend_change_pct": self.marketing_spend_change_pct,
        }


@dataclass(frozen=True)
class RevenueDataset:
    metadata: Metadata
    funnel: tuple[FunnelStage, ...]
    opportunities: tuple[Opportunity, ...]
    marketing_channels: tuple[MarketingChannel, ...]
    unit_economics: UnitEconomics
    default_scenario: ScenarioInputs

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RevenueDataset:
        root = _mapping(payload, "dataset")
        _reject_unknown_fields(
            root,
            {
                "metadata",
                "funnel",
                "opportunities",
                "marketing_channels",
                "unit_economics",
                "default_scenario",
            },
            "dataset",
        )
        metadata = cls._parse_metadata(_mapping(root.get("metadata"), "metadata"))
        funnel = cls._parse_funnel(_list(root.get("funnel"), "funnel"))
        channels = cls._parse_channels(
            _list(
                root.get("marketing_channels"),
                "marketing_channels",
                maximum_items=MAX_CHANNELS,
            )
        )
        opportunities = cls._parse_opportunities(
            _list(
                root.get("opportunities"),
                "opportunities",
                maximum_items=MAX_OPPORTUNITIES,
            ),
            metadata,
            channels,
        )
        unit_economics = cls._parse_unit_economics(
            _mapping(root.get("unit_economics"), "unit_economics")
        )
        scenario = ScenarioInputs.from_dict(
            _mapping(root.get("default_scenario"), "default_scenario")
        )
        cls._validate_cross_totals(funnel, opportunities, channels)
        return cls(metadata, funnel, opportunities, channels, unit_economics, scenario)

    @staticmethod
    def _parse_metadata(raw: dict[str, Any]) -> Metadata:
        _reject_unknown_fields(
            raw,
            {
                "dataset_id",
                "label",
                "synthetic",
                "currency",
                "period_start",
                "period_end",
                "revenue_target",
                "pipeline_coverage_target",
            },
            "metadata",
        )
        if raw.get("synthetic") is not True:
            raise ValidationError(
                "metadata.synthetic must be exactly true as an explicit synthetic-data attestation"
            )
        label = _string(raw.get("label"), "metadata.label")
        if not label.upper().startswith("SYNTHETIC"):
            raise ValidationError(
                "metadata.label must begin with SYNTHETIC as part of the explicit attestation"
            )
        currency = _string(raw.get("currency"), "metadata.currency").upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValidationError("metadata.currency must be a three-letter code")
        period_start = _date(raw.get("period_start"), "metadata.period_start")
        period_end = _date(raw.get("period_end"), "metadata.period_end")
        if period_end < period_start:
            raise ValidationError("metadata.period_end must be on or after period_start")
        return Metadata(
            dataset_id=_string(raw.get("dataset_id"), "metadata.dataset_id"),
            label=label,
            synthetic=True,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
            revenue_target=_money(
                raw.get("revenue_target"), "metadata.revenue_target", allow_zero=False
            ),
            pipeline_coverage_target=_number(
                raw.get("pipeline_coverage_target"),
                "metadata.pipeline_coverage_target",
                minimum=0.01,
                maximum=MAX_PIPELINE_COVERAGE_TARGET,
            ),
        )

    @staticmethod
    def _parse_funnel(raw: list[Any]) -> tuple[FunnelStage, ...]:
        if len(raw) != len(CANONICAL_FUNNEL_STAGES):
            expected = " → ".join(CANONICAL_FUNNEL_STAGES)
            raise ValidationError(f"funnel must contain exactly the canonical stages: {expected}")
        stages = []
        for index, item in enumerate(raw):
            record = _mapping(item, f"funnel[{index}]")
            _reject_unknown_fields(record, {"stage", "count"}, f"funnel[{index}]")
            stages.append(
                FunnelStage(
                    stage=_string(record.get("stage"), f"funnel[{index}].stage"),
                    count=_integer(record.get("count"), f"funnel[{index}].count"),
                )
            )
        names = tuple(stage.stage for stage in stages)
        if names != CANONICAL_FUNNEL_STAGES:
            expected = " → ".join(CANONICAL_FUNNEL_STAGES)
            raise ValidationError(f"funnel stages must be ordered exactly as: {expected}")
        for previous, current in zip(stages, stages[1:], strict=False):
            if current.count > previous.count:
                raise ValidationError("funnel counts must be non-increasing")
        return tuple(stages)

    @staticmethod
    def _parse_channels(raw: list[Any]) -> tuple[MarketingChannel, ...]:
        if not raw:
            raise ValidationError("marketing_channels must not be empty")
        channels = []
        for index, item in enumerate(raw):
            record = _mapping(item, f"marketing_channels[{index}]")
            _reject_unknown_fields(
                record, {"channel", "spend", "leads"}, f"marketing_channels[{index}]"
            )
            channels.append(
                MarketingChannel(
                    channel=_string(record.get("channel"), f"marketing_channels[{index}].channel"),
                    spend=_money(record.get("spend"), f"marketing_channels[{index}].spend"),
                    leads=_integer(record.get("leads"), f"marketing_channels[{index}].leads"),
                )
            )
        names = [channel.channel.casefold() for channel in channels]
        if len(set(names)) != len(names):
            raise ValidationError("marketing channel names must be unique")
        return tuple(channels)

    @classmethod
    def _parse_opportunities(
        cls,
        raw: list[Any],
        metadata: Metadata,
        channels: tuple[MarketingChannel, ...],
    ) -> tuple[Opportunity, ...]:
        channel_names = {channel.channel for channel in channels}
        opportunities = []
        for index, item in enumerate(raw):
            path = f"opportunities[{index}]"
            record = _mapping(item, path)
            _reject_unknown_fields(
                record,
                {
                    "id",
                    "created_date",
                    "close_date",
                    "expected_close_date",
                    "status",
                    "stage",
                    "acv",
                    "forecast_category",
                    "probability",
                    "marketing_source",
                },
                path,
            )
            status = _string(record.get("status"), f"{path}.status").casefold()
            if status not in {"won", "lost", "open"}:
                raise ValidationError(f"{path}.status must be won, lost, or open")
            created_date = _date(record.get("created_date"), f"{path}.created_date")
            if not metadata.period_start <= created_date <= metadata.period_end:
                raise ValidationError(f"{path}.created_date must be within the reporting period")
            close_date = _optional_date(record.get("close_date"), f"{path}.close_date")
            expected_close_date = _optional_date(
                record.get("expected_close_date"), f"{path}.expected_close_date"
            )
            category = _string(
                record.get("forecast_category"), f"{path}.forecast_category"
            ).casefold()
            probability = _number(
                record.get("probability"), f"{path}.probability", minimum=0, maximum=1
            )

            if status in {"won", "lost"}:
                if close_date is None:
                    raise ValidationError(f"{path}.close_date is required for closed opportunities")
                if close_date < created_date:
                    raise ValidationError(f"{path}.close_date cannot precede created_date")
                if close_date > metadata.period_end:
                    raise ValidationError(f"{path}.close_date must be within the reporting period")
                if category != "closed":
                    raise ValidationError(f"{path}.forecast_category must be closed")
                expected_probability = 1.0 if status == "won" else 0.0
                if probability != expected_probability:
                    raise ValidationError(
                        f"{path}.probability must be {expected_probability} for status {status}"
                    )
            else:
                if close_date is not None:
                    raise ValidationError(
                        f"{path}.close_date must be omitted for open opportunities"
                    )
                if expected_close_date is None or expected_close_date < created_date:
                    raise ValidationError(
                        f"{path}.expected_close_date is required and cannot precede created_date"
                    )
                if category not in {"commit", "best_case", "pipeline"}:
                    raise ValidationError(
                        f"{path}.forecast_category must be commit, best_case, or pipeline"
                    )

            source = _string(record.get("marketing_source"), f"{path}.marketing_source")
            if source not in channel_names:
                raise ValidationError(f"{path}.marketing_source must match a marketing channel")
            opportunity_id = _string(record.get("id"), f"{path}.id")
            if not re.fullmatch(r"SYN-OPP-[A-Z0-9][A-Z0-9-]{0,31}", opportunity_id):
                raise ValidationError(
                    f"{path}.id must use the synthetic identifier format SYN-OPP-*"
                )
            opportunities.append(
                Opportunity(
                    id=opportunity_id,
                    created_date=created_date,
                    close_date=close_date,
                    expected_close_date=expected_close_date,
                    status=status,
                    stage=_string(record.get("stage"), f"{path}.stage"),
                    acv=_money(record.get("acv"), f"{path}.acv", allow_zero=False),
                    forecast_category=category,
                    probability=probability,
                    marketing_source=source,
                )
            )

        ids = [opportunity.id for opportunity in opportunities]
        if len(set(ids)) != len(ids):
            raise ValidationError("opportunity ids must be unique")
        return tuple(opportunities)

    @staticmethod
    def _parse_unit_economics(raw: dict[str, Any]) -> UnitEconomics:
        _reject_unknown_fields(
            raw,
            {
                "sales_acquisition_spend",
                "gross_margin_rate",
                "annual_logo_churn_rate",
            },
            "unit_economics",
        )
        gross_margin_raw = raw.get("gross_margin_rate")
        churn_raw = raw.get("annual_logo_churn_rate")
        return UnitEconomics(
            sales_acquisition_spend=_money(
                raw.get("sales_acquisition_spend"),
                "unit_economics.sales_acquisition_spend",
            ),
            gross_margin_rate=(
                None
                if gross_margin_raw is None
                else _number(
                    gross_margin_raw,
                    "unit_economics.gross_margin_rate",
                    minimum=0,
                    maximum=1,
                )
            ),
            annual_logo_churn_rate=(
                None
                if churn_raw is None
                else _number(
                    churn_raw,
                    "unit_economics.annual_logo_churn_rate",
                    minimum=0.000001,
                    maximum=1,
                )
            ),
        )

    @staticmethod
    def _validate_cross_totals(
        funnel: tuple[FunnelStage, ...],
        opportunities: tuple[Opportunity, ...],
        channels: tuple[MarketingChannel, ...],
    ) -> None:
        if funnel[0].count != sum(channel.leads for channel in channels):
            raise ValidationError(
                "the first funnel count must equal total synthetic marketing channel leads"
            )
        stage_counts = {stage.stage: stage.count for stage in funnel}
        if stage_counts["Opportunity"] != len(opportunities):
            raise ValidationError(
                "the Opportunity funnel count must equal the opportunity record count"
            )
        won_count = sum(opportunity.status == "won" for opportunity in opportunities)
        if stage_counts["Won"] != won_count:
            raise ValidationError("the Won funnel count must equal closed-won opportunity records")


def load_dataset(path: str | Path) -> RevenueDataset:
    input_path = Path(path)
    try:
        with input_path.open("rb") as input_file:
            raw_bytes = input_file.read(MAX_DATASET_BYTES + 1)
        if len(raw_bytes) > MAX_DATASET_BYTES:
            raise ValidationError(f"dataset must be at most {MAX_DATASET_BYTES} bytes")
    except OSError as exc:
        raise ValidationError(f"cannot read dataset: {input_path}") from exc
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("dataset must be UTF-8 JSON") from exc
    try:
        payload = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_json_fields,
            parse_constant=_reject_nonstandard_json_number,
        )
    except json.JSONDecodeError as exc:
        raise ValidationError(f"dataset is not valid JSON: {exc}") from exc
    return RevenueDataset.from_dict(payload)
