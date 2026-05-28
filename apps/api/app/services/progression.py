from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib


ROOT = Path(__file__).resolve().parents[4]
PROGRESSION_MODEL_PATH = ROOT / "ml" / "models" / "artifacts" / "progression_next_set_model.joblib"


@dataclass(frozen=True)
class SetObservation:
    exercise: str
    weight_kg: float
    reps: int
    set_index: int
    performed_at: str


@dataclass(frozen=True)
class ProgressionPrediction:
    exercise: str
    target_weight_kg: float
    target_reps: int
    target_reps_min: int
    target_reps_max: int
    confidence: float
    model_version: str
    strategy: str
    reason: str
    target_kind: str = "working"


def _round_load(value: float) -> float:
    return max(0.0, round(value / 2.5) * 2.5)


def _estimate_epley(weight_kg: float, reps: int) -> float:
    return weight_kg * (1.0 + max(1, reps) / 30.0)


def _parse_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromisoformat(value[:10])


def _normalize_rep_range(rep_mode: str, rep_min: int, rep_max: int) -> tuple[int, int]:
    if rep_mode == "custom":
        low = max(1, min(30, rep_min))
        high = max(low, min(30, rep_max))
        return low, high
    if rep_mode == "pr":
        return 1, 3
    return 8, 10


def build_progression_feature_row(
    exercise: str,
    history: list[SetObservation],
    set_index: int = 1,
    current_session: list[SetObservation] | None = None,
    preferred_rep_mode: str = "auto",
    preferred_rep_min: int = 8,
    preferred_rep_max: int = 10,
) -> dict[str, float | int | str]:
    ordered = sorted(history, key=lambda row: (row.performed_at, row.set_index))
    current_session = current_session or []
    rep_min, rep_max = _normalize_rep_range(preferred_rep_mode, preferred_rep_min, preferred_rep_max)
    latest = ordered[-1] if ordered else None
    latest_day = latest.performed_at[:10] if latest else ""
    latest_session = [row for row in ordered if row.performed_at[:10] == latest_day] if latest else []
    matching = next((row for row in latest_session if row.set_index == set_index), latest_session[min(set_index - 1, len(latest_session) - 1)] if latest_session else None)
    recent = ordered[-12:]
    recent_e1rm = [_estimate_epley(row.weight_kg, row.reps) for row in recent]
    prior_current = [row for row in current_session if row.set_index < set_index]
    previous_current = prior_current[-1] if prior_current else None
    today = _parse_date(current_session[-1].performed_at if current_session else latest.performed_at) if latest or current_session else None
    last_date = _parse_date(latest.performed_at) if latest else today
    days_since_last = max(0.0, (today - last_date).total_seconds() / 86400.0) if today and last_date else 0.0
    avg_recent_reps = sum(row.reps for row in recent) / max(1, len(recent))
    avg_recent_weight = sum(row.weight_kg for row in recent) / max(1, len(recent))
    avg_latest_reps = sum(row.reps for row in latest_session) / max(1, len(latest_session))
    avg_latest_weight = sum(row.weight_kg for row in latest_session) / max(1, len(latest_session))
    e1rm_trend = recent_e1rm[-1] - recent_e1rm[0] if len(recent_e1rm) >= 2 else 0.0

    return {
        "exercise": exercise,
        "set_index": set_index,
        "preferred_rep_mode": preferred_rep_mode,
        "preferred_rep_min": rep_min,
        "preferred_rep_max": rep_max,
        "history_count": len(ordered),
        "latest_weight_kg": latest.weight_kg if latest else 0.0,
        "latest_reps": latest.reps if latest else 0,
        "latest_set_index": latest.set_index if latest else 0,
        "matching_weight_kg": matching.weight_kg if matching else 0.0,
        "matching_reps": matching.reps if matching else 0,
        "avg_recent_reps": avg_recent_reps,
        "avg_recent_weight_kg": avg_recent_weight,
        "avg_latest_session_reps": avg_latest_reps,
        "avg_latest_session_weight_kg": avg_latest_weight,
        "best_recent_weight_kg": max((row.weight_kg for row in recent), default=0.0),
        "best_recent_e1rm": max(recent_e1rm, default=0.0),
        "e1rm_trend": e1rm_trend,
        "days_since_last": days_since_last,
        "current_session_sets": len(prior_current),
        "previous_current_weight_kg": previous_current.weight_kg if previous_current else 0.0,
        "previous_current_reps": previous_current.reps if previous_current else 0,
    }


def _load_for_rep_target(e1rm: float, reps: int) -> float:
    return _round_load(e1rm / (1.0 + max(1, reps) / 30.0))


def _pr_ramp_prediction(exercise: str, top_weight: float, set_index: int) -> ProgressionPrediction:
    # Sources used for the policy: ACSM 2026 position-stand overview for strength emphasis
    # around heavy loads, and NSCA dynamic warm-up guidance for gradual, non-fatiguing preparation.
    ramp = [
        (0.50, 8, 10, "warmup", 0.55, "pr_ramp_50"),
        (0.70, 4, 6, "warmup", 0.6, "pr_ramp_70"),
        (0.85, 2, 3, "warmup", 0.65, "pr_ramp_85"),
        (1.00, 1, 3, "top", 0.7, "pr_top_set"),
    ]
    ratio, reps_min, reps_max, target_kind, confidence, strategy = ramp[min(max(0, set_index - 1), len(ramp) - 1)]
    target_weight = _round_load(top_weight * ratio)
    target_reps = max(reps_min, min(reps_max, round((reps_min + reps_max) / 2)))
    return ProgressionPrediction(
        exercise=exercise,
        target_weight_kg=target_weight,
        target_reps=target_reps,
        target_reps_min=reps_min,
        target_reps_max=reps_max,
        confidence=confidence,
        model_version="progression_v2_preferences_e1rm",
        strategy=strategy,
        reason="PR mode uses a gradual warm-up ramp toward a heavy top set, grounded in personal estimated strength and non-fatiguing warm-up guidance.",
        target_kind=target_kind,
    )


def _predict_next_set_policy(
    exercise: str,
    history: list[SetObservation],
    set_index: int = 1,
    current_session: list[SetObservation] | None = None,
    preferred_rep_mode: str = "auto",
    preferred_rep_min: int = 8,
    preferred_rep_max: int = 10,
) -> ProgressionPrediction:
    """Predict the next set from personal history, set position, and same-session fatigue."""
    rep_min, rep_max = _normalize_rep_range(preferred_rep_mode, preferred_rep_min, preferred_rep_max)
    current_session = current_session or []
    prior_session_sets = [row for row in current_session if row.set_index < set_index]
    if prior_session_sets:
      previous = prior_session_sets[-1]
      previous_reps = previous.reps
      if len(prior_session_sets) >= 2:
          fatigue_drop = max(0, prior_session_sets[-2].reps - previous_reps)
      else:
          fatigue_drop = 1 if previous_reps <= 10 else 0
      if previous_reps >= 12:
           return ProgressionPrediction(
               exercise=exercise,
               target_weight_kg=_round_load(previous.weight_kg + 2.5),
              target_reps=rep_min,
              target_reps_min=rep_min,
              target_reps_max=rep_max,
              confidence=0.72,
              model_version="progression_v2_preferences_e1rm",
              strategy="increase_load_after_high_reps",
              reason="Earlier set exceeded the upper rep range; increase load slightly and rebuild reps.",
           )
      should_deload_for_fatigue = previous_reps <= rep_min
      next_reps = max(rep_min, min(rep_max, previous_reps - max(1, fatigue_drop)))
      return ProgressionPrediction(
          exercise=exercise,
          target_weight_kg=_round_load(previous.weight_kg - 2.5 if should_deload_for_fatigue else previous.weight_kg),
          target_reps=next_reps,
          target_reps_min=max(rep_min, next_reps - 1),
          target_reps_max=min(rep_max, next_reps + 1),
          confidence=0.78,
          model_version="progression_v2_preferences_e1rm",
          strategy="fatigue_deload" if should_deload_for_fatigue else "same_load_fatigue_adjusted_reps",
          reason="Previous set reached the lower rep target, so the next set lowers the load." if should_deload_for_fatigue else "Prediction follows the user's same-session fatigue pattern.",
      )

    ordered = sorted(history, key=lambda row: (row.performed_at, row.set_index))
    if not ordered:
        return ProgressionPrediction(
            exercise=exercise,
            target_weight_kg=0.0,
            target_reps=max(rep_min, min(rep_max, 8)),
            target_reps_min=rep_min,
            target_reps_max=rep_max,
            confidence=0.35,
            model_version="progression_v2_preferences_e1rm",
            strategy="cold_start_reps_only",
            reason="No personal history found. Start conservatively and log actual reps for personalization.",
        )

    latest_day = ordered[-1].performed_at[:10]
    latest_session = [row for row in ordered if row.performed_at[:10] == latest_day]
    matching = next((row for row in latest_session if row.set_index == set_index), latest_session[min(set_index - 1, len(latest_session) - 1)])
    avg_reps = sum(row.reps for row in latest_session) / max(1, len(latest_session))
    best_recent_weight = max(row.weight_kg for row in latest_session)
    recent_e1rm = [_estimate_epley(row.weight_kg, row.reps) for row in latest_session[-3:]]
    e1rm_trend = recent_e1rm[-1] - recent_e1rm[0] if len(recent_e1rm) >= 2 else 0.0
    estimated_top_weight = _load_for_rep_target(max(recent_e1rm), max(1, min(3, rep_max)))

    if preferred_rep_mode == "pr":
        return _pr_ramp_prediction(ordered[-1].exercise, max(best_recent_weight, estimated_top_weight), set_index)

    if set_index == 1 and avg_reps >= 10 and e1rm_trend >= -1.0:
        return ProgressionPrediction(
            exercise=ordered[-1].exercise,
            target_weight_kg=_load_for_rep_target(max(recent_e1rm), rep_min),
            target_reps=rep_min,
            target_reps_min=rep_min,
            target_reps_max=rep_max,
            confidence=0.68,
            model_version="progression_v2_preferences_e1rm",
            strategy="progressive_overload",
            reason="Latest session cleared the rep target and estimated strength did not decline.",
        )

    if avg_reps < 7:
        return ProgressionPrediction(
            exercise=ordered[-1].exercise,
            target_weight_kg=_round_load(max(0.0, matching.weight_kg - 2.5)),
            target_reps=rep_min,
            target_reps_min=rep_min,
            target_reps_max=rep_max,
            confidence=0.66,
            model_version="progression_v2_preferences_e1rm",
            strategy="load_backoff",
            reason="Recent reps were below target; reduce load slightly to rebuild useful volume.",
        )

    return ProgressionPrediction(
        exercise=ordered[-1].exercise,
        target_weight_kg=_load_for_rep_target(_estimate_epley(matching.weight_kg, matching.reps), max(rep_min, min(rep_max, matching.reps))),
        target_reps=max(rep_min, min(rep_max, matching.reps)),
        target_reps_min=rep_min,
        target_reps_max=rep_max,
        confidence=0.7,
        model_version="progression_v2_preferences_e1rm",
        strategy="repeat_matching_set",
        reason="Prediction uses the matching set from the latest personal session and adapts it to the preferred rep range.",
    )


@lru_cache(maxsize=1)
def _load_progression_bundle() -> dict[str, Any] | None:
    if not PROGRESSION_MODEL_PATH.exists():
        return None
    return joblib.load(PROGRESSION_MODEL_PATH)


def _predict_with_ml_artifact(
    *,
    exercise: str,
    history: list[SetObservation],
    set_index: int,
    current_session: list[SetObservation] | None,
    preferred_rep_mode: str,
    preferred_rep_min: int,
    preferred_rep_max: int,
    policy: ProgressionPrediction,
) -> ProgressionPrediction | None:
    if preferred_rep_mode == "pr" or policy.strategy == "cold_start_reps_only":
        return None
    bundle = _load_progression_bundle()
    if not bundle:
        return None
    model = bundle.get("model")
    if model is None:
        return None
    features = build_progression_feature_row(
        exercise=exercise,
        history=history,
        set_index=set_index,
        current_session=current_session,
        preferred_rep_mode=preferred_rep_mode,
        preferred_rep_min=preferred_rep_min,
        preferred_rep_max=preferred_rep_max,
    )
    predicted_weight, predicted_reps = model.predict([features])[0]
    rep_min, rep_max = _normalize_rep_range(preferred_rep_mode, preferred_rep_min, preferred_rep_max)
    if bundle.get("reps_source") == "policy_guardrail":
        target_reps = policy.target_reps
        target_reps_min = policy.target_reps_min
        target_reps_max = policy.target_reps_max
    else:
        target_reps = max(rep_min, min(rep_max, int(round(float(predicted_reps)))))
        target_reps_min = rep_min
        target_reps_max = rep_max
    target_weight = _round_load(float(predicted_weight))
    if target_weight <= 0:
        return None
    return ProgressionPrediction(
        exercise=policy.exercise,
        target_weight_kg=target_weight,
        target_reps=target_reps,
        target_reps_min=target_reps_min,
        target_reps_max=target_reps_max,
        confidence=min(0.86, max(policy.confidence, float(bundle.get("confidence", 0.72)))),
        model_version=str(bundle.get("model_version", "progression_v3_supervised_next_set")),
        strategy=str(bundle.get("strategy", "supervised_next_set_regressor")),
        reason=str(bundle.get("reason", "Supervised progression model predicted the next set from personal set history, same-session fatigue features, estimated strength trend, and the selected rep policy.")),
        target_kind=policy.target_kind,
    )


def predict_next_set(
    exercise: str,
    history: list[SetObservation],
    set_index: int = 1,
    current_session: list[SetObservation] | None = None,
    preferred_rep_mode: str = "auto",
    preferred_rep_min: int = 8,
    preferred_rep_max: int = 10,
) -> ProgressionPrediction:
    policy = _predict_next_set_policy(
        exercise=exercise,
        history=history,
        set_index=set_index,
        current_session=current_session,
        preferred_rep_mode=preferred_rep_mode,
        preferred_rep_min=preferred_rep_min,
        preferred_rep_max=preferred_rep_max,
    )
    ml_prediction = _predict_with_ml_artifact(
        exercise=exercise,
        history=history,
        set_index=set_index,
        current_session=current_session,
        preferred_rep_mode=preferred_rep_mode,
        preferred_rep_min=preferred_rep_min,
        preferred_rep_max=preferred_rep_max,
        policy=policy,
    )
    return ml_prediction or policy
