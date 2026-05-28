from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
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
ARTIFACTS_DIR = ROOT / "ml" / "models" / "artifacts"

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
    *WEATHER_FEATURES,
]


@dataclass(frozen=True)
class ExperimentMetric:
    model: str
    scope: str
    train_rows: int
    test_rows: int
    mae: float
    rmse: float
    wape: float


def load_dataset() -> pd.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"Missing features file: {FEATURES_PATH}. Run scripts/prepare_data.py first."
        )

    df = pd.read_csv(FEATURES_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if WEATHER_PATH.exists():
        df = join_weather(df, WEATHER_PATH)
    df = df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)

    for column in NUMERIC_FEATURES + [TARGET]:
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

    train_df = pd.concat(train_parts, ignore_index=True)
    test_df = pd.concat(test_parts, ignore_index=True)
    return train_df, test_df


def make_preprocessor(dense: bool = True) -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=not dense)),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUMERIC_FEATURES),
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )


def make_models() -> dict[str, Pipeline]:
    return {
        "ridge_regression": Pipeline(
            steps=[
                ("preprocess", make_preprocessor(dense=False)),
                ("model", Ridge(alpha=1.0)),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                ("preprocess", make_preprocessor(dense=True)),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=160,
                        max_depth=14,
                        min_samples_leaf=4,
                        random_state=42,
                        n_jobs=1,
                    ),
                ),
            ]
        ),
        "hist_gradient_boosting": Pipeline(
            steps=[
                ("preprocess", make_preprocessor(dense=True)),
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
        ),
    }


def calculate_metrics(model_name: str, scope: str, y_true: np.ndarray, y_pred: np.ndarray, train_rows: int) -> ExperimentMetric:
    y_pred = np.clip(y_pred, 0, None)
    absolute_errors = np.abs(y_true - y_pred)
    actual_total = np.sum(np.abs(y_true))
    return ExperimentMetric(
        model=model_name,
        scope=scope,
        train_rows=train_rows,
        test_rows=len(y_true),
        mae=round(float(mean_absolute_error(y_true, y_pred)), 4),
        rmse=round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        wape=round(float(np.sum(absolute_errors) / actual_total), 4) if actual_total else 0.0,
    )


def run_pooled_models(train_df: pd.DataFrame, test_df: pd.DataFrame) -> list[ExperimentMetric]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    X_train = train_df[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_train = train_df[TARGET].astype(float).to_numpy()
    X_test = test_df[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_test = test_df[TARGET].astype(float).to_numpy()

    metrics: list[ExperimentMetric] = []
    predictions = test_df[["timestamp", "gym_id", "city", "address", TARGET]].copy()

    for model_name, pipeline in make_models().items():
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        metrics.append(
            calculate_metrics(
                model_name=model_name,
                scope="all_gyms_pooled",
                y_true=y_test,
                y_pred=y_pred,
                train_rows=len(train_df),
            )
        )
        predictions[f"pred_{model_name}"] = np.clip(y_pred, 0, None)
        joblib.dump(pipeline, ARTIFACTS_DIR / f"{model_name}.joblib")

    predictions.to_csv(REPORTS_DIR / "ml_predictions_sample.csv", index=False)
    write_error_analysis(predictions, "hist_gradient_boosting")
    return metrics


def write_error_analysis(predictions: pd.DataFrame, model_name: str) -> None:
    prediction_column = f"pred_{model_name}"
    if prediction_column not in predictions.columns:
        return

    analysis_df = predictions.copy()
    analysis_df["timestamp"] = pd.to_datetime(analysis_df["timestamp"])
    analysis_df["hour"] = analysis_df["timestamp"].dt.hour
    analysis_df["day_of_week"] = analysis_df["timestamp"].dt.dayofweek
    analysis_df["absolute_error"] = (analysis_df[TARGET] - analysis_df[prediction_column]).abs()
    analysis_df["squared_error"] = (analysis_df[TARGET] - analysis_df[prediction_column]) ** 2

    by_hour = (
        analysis_df.groupby("hour")
        .agg(
            rows=("absolute_error", "size"),
            mae=("absolute_error", "mean"),
            rmse=("squared_error", lambda values: float(np.sqrt(values.mean()))),
            avg_actual=(TARGET, "mean"),
            avg_prediction=(prediction_column, "mean"),
        )
        .reset_index()
    )
    by_hour.to_csv(REPORTS_DIR / "error_by_hour.csv", index=False)

    by_weekday = (
        analysis_df.groupby("day_of_week")
        .agg(
            rows=("absolute_error", "size"),
            mae=("absolute_error", "mean"),
            rmse=("squared_error", lambda values: float(np.sqrt(values.mean()))),
            avg_actual=(TARGET, "mean"),
            avg_prediction=(prediction_column, "mean"),
        )
        .reset_index()
    )
    by_weekday.to_csv(REPORTS_DIR / "error_by_weekday.csv", index=False)

    by_gym = (
        analysis_df.groupby(["gym_id", "city", "address"])
        .agg(
            rows=("absolute_error", "size"),
            mae=("absolute_error", "mean"),
            rmse=("squared_error", lambda values: float(np.sqrt(values.mean()))),
            avg_actual=(TARGET, "mean"),
            avg_prediction=(prediction_column, "mean"),
        )
        .reset_index()
        .sort_values("mae", ascending=False)
    )
    by_gym.to_csv(REPORTS_DIR / "error_by_gym.csv", index=False)


def run_arima_selected_gym(df: pd.DataFrame) -> ExperimentMetric | None:
    try:
        from statsmodels.tsa.arima.model import ARIMA
    except Exception:
        return None

    gym_counts = df.groupby("gym_id").size().sort_values(ascending=False)
    if gym_counts.empty:
        return None

    selected_gym = gym_counts.index[0]
    series_df = df[df["gym_id"] == selected_gym].sort_values("timestamp")
    series = series_df[TARGET].astype(float).reset_index(drop=True)
    if len(series) < 80:
        return None

    split_index = max(1, int(len(series) * 0.8))
    train = series.iloc[:split_index]
    test = series.iloc[split_index:]

    # A compact ARIMA is used first to keep the experiment reproducible on a laptop.
    model = ARIMA(train, order=(2, 0, 2))
    fitted = model.fit()
    forecast = fitted.forecast(steps=len(test)).to_numpy()

    return calculate_metrics(
        model_name="arima_2_0_2",
        scope=f"selected_gym:{selected_gym}",
        y_true=test.to_numpy(),
        y_pred=forecast,
        train_rows=len(train),
    )


def write_metrics(metrics: list[ExperimentMetric]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics = sorted(metrics, key=lambda row: (row.mae, row.rmse))
    records = [asdict(row) for row in metrics]

    pd.DataFrame(records).to_csv(REPORTS_DIR / "ml_experiment_metrics.csv", index=False)
    (REPORTS_DIR / "ml_experiment_metrics.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(records, ensure_ascii=False, indent=2))


def main() -> None:
    df = load_dataset()
    train_df, test_df = split_by_time_per_gym(df)
    metrics = run_pooled_models(train_df, test_df)

    arima_metric = run_arima_selected_gym(df)
    if arima_metric is not None:
        metrics.append(arima_metric)

    write_metrics(metrics)


if __name__ == "__main__":
    main()
