from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.weather_features import WEATHER_FEATURES, join_weather

FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
WEATHER_PATH = ROOT / "data" / "external" / "weather_observation_features.csv"
REPORTS_DIR = ROOT / "ml" / "reports"

TARGET = "active_people"
CATEGORICAL_FEATURES = ["gym_id", "city", "address"]
BASE_NUMERIC_FEATURES = [
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
]
@dataclass(frozen=True)
class WeatherAblationMetric:
    feature_set: str
    model: str
    train_rows: int
    test_rows: int
    matched_weather_rows: int
    mae: float
    rmse: float
    wape: float


def load_base_features() -> pd.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing features file: {FEATURES_PATH}. Run make data first.")
    df = pd.read_csv(FEATURES_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["timestamp_hour"] = df["timestamp"].dt.floor("h")
    for column in BASE_NUMERIC_FEATURES + [TARGET]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)


def load_weather() -> pd.DataFrame:
    if not WEATHER_PATH.exists():
        raise FileNotFoundError(f"Missing weather file: {WEATHER_PATH}. Run make weather-observed first.")
    weather = pd.read_csv(WEATHER_PATH)
    weather["timestamp_hour"] = pd.to_datetime(weather["timestamp_hour"])
    for column in WEATHER_FEATURES:
        weather[column] = pd.to_numeric(weather[column], errors="coerce")
    weather = weather.sort_values(["city", "timestamp_hour", "weather_source"]).drop_duplicates(
        subset=["city", "timestamp_hour"],
        keep="last",
    )
    return weather[["city", "timestamp_hour", *WEATHER_FEATURES]]


def build_weather_dataset() -> tuple[pd.DataFrame, int]:
    base = load_base_features()
    joined = join_weather(base.drop(columns=["timestamp_hour"]), WEATHER_PATH)
    weather = load_weather()
    matched = int(joined[WEATHER_FEATURES].notna().all(axis=1).sum())
    return joined, matched


def split_by_time_per_gym(df: pd.DataFrame, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _, group in df.groupby("gym_id", sort=False):
        group = group.sort_values("timestamp")
        split_index = max(1, int(len(group) * train_ratio))
        train_parts.append(group.iloc[:split_index])
        test_parts.append(group.iloc[split_index:])
    return pd.concat(train_parts, ignore_index=True), pd.concat(test_parts, ignore_index=True)


def make_model(numeric_features: list[str]) -> Pipeline:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_features),
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            (
                "model",
                HistGradientBoostingRegressor(
                    max_iter=240,
                    learning_rate=0.06,
                    max_leaf_nodes=31,
                    l2_regularization=0.05,
                    random_state=42,
                ),
            ),
        ]
    )


def calculate_metrics(feature_set: str, y_true: np.ndarray, y_pred: np.ndarray, train_rows: int, matched_weather_rows: int) -> WeatherAblationMetric:
    y_pred = np.clip(y_pred, 0, None)
    absolute_errors = np.abs(y_true - y_pred)
    actual_total = np.sum(np.abs(y_true))
    return WeatherAblationMetric(
        feature_set=feature_set,
        model="hist_gradient_boosting",
        train_rows=train_rows,
        test_rows=len(y_true),
        matched_weather_rows=matched_weather_rows,
        mae=round(float(mean_absolute_error(y_true, y_pred)), 4),
        rmse=round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        wape=round(float(np.sum(absolute_errors) / actual_total), 4) if actual_total else 0.0,
    )


def run_experiment() -> list[WeatherAblationMetric]:
    df, matched_weather_rows = build_weather_dataset()
    train_df, test_df = split_by_time_per_gym(df)
    y_train = train_df[TARGET].astype(float).to_numpy()
    y_test = test_df[TARGET].astype(float).to_numpy()

    metrics: list[WeatherAblationMetric] = []
    feature_sets = {
        "base_without_weather": BASE_NUMERIC_FEATURES,
        "base_with_weather": BASE_NUMERIC_FEATURES + WEATHER_FEATURES,
    }
    for feature_set, numeric_features in feature_sets.items():
        model = make_model(numeric_features)
        model.fit(train_df[CATEGORICAL_FEATURES + numeric_features], y_train)
        y_pred = model.predict(test_df[CATEGORICAL_FEATURES + numeric_features])
        metrics.append(
            calculate_metrics(
                feature_set=feature_set,
                y_true=y_test,
                y_pred=y_pred,
                train_rows=len(train_df),
                matched_weather_rows=matched_weather_rows,
            )
        )
    return sorted(metrics, key=lambda row: (row.mae, row.rmse))


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics = run_experiment()
    records = [asdict(row) for row in metrics]
    pd.DataFrame(records).to_csv(REPORTS_DIR / "weather_ablation_metrics.csv", index=False)
    (REPORTS_DIR / "weather_ablation_metrics.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
