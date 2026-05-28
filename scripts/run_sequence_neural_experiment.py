from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.weather_features import WEATHER_FEATURES, join_weather


FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
WEATHER_PATH = ROOT / "data" / "external" / "weather_observation_features.csv"
REPORTS_DIR = ROOT / "ml" / "reports"

TARGET = "active_people"
SEQUENCE_WINDOW = 12
CONTEXT_FEATURES = [
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
    *WEATHER_FEATURES,
]


@dataclass(frozen=True)
class SequenceMetric:
    model: str
    scope: str
    sequence_window: int
    train_rows: int
    test_rows: int
    mae: float
    rmse: float
    wape: float


def load_dataset() -> pd.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing features file: {FEATURES_PATH}. Run make data first.")
    df = pd.read_csv(FEATURES_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if WEATHER_PATH.exists():
        df = join_weather(df, WEATHER_PATH)
    for column in [TARGET, *CONTEXT_FEATURES]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)


def build_sequences(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    rows: list[dict[str, float | str]] = []
    targets: list[float] = []
    for gym_id, group in df.groupby("gym_id", sort=False):
        group = group.sort_values("timestamp").reset_index(drop=True)
        counts = group[TARGET].astype(float).to_numpy()
        for index in range(SEQUENCE_WINDOW, len(group)):
            row: dict[str, float | str] = {
                "gym_id": str(gym_id),
                "timestamp": group.loc[index, "timestamp"],
            }
            for lag_index in range(SEQUENCE_WINDOW):
                row[f"seq_lag_{lag_index + 1}"] = float(counts[index - lag_index - 1])
            for feature in CONTEXT_FEATURES:
                row[feature] = group.loc[index, feature]
            rows.append(row)
            targets.append(float(counts[index]))
    if not rows:
        raise ValueError("Not enough rows to build sequence dataset.")
    return pd.DataFrame(rows), np.asarray(targets, dtype=float)


def split_by_time_per_gym(sequence_df: pd.DataFrame, targets: np.ndarray, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
    sequence_df = sequence_df.copy()
    sequence_df["target"] = targets
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _, group in sequence_df.groupby("gym_id", sort=False):
        group = group.sort_values("timestamp")
        split_index = max(1, int(len(group) * train_ratio))
        train_parts.append(group.iloc[:split_index])
        test_parts.append(group.iloc[split_index:])
    train_df = pd.concat(train_parts, ignore_index=True)
    test_df = pd.concat(test_parts, ignore_index=True)
    return train_df, test_df, train_df.pop("target").to_numpy(), test_df.pop("target").to_numpy()


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray, train_rows: int) -> SequenceMetric:
    y_pred = np.clip(y_pred, 0, None)
    absolute_errors = np.abs(y_true - y_pred)
    actual_total = np.sum(np.abs(y_true))
    return SequenceMetric(
        model="mlp_sequence_regressor",
        scope="all_gyms_pooled_flattened_sequence",
        sequence_window=SEQUENCE_WINDOW,
        train_rows=train_rows,
        test_rows=len(y_true),
        mae=round(float(mean_absolute_error(y_true, y_pred)), 4),
        rmse=round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        wape=round(float(np.sum(absolute_errors) / actual_total), 4) if actual_total else 0.0,
    )


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load_dataset()
    sequence_df, targets = build_sequences(df)
    train_df, test_df, y_train, y_test = split_by_time_per_gym(sequence_df, targets)
    feature_columns = [column for column in train_df.columns if column not in {"gym_id", "timestamp"}]

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                MLPRegressor(
                    hidden_layer_sizes=(96, 48),
                    activation="relu",
                    solver="adam",
                    alpha=0.001,
                    learning_rate_init=0.001,
                    max_iter=260,
                    early_stopping=True,
                    validation_fraction=0.12,
                    n_iter_no_change=16,
                    random_state=42,
                ),
            ),
        ]
    )
    model.fit(train_df[feature_columns], y_train)
    y_pred = model.predict(test_df[feature_columns])
    metric = calculate_metrics(y_test, y_pred, train_rows=len(train_df))
    records = [asdict(metric)]
    pd.DataFrame(records).to_csv(REPORTS_DIR / "sequence_neural_metrics.csv", index=False)
    (REPORTS_DIR / "sequence_neural_metrics.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
