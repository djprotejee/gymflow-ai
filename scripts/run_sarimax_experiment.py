from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.statespace.sarimax import SARIMAX


ROOT = Path(__file__).resolve().parents[1]
FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
REPORTS_DIR = ROOT / "ml" / "reports"

TARGET = "active_people"
EXOG_FEATURES = [
    "hour",
    "day_of_week",
    "is_weekend",
    "is_open_estimated",
    "is_public_holiday_ua",
    "is_major_low_traffic_holiday",
    "is_major_holiday_window",
    "holiday_effect_multiplier",
    "lag_1",
    "lag_4",
    "rolling_mean_4",
    "rolling_mean_16",
]


@dataclass(frozen=True)
class SarimaxMetric:
    model: str
    scope: str
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
    for column in [TARGET, *EXOG_FEATURES]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["gym_id", "timestamp"]).reset_index(drop=True)


def prepare_exog(train_df: pd.DataFrame, test_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    train_exog = scaler.fit_transform(imputer.fit_transform(train_df[EXOG_FEATURES]))
    test_exog = scaler.transform(imputer.transform(test_df[EXOG_FEATURES]))
    return train_exog, test_exog


def calculate_metric(scope: str, y_true: np.ndarray, y_pred: np.ndarray, train_rows: int) -> SarimaxMetric:
    y_pred = np.clip(y_pred, 0, None)
    absolute_errors = np.abs(y_true - y_pred)
    actual_total = np.sum(np.abs(y_true))
    return SarimaxMetric(
        model="sarimax_1_0_1_exogenous",
        scope=scope,
        train_rows=train_rows,
        test_rows=len(y_true),
        mae=round(float(mean_absolute_error(y_true, y_pred)), 4),
        rmse=round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        wape=round(float(np.sum(absolute_errors) / actual_total), 4) if actual_total else 0.0,
    )


def run_selected_gym(df: pd.DataFrame) -> tuple[SarimaxMetric, pd.DataFrame]:
    selected_gym = df.groupby("gym_id").size().sort_values(ascending=False).index[0]
    gym_df = df[df["gym_id"] == selected_gym].sort_values("timestamp").reset_index(drop=True)
    split_index = max(1, int(len(gym_df) * 0.8))
    train_df = gym_df.iloc[:split_index].copy()
    test_df = gym_df.iloc[split_index:].copy()
    train_exog, test_exog = prepare_exog(train_df, test_df)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SARIMAX(
            train_df[TARGET].astype(float).to_numpy(),
            exog=train_exog,
            order=(1, 0, 1),
            seasonal_order=(0, 0, 0, 0),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted = model.fit(disp=False, maxiter=80)
        forecast = fitted.forecast(steps=len(test_df), exog=test_exog)

    predictions = test_df[["timestamp", "gym_id", "city", "address", TARGET]].copy()
    predictions["pred_sarimax_1_0_1_exogenous"] = np.clip(np.asarray(forecast), 0, None)
    metric = calculate_metric(
        scope=f"selected_gym:{selected_gym}",
        y_true=test_df[TARGET].astype(float).to_numpy(),
        y_pred=predictions["pred_sarimax_1_0_1_exogenous"].to_numpy(),
        train_rows=len(train_df),
    )
    return metric, predictions


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load_dataset()
    metric, predictions = run_selected_gym(df)
    records = [asdict(metric)]
    pd.DataFrame(records).to_csv(REPORTS_DIR / "sarimax_metrics.csv", index=False)
    (REPORTS_DIR / "sarimax_metrics.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    predictions.to_csv(REPORTS_DIR / "sarimax_predictions_sample.csv", index=False)
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
