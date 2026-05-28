from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.business_hours import business_hours_label, is_business_open
from gymflow_core.weather_features import WEATHER_FEATURES, load_weather_features
from holiday_features import (
    days_to_nearest_major_holiday,
    holiday_effect_multiplier,
    is_gym_closed_holiday,
    is_major_holiday_window,
    is_major_low_traffic_holiday,
    is_public_holiday_ua,
)


FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
OBSERVATIONS_PATH = ROOT / "data" / "processed" / "occupancy_observations.csv"
MODEL_PATH = ROOT / "ml" / "models" / "artifacts" / "hist_gradient_boosting.joblib"
REPORTS_DIR = ROOT / "ml" / "reports"
FUTURE_FORECAST_PATH = REPORTS_DIR / "future_forecast_7d.csv"
ML_PREDICTIONS_PATH = REPORTS_DIR / "ml_predictions_sample.csv"
WEATHER_FUTURE_PATH = ROOT / "data" / "external" / "weather_future_features.csv"

CATEGORICAL_FEATURES = ["gym_id", "city", "address"]
NUMERIC_FEATURES = [
    "hour",
    "day_of_week",
    "is_weekend",
    "month",
    "day_of_month",
    "week_of_year",
    "is_open_estimated",
    "is_public_holiday_ua",
    "is_gym_closed_holiday",
    "is_major_low_traffic_holiday",
    "is_major_holiday_window",
    "days_to_nearest_major_holiday",
    "holiday_effect_multiplier",
    "lag_1",
    "lag_4",
    "lag_96",
    "rolling_mean_4",
    "rolling_mean_16",
    "rolling_mean_96",
    *WEATHER_FEATURES,
]

@dataclass(frozen=True)
class FutureForecastSummary:
    model: str
    rows: int
    gyms: int
    min_timestamp: str
    max_timestamp: str
    horizon_days: int
    interval_minutes: int


def infer_interval_minutes(df: pd.DataFrame) -> int:
    diffs: list[pd.Series] = []
    for _, group in df.groupby("gym_id"):
        diff = group.sort_values("timestamp")["timestamp"].diff().dropna().dt.total_seconds() / 60
        if not diff.empty:
            diffs.append(diff)
    if not diffs:
        return 20
    return max(5, int(round(pd.concat(diffs).median())))


def rolling(values: list[float], window: int) -> float:
    sample = values[-window:] if values else []
    if not sample:
        return float("nan")
    return float(np.mean(sample))


def load_uncertainty_lookup() -> tuple[dict[tuple[str, int], float], dict[int, float], float]:
    if not ML_PREDICTIONS_PATH.exists():
        return {}, {}, 8.0

    predictions = pd.read_csv(ML_PREDICTIONS_PATH)
    if "pred_hist_gradient_boosting" not in predictions.columns:
        return {}, {}, 8.0

    predictions["timestamp"] = pd.to_datetime(predictions["timestamp"])
    predictions["hour"] = predictions["timestamp"].dt.hour
    predictions["absolute_error"] = (
        pd.to_numeric(predictions["active_people"], errors="coerce")
        - pd.to_numeric(predictions["pred_hist_gradient_boosting"], errors="coerce")
    ).abs()
    predictions = predictions.dropna(subset=["absolute_error"])
    if predictions.empty:
        return {}, {}, 8.0

    gym_hour = (
        predictions.groupby(["gym_id", "hour"])["absolute_error"]
        .quantile(0.8)
        .to_dict()
    )
    by_hour = predictions.groupby("hour")["absolute_error"].quantile(0.8).to_dict()
    global_value = float(predictions["absolute_error"].quantile(0.8))
    return {(str(gym_id), int(hour)): float(value) for (gym_id, hour), value in gym_hour.items()}, {int(hour): float(value) for hour, value in by_hour.items()}, global_value


def uncertainty_for(gym_id: str, timestamp: pd.Timestamp, gym_hour: dict[tuple[str, int], float], by_hour: dict[int, float], global_value: float) -> float:
    return float(gym_hour.get((str(gym_id), int(timestamp.hour)), by_hour.get(int(timestamp.hour), global_value)))


def build_feature_row(timestamp: pd.Timestamp, gym_id: str, city: str, address: str, history: list[float]) -> dict[str, object]:
    return {
        "gym_id": gym_id,
        "city": city,
        "address": address,
        "hour": timestamp.hour,
        "day_of_week": timestamp.dayofweek,
        "is_weekend": 1 if timestamp.dayofweek >= 5 else 0,
        "month": timestamp.month,
        "day_of_month": timestamp.day,
        "week_of_year": int(timestamp.isocalendar().week),
        "is_open_estimated": is_business_open(timestamp),
        "is_public_holiday_ua": is_public_holiday_ua(timestamp),
        "is_gym_closed_holiday": is_gym_closed_holiday(timestamp),
        "is_major_low_traffic_holiday": is_major_low_traffic_holiday(timestamp),
        "is_major_holiday_window": is_major_holiday_window(timestamp),
        "days_to_nearest_major_holiday": days_to_nearest_major_holiday(timestamp),
        "holiday_effect_multiplier": holiday_effect_multiplier(timestamp),
        "lag_1": history[-1] if len(history) >= 1 else np.nan,
        "lag_4": history[-4] if len(history) >= 4 else np.nan,
        "lag_96": history[-96] if len(history) >= 96 else np.nan,
        "rolling_mean_4": rolling(history, 4),
        "rolling_mean_16": rolling(history, 16),
        "rolling_mean_96": rolling(history, 96),
    }


def next_forecast_start(last_observed_at: pd.Timestamp, interval_minutes: int, now: datetime | None = None) -> pd.Timestamp:
    last_based_start = last_observed_at + timedelta(minutes=interval_minutes)
    current = pd.Timestamp(now or datetime.now()).replace(second=0, microsecond=0)
    if current <= last_based_start:
        return last_based_start
    minutes = int(current.minute)
    remainder = minutes % interval_minutes
    if remainder:
        current += timedelta(minutes=interval_minutes - remainder)
    return current.replace(second=0, microsecond=0)


def generate_future_forecast(horizon_days: int = 7) -> FutureForecastSummary:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Missing model artifact: {MODEL_PATH}. Run scripts/run_ml_experiments.py first.")
    if not FEATURES_PATH.exists() or not OBSERVATIONS_PATH.exists():
        raise FileNotFoundError("Missing processed data. Run scripts/prepare_data.py first.")

    model = joblib.load(MODEL_PATH)
    observations = pd.read_csv(OBSERVATIONS_PATH)
    observations["timestamp"] = pd.to_datetime(observations["timestamp"])
    observations["active_people"] = pd.to_numeric(observations["active_people"], errors="coerce").fillna(0).clip(lower=0)
    interval_minutes = infer_interval_minutes(observations)
    weather = load_weather_features(WEATHER_FUTURE_PATH) if WEATHER_FUTURE_PATH.exists() else pd.DataFrame()
    uncertainty_by_gym_hour, uncertainty_by_hour, global_uncertainty = load_uncertainty_lookup()
    weather_map = {}
    if not weather.empty:
        weather_map = {
            (str(row.city), pd.Timestamp(row.timestamp_hour)): {feature: getattr(row, feature) for feature in WEATHER_FEATURES}
            for row in weather.itertuples(index=False)
        }

    start = next_forecast_start(observations["timestamp"].max(), interval_minutes)
    end = start + timedelta(days=horizon_days)
    future_timestamps = pd.date_range(start=start, end=end, freq=f"{interval_minutes}min", inclusive="left")

    gym_meta = (
        observations.sort_values("timestamp")
        .groupby("gym_id")[["city", "address"]]
        .last()
        .reset_index()
    )

    rows: list[dict[str, object]] = []
    for gym in gym_meta.itertuples(index=False):
        gym_history = (
            observations[observations["gym_id"] == gym.gym_id]
            .sort_values("timestamp")["active_people"]
            .astype(float)
            .tolist()
        )
        for timestamp in future_timestamps:
            feature_row = build_feature_row(timestamp, gym.gym_id, gym.city, gym.address, gym_history)
            weather_values = weather_map.get((str(gym.city), timestamp.floor("h")), {})
            for feature in WEATHER_FEATURES:
                feature_row[feature] = weather_values.get(feature, np.nan)
            feature_frame = pd.DataFrame([feature_row])[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
            prediction = float(np.clip(model.predict(feature_frame)[0], 0, None))
            if feature_row["is_gym_closed_holiday"] or not feature_row["is_open_estimated"]:
                prediction = 0.0
            uncertainty = uncertainty_for(gym.gym_id, timestamp, uncertainty_by_gym_hour, uncertainty_by_hour, global_uncertainty)
            if prediction == 0.0:
                uncertainty = 0.0
            gym_history.append(prediction)
            rows.append(
                {
                    "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "gym_id": gym.gym_id,
                    "city": gym.city,
                    "address": gym.address,
                    "prediction": round(prediction, 3),
                    "prediction_interval_low": round(max(0.0, prediction - uncertainty), 3),
                    "prediction_interval_high": round(prediction + uncertainty, 3),
                    "uncertainty_abs_error_p80": round(uncertainty, 3),
                    "uncertainty_method": "historical_holdout_abs_error_p80_by_gym_hour",
                    "model": "hist_gradient_boosting",
                    "is_weekend": feature_row["is_weekend"],
                    "is_open_estimated": feature_row["is_open_estimated"],
                    "business_hours": business_hours_label(timestamp),
                    "is_public_holiday_ua": feature_row["is_public_holiday_ua"],
                    "is_gym_closed_holiday": feature_row["is_gym_closed_holiday"],
                    "is_major_low_traffic_holiday": feature_row["is_major_low_traffic_holiday"],
                    "is_major_holiday_window": feature_row["is_major_holiday_window"],
                    "holiday_effect_multiplier": feature_row["holiday_effect_multiplier"],
                    "temperature_2m": feature_row.get("temperature_2m", ""),
                    "precipitation": feature_row.get("precipitation", ""),
                    "cloud_cover": feature_row.get("cloud_cover", ""),
                    "wind_speed_10m": feature_row.get("wind_speed_10m", ""),
                }
            )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(FUTURE_FORECAST_PATH, index=False)
    summary = FutureForecastSummary(
        model="hist_gradient_boosting",
        rows=len(rows),
        gyms=len(gym_meta),
        min_timestamp=rows[0]["timestamp"],
        max_timestamp=rows[-1]["timestamp"],
        horizon_days=horizon_days,
        interval_minutes=interval_minutes,
    )
    (REPORTS_DIR / "future_forecast_7d_summary.json").write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    generate_future_forecast()
