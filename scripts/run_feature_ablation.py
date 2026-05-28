from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
REPORTS_DIR = ROOT / "ml" / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

TARGET = "active_people"
CATEGORICAL_FEATURES = ["gym_id", "city", "address"]
CALENDAR_FEATURES = ["hour", "day_of_week", "is_weekend", "month", "day_of_month", "week_of_year", "is_open_estimated"]
HOLIDAY_FEATURES = [
    "is_public_holiday_ua",
    "is_gym_closed_holiday",
    "is_major_low_traffic_holiday",
    "is_major_holiday_window",
    "days_to_nearest_major_holiday",
    "holiday_effect_multiplier",
]
LAG_FEATURES = ["lag_1", "lag_4", "lag_96"]
ROLLING_FEATURES = ["rolling_mean_4", "rolling_mean_16", "rolling_mean_96"]

FEATURE_GROUPS = {
    "calendar_only": CALENDAR_FEATURES,
    "calendar_holiday": CALENDAR_FEATURES + HOLIDAY_FEATURES,
    "lag_only": LAG_FEATURES,
    "rolling_only": ROLLING_FEATURES,
    "calendar_lag": CALENDAR_FEATURES + LAG_FEATURES,
    "calendar_holiday_lag": CALENDAR_FEATURES + HOLIDAY_FEATURES + LAG_FEATURES,
    "calendar_rolling": CALENDAR_FEATURES + ROLLING_FEATURES,
    "lag_rolling": LAG_FEATURES + ROLLING_FEATURES,
    "all_features": CALENDAR_FEATURES + HOLIDAY_FEATURES + LAG_FEATURES + ROLLING_FEATURES,
}


@dataclass(frozen=True)
class AblationMetric:
    feature_group: str
    model: str
    train_rows: int
    test_rows: int
    mae: float
    rmse: float
    wape: float


def load_dataset() -> pd.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing features file: {FEATURES_PATH}. Run scripts/prepare_data.py first.")

    df = pd.read_csv(FEATURES_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)
    for column in CALENDAR_FEATURES + HOLIDAY_FEATURES + LAG_FEATURES + ROLLING_FEATURES + [TARGET]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def split_by_time_per_gym(df: pd.DataFrame, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _, group in df.groupby("gym_id", sort=False):
        group = group.sort_values("timestamp")
        split_index = max(1, int(len(group) * train_ratio))
        train_parts.append(group.iloc[:split_index])
        test_parts.append(group.iloc[split_index:])
    return pd.concat(train_parts, ignore_index=True), pd.concat(test_parts, ignore_index=True)


def make_pipeline(numeric_features: list[str]) -> Pipeline:
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
                    max_iter=200,
                    learning_rate=0.06,
                    max_leaf_nodes=31,
                    l2_regularization=0.05,
                    random_state=42,
                ),
            ),
        ]
    )


def calculate_metrics(feature_group: str, y_true: np.ndarray, y_pred: np.ndarray, train_rows: int) -> AblationMetric:
    y_pred = np.clip(y_pred, 0, None)
    absolute_errors = np.abs(y_true - y_pred)
    actual_total = np.sum(np.abs(y_true))
    return AblationMetric(
        feature_group=feature_group,
        model="hist_gradient_boosting",
        train_rows=train_rows,
        test_rows=len(y_true),
        mae=round(float(mean_absolute_error(y_true, y_pred)), 4),
        rmse=round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        wape=round(float(np.sum(absolute_errors) / actual_total), 4) if actual_total else 0.0,
    )


def run_ablation() -> list[AblationMetric]:
    df = load_dataset()
    train_df, test_df = split_by_time_per_gym(df)
    y_train = train_df[TARGET].astype(float).to_numpy()
    y_test = test_df[TARGET].astype(float).to_numpy()

    metrics: list[AblationMetric] = []
    for group_name, numeric_features in FEATURE_GROUPS.items():
        columns = CATEGORICAL_FEATURES + numeric_features
        pipeline = make_pipeline(numeric_features)
        pipeline.fit(train_df[columns], y_train)
        predictions = pipeline.predict(test_df[columns])
        metrics.append(calculate_metrics(group_name, y_test, predictions, len(train_df)))

    return sorted(metrics, key=lambda item: (item.mae, item.rmse))


def write_outputs(metrics: list[AblationMetric]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    records = [asdict(metric) for metric in metrics]
    metrics_df = pd.DataFrame(records)
    metrics_df.to_csv(REPORTS_DIR / "feature_ablation_metrics.csv", index=False)
    (REPORTS_DIR / "feature_ablation_metrics.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    plot_df = metrics_df.sort_values("mae", ascending=True)
    plt.figure(figsize=(10, 5.4))
    plt.barh(plot_df["feature_group"], plot_df["mae"], color="#ff7a2d")
    plt.xlabel("MAE")
    plt.ylabel("Feature group")
    plt.title("Feature ablation by MAE")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "feature_ablation_mae.png", dpi=180)
    plt.close()

    best = records[0]
    worst = records[-1]
    report = f"""# Feature Ablation Report

Date: 2026-05-23

## Purpose

This experiment evaluates how different feature groups affect gym occupancy forecasting quality on the normalized 2026 dataset.

## Data

- Dataset: `data/processed/occupancy_features.csv`
- Split: time-respecting 80/20 split per gym
- Model: HistGradientBoostingRegressor
- Metrics: MAE, RMSE, WAPE

## Result Summary

Best feature group: `{best["feature_group"]}` with MAE `{best["mae"]}`, RMSE `{best["rmse"]}`, WAPE `{best["wape"]}`.

Weakest feature group: `{worst["feature_group"]}` with MAE `{worst["mae"]}`, RMSE `{worst["rmse"]}`, WAPE `{worst["wape"]}`.

## Full Table

| Feature group | MAE | RMSE | WAPE |
|---|---:|---:|---:|
"""
    for row in records:
        report += f'| {row["feature_group"]} | {row["mae"]} | {row["rmse"]} | {row["wape"]} |\n'

    report += """
## Interpretation

The ablation isolates the contribution of calendar, lag, and rolling-window features while keeping gym identity features available in every run. The result should be used in the thesis to justify the final forecasting feature set instead of presenting the model as a black box.

## Figure

`ml/reports/figures/feature_ablation_mae.png`
"""
    (REPORTS_DIR / "feature_ablation_report.md").write_text(report, encoding="utf-8")
    print(json.dumps(records, ensure_ascii=False, indent=2))


def main() -> None:
    write_outputs(run_ablation())


if __name__ == "__main__":
    main()
