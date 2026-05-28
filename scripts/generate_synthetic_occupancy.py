from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.business_hours import is_business_open
from holiday_features import holiday_effect_multiplier, is_gym_closed_holiday, is_public_holiday_ua
from prepare_data import add_features, write_csv


OBSERVATIONS_PATH = ROOT / "data" / "processed" / "occupancy_observations.csv"
SYNTHETIC_DIR = ROOT / "data" / "synthetic"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "ml" / "reports"

SYNTHETIC_MONTHS = 6
SYNTHETIC_DAYS = 183
RANDOM_SEED = 42

@dataclass(frozen=True)
class SyntheticSummary:
    real_rows: int
    synthetic_rows: int
    extended_rows: int
    gyms: int
    real_min_timestamp: str
    real_max_timestamp: str
    synthetic_min_timestamp: str
    synthetic_max_timestamp: str
    synthetic_days: int
    interval_minutes: int
    random_seed: int
    method: str


def load_real_observations() -> pd.DataFrame:
    if not OBSERVATIONS_PATH.exists():
        raise FileNotFoundError(f"Missing observations file: {OBSERVATIONS_PATH}")

    df = pd.read_csv(OBSERVATIONS_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["active_people"] = pd.to_numeric(df["active_people"], errors="coerce").fillna(0).clip(lower=0)
    df["is_synthetic"] = 0
    df["generation_method"] = "normalized_2026_raw_observation"
    return df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)


def infer_interval_minutes(df: pd.DataFrame) -> int:
    diffs: list[pd.Series] = []
    for _, group in df.groupby("gym_id"):
        diff = group.sort_values("timestamp")["timestamp"].diff().dropna().dt.total_seconds() / 60
        if not diff.empty:
            diffs.append(diff)
    if not diffs:
        return 20
    return max(5, int(round(pd.concat(diffs).median())))


def build_profiles(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    profiled = df.copy()
    profiled["day_of_week"] = profiled["timestamp"].dt.dayofweek
    profiled["hour"] = profiled["timestamp"].dt.hour

    hourly_profile = (
        profiled.groupby(["gym_id", "day_of_week", "hour"])["active_people"]
        .agg(["mean", "std"])
        .reset_index()
        .rename(columns={"mean": "profile_mean", "std": "profile_std"})
    )
    hourly_profile["profile_std"] = hourly_profile["profile_std"].fillna(0)

    fallback_profile = (
        profiled.groupby(["gym_id", "hour"])["active_people"]
        .agg(["mean", "std"])
        .reset_index()
        .rename(columns={"mean": "fallback_mean", "std": "fallback_std"})
    )
    fallback_profile["fallback_std"] = fallback_profile["fallback_std"].fillna(0)

    profiled["expected"] = profiled.groupby(["gym_id", "day_of_week", "hour"])["active_people"].transform("mean")
    residuals = (profiled["active_people"] - profiled["expected"]).dropna().to_numpy()
    if len(residuals) == 0:
        residuals = np.array([0.0])

    return hourly_profile, fallback_profile, residuals


def seasonal_multiplier(timestamp: pd.Timestamp) -> float:
    if timestamp.month in {6, 7, 8}:
        return 0.92
    if timestamp.month in {10, 11}:
        return 1.05
    return 1.0


def synthesize() -> SyntheticSummary:
    rng = np.random.default_rng(RANDOM_SEED)
    real_df = load_real_observations()
    interval_minutes = infer_interval_minutes(real_df)
    hourly_profile, fallback_profile, residuals = build_profiles(real_df)

    profile_map = {
        (row.gym_id, int(row.day_of_week), int(row.hour)): (float(row.profile_mean), float(row.profile_std))
        for row in hourly_profile.itertuples(index=False)
    }
    fallback_map = {
        (row.gym_id, int(row.hour)): (float(row.fallback_mean), float(row.fallback_std))
        for row in fallback_profile.itertuples(index=False)
    }

    gym_meta = (
        real_df.sort_values("timestamp")
        .groupby("gym_id")[["city", "address"]]
        .last()
        .reset_index()
    )
    start = real_df["timestamp"].max() + timedelta(minutes=interval_minutes)
    end = start + timedelta(days=SYNTHETIC_DAYS)
    timestamps = pd.date_range(start=start, end=end, freq=f"{interval_minutes}min", inclusive="left")

    rows: list[dict[str, object]] = []
    for gym in gym_meta.itertuples(index=False):
        trend = rng.normal(0.0, 0.004)
        for step, timestamp in enumerate(timestamps):
            key = (gym.gym_id, int(timestamp.dayofweek), int(timestamp.hour))
            fallback_key = (gym.gym_id, int(timestamp.hour))
            mean, std = profile_map.get(key, fallback_map.get(fallback_key, (real_df["active_people"].mean(), 8.0)))
            residual = rng.choice(residuals)
            smooth_noise = rng.normal(0, max(1.5, std * 0.18))
            synthetic_value = (
                mean
                * holiday_effect_multiplier(timestamp)
                * seasonal_multiplier(timestamp)
                * (1 + trend * (step / max(1, len(timestamps))))
                + residual * 0.35
                + smooth_noise
            )
            active_people = int(round(np.clip(synthetic_value, 0, 260)))
            if is_gym_closed_holiday(timestamp) or not is_business_open(timestamp):
                active_people = 0
            rows.append(
                {
                    "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "city": gym.city,
                    "address": gym.address,
                    "active_people": active_people,
                    "source_file": "synthetic_profile_bootstrap",
                    "gym_id": gym.gym_id,
                    "is_synthetic": 1,
                    "generation_method": "profile_bootstrap_calendar_holiday_seasonality",
                }
            )

    synthetic_df = pd.DataFrame(rows)
    real_aligned = real_df[
        ["timestamp", "city", "address", "active_people", "source_file", "gym_id", "is_synthetic", "generation_method"]
    ].copy()
    real_aligned["timestamp"] = real_aligned["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    extended = pd.concat([real_aligned, synthetic_df], ignore_index=True)
    extended = extended.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)

    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    synthetic_path = SYNTHETIC_DIR / "occupancy_synthetic_6m.csv"
    extended_path = PROCESSED_DIR / "occupancy_research_extended.csv"
    features_path = PROCESSED_DIR / "occupancy_research_features.csv"

    synthetic_df.to_csv(synthetic_path, index=False)
    extended.to_csv(extended_path, index=False)

    metadata_map = {
        (str(row.timestamp), str(row.gym_id)): (int(row.is_synthetic), str(row.generation_method))
        for row in extended.itertuples(index=False)
    }

    feature_rows = add_features(
        extended[
            ["timestamp", "city", "address", "active_people", "source_file", "gym_id"]
        ].astype(str).to_dict("records")
    )
    for row in feature_rows:
        is_synthetic, generation_method = metadata_map[(row["timestamp"], row["gym_id"])]
        row["is_synthetic"] = str(is_synthetic)
        row["generation_method"] = generation_method
        ts = pd.Timestamp(row["timestamp"])
        row["is_public_holiday_ua"] = str(is_public_holiday_ua(ts))
        row["is_gym_closed_holiday"] = str(is_gym_closed_holiday(ts))
        row["seasonal_period"] = "summer" if ts.month in {6, 7, 8} else "autumn" if ts.month in {9, 10, 11} else "spring"
    write_csv(features_path, feature_rows)

    summary = SyntheticSummary(
        real_rows=len(real_df),
        synthetic_rows=len(synthetic_df),
        extended_rows=len(extended),
        gyms=real_df["gym_id"].nunique(),
        real_min_timestamp=real_df["timestamp"].min().strftime("%Y-%m-%d %H:%M:%S"),
        real_max_timestamp=real_df["timestamp"].max().strftime("%Y-%m-%d %H:%M:%S"),
        synthetic_min_timestamp=synthetic_df["timestamp"].min(),
        synthetic_max_timestamp=synthetic_df["timestamp"].max(),
        synthetic_days=SYNTHETIC_DAYS,
        interval_minutes=interval_minutes,
        random_seed=RANDOM_SEED,
        method="Gym/hour/weekday profile bootstrap with residual noise, weekend, holiday, and seasonal multipliers.",
    )
    (REPORTS_DIR / "synthetic_data_summary.json").write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    synthesize()
