from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
REAL_FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
RESEARCH_FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_research_features.csv"
REPORTS_DIR = ROOT / "ml" / "reports"

TARGET = "active_people"
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
]


@dataclass(frozen=True)
class SyntheticTrainingMetric:
    experiment: str
    model: str
    train_rows: int
    synthetic_train_rows: int
    test_rows: int
    mae: float
    rmse: float
    wape: float


def load_real_dataset() -> pd.DataFrame:
    if not REAL_FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing real features file: {REAL_FEATURES_PATH}. Run make data first.")
    df = pd.read_csv(REAL_FEATURES_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for column in [TARGET, *NUMERIC_FEATURES]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)


def load_synthetic_supplement(max_ratio_to_real_train: int, real_train_rows: int) -> pd.DataFrame:
    if not RESEARCH_FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing research feature file: {RESEARCH_FEATURES_PATH}. Run make synthetic first.")
    df = pd.read_csv(RESEARCH_FEATURES_PATH)
    if "is_synthetic" not in df.columns:
        return pd.DataFrame(columns=df.columns)
    df = df[df["is_synthetic"].astype(str) == "1"].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for column in [TARGET, *NUMERIC_FEATURES]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    max_rows = max(0, real_train_rows * max_ratio_to_real_train)
    if len(df) > max_rows:
        df = df.sort_values(["gym_id", "timestamp"]).groupby("gym_id", group_keys=False).head(max_rows // max(1, df["gym_id"].nunique()))
    return df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)


def split_by_time_per_gym(df: pd.DataFrame, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _, group in df.groupby("gym_id", sort=False):
        group = group.sort_values("timestamp")
        split_index = max(1, int(len(group) * train_ratio))
        train_parts.append(group.iloc[:split_index])
        test_parts.append(group.iloc[split_index:])
    return pd.concat(train_parts, ignore_index=True), pd.concat(test_parts, ignore_index=True)


def make_pipeline() -> Pipeline:
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
            ("num", numeric_pipeline, NUMERIC_FEATURES),
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


def calculate_metric(
    experiment: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    train_rows: int,
    synthetic_train_rows: int,
) -> SyntheticTrainingMetric:
    y_pred = np.clip(y_pred, 0, None)
    absolute_errors = np.abs(y_true - y_pred)
    actual_total = np.sum(np.abs(y_true))
    return SyntheticTrainingMetric(
        experiment=experiment,
        model="hist_gradient_boosting",
        train_rows=train_rows,
        synthetic_train_rows=synthetic_train_rows,
        test_rows=len(y_true),
        mae=round(float(mean_absolute_error(y_true, y_pred)), 4),
        rmse=round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        wape=round(float(np.sum(absolute_errors) / actual_total), 4) if actual_total else 0.0,
    )


def evaluate(train_df: pd.DataFrame, test_df: pd.DataFrame, experiment: str, synthetic_train_rows: int) -> SyntheticTrainingMetric:
    columns = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    model = make_pipeline()
    model.fit(train_df[columns], train_df[TARGET].astype(float).to_numpy())
    y_true = test_df[TARGET].astype(float).to_numpy()
    y_pred = model.predict(test_df[columns])
    return calculate_metric(experiment, y_true, y_pred, len(train_df), synthetic_train_rows)


def write_report(metrics: list[SyntheticTrainingMetric]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    records = [asdict(metric) for metric in sorted(metrics, key=lambda item: item.mae)]
    pd.DataFrame(records).to_csv(REPORTS_DIR / "synthetic_training_metrics.csv", index=False)
    (REPORTS_DIR / "synthetic_training_metrics.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Real-Only vs Real+Synthetic Training Experiment",
        "",
        "Date: 2026-05-24",
        "",
        "This diagnostic experiment evaluates whether adding the generated synthetic scenario extension to the training set improves performance on the same real holdout.",
        "",
        "Important limitation: synthetic rows are scenario data generated from the project profiles. They are not direct real observations and should not be presented as new empirical collection.",
        "",
        "| Experiment | Train rows | Synthetic train rows | Test rows | MAE | RMSE | WAPE |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in records:
        lines.append(
            f'| {row["experiment"]} | {row["train_rows"]} | {row["synthetic_train_rows"]} | {row["test_rows"]} | {row["mae"]} | {row["rmse"]} | {row["wape"]} |'
        )
    lines.extend(
        [
            "",
            "Interpretation should be based on the actual metric difference. If the synthetic supplement does not improve the real holdout, it is still useful for scenario demos and stress testing, not as a replacement for real collection.",
        ]
    )
    (REPORTS_DIR / "synthetic_training_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(records, ensure_ascii=False, indent=2))


def main() -> None:
    real_df = load_real_dataset()
    real_train_df, real_test_df = split_by_time_per_gym(real_df)
    synthetic_df = load_synthetic_supplement(max_ratio_to_real_train=3, real_train_rows=len(real_train_df))
    combined_train_df = pd.concat([real_train_df, synthetic_df], ignore_index=True, sort=False)
    metrics = [
        evaluate(real_train_df, real_test_df, "real_only_train_real_holdout", synthetic_train_rows=0),
        evaluate(combined_train_df, real_test_df, "real_plus_synthetic_train_real_holdout", synthetic_train_rows=len(synthetic_df)),
    ]
    write_report(metrics)


if __name__ == "__main__":
    main()
