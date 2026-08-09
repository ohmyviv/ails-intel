from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


VALID_HEALTH = {"complete", "partial", "failed", "missing"}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


@dataclass(frozen=True)
class CoverageDecision:
    confidence: str
    reasons: tuple[str, ...]
    mandatory_completed: int
    mandatory_total: int
    mandatory_partial: int
    mandatory_failed: int
    mandatory_missing: int


@dataclass(frozen=True)
class RescueDecision:
    required: bool
    reasons: tuple[str, ...]
    broad_search_max: int
    premium_sweep: bool
    tier_a_exact_sweep: bool
    max_new_candidates: int


def _health(value: object) -> str:
    text = str(value or "missing").strip().lower()
    return text if text in VALID_HEALTH else "missing"


def evaluate_coverage(
    *,
    channel_health: Mapping[str, object],
    mandatory_channels: Sequence[str],
    premium_sweep_complete: bool,
    unresolved_gap: bool,
    abnormal_low_signal: bool,
    collector_saturation_count: int,
    pending_p0_due_count: int,
    rescue_was_required: bool = False,
    rescue_material_event_count: int = 0,
) -> CoverageDecision:
    """Apply the v11 deterministic Coverage Gate.

    This deliberately produces a categorical HIGH/MEDIUM/LOW outcome rather
    than a pseudo-probability. Missing mandatory-channel evidence is treated as
    unresolved coverage, not as an implicit success.
    """
    mandatory = [str(x).strip() for x in mandatory_channels if str(x).strip()]
    health = {channel: _health(channel_health.get(channel)) for channel in mandatory}

    complete = sum(1 for value in health.values() if value == "complete")
    partial = sum(1 for value in health.values() if value == "partial")
    failed = sum(1 for value in health.values() if value == "failed")
    missing = sum(1 for value in health.values() if value == "missing")

    low: list[str] = []
    if health.get("C1") in {"failed", "missing"}:
        low.append("c1_failed_or_missing")
    if health.get("C2") in {"failed", "missing"}:
        low.append("c2_failed_or_missing")
    if failed >= 1:
        low.append("mandatory_failed")
    if missing >= 1:
        low.append("mandatory_missing")
    if partial >= 2:
        low.append("mandatory_partial_gte_2")
    if unresolved_gap:
        low.append("unresolved_gap")
    if not premium_sweep_complete:
        low.append("premium_sweep_incomplete")
    if abnormal_low_signal and partial >= 1:
        low.append("abnormal_low_signal_with_partial")

    if low:
        confidence = "LOW"
        reasons = tuple(sorted(set(low)))
    else:
        medium: list[str] = []
        if partial == 1:
            medium.append("mandatory_partial_eq_1")
        if int(collector_saturation_count) >= 1:
            medium.append("collector_saturation")
        if abnormal_low_signal:
            medium.append("abnormal_low_signal")
        if int(pending_p0_due_count) > 0:
            medium.append("due_p0_pending")
        if rescue_was_required:
            medium.append("rescue_was_required")
        if int(rescue_material_event_count) > 0:
            medium.append("material_rescue_event")

        if medium:
            confidence = "MEDIUM"
            reasons = tuple(sorted(set(medium)))
        else:
            confidence = "HIGH"
            reasons = ("mandatory_complete_and_no_material_degradation",)

    return CoverageDecision(
        confidence=confidence,
        reasons=reasons,
        mandatory_completed=complete,
        mandatory_total=len(mandatory),
        mandatory_partial=partial,
        mandatory_failed=failed,
        mandatory_missing=missing,
    )


def plan_rescue(
    *,
    pre_rescue_confidence: str,
    previous_gap: bool,
    abnormal_low_signal: bool,
    rolling_critical_miss_count: int,
    broad_search_max: int = 4,
    premium_sweep: bool = True,
    tier_a_exact_sweep: bool = True,
    max_new_candidates: int = 3,
) -> RescueDecision:
    confidence = str(pre_rescue_confidence).strip().upper()
    if confidence not in VALID_CONFIDENCE:
        raise ValueError("pre_rescue_confidence must be HIGH, MEDIUM, or LOW")

    reasons: list[str] = []
    if confidence == "LOW":
        reasons.append("coverage_low")
    if previous_gap:
        reasons.append("previous_gap")
    if abnormal_low_signal:
        reasons.append("abnormal_low_signal")
    if int(rolling_critical_miss_count) > 0:
        reasons.append("rolling_critical_miss")

    required = bool(reasons)
    return RescueDecision(
        required=required,
        reasons=tuple(sorted(set(reasons))),
        broad_search_max=max(0, int(broad_search_max)) if required else 0,
        premium_sweep=bool(premium_sweep) if required else False,
        tier_a_exact_sweep=bool(tier_a_exact_sweep) if required else False,
        max_new_candidates=max(0, int(max_new_candidates)) if required else 0,
    )
