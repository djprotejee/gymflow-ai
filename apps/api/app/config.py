from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"
DATA_SUMMARY_PATH = ROOT / "ml" / "reports" / "data_summary.json"
OBSERVATIONS_PATH = ROOT / "data" / "processed" / "occupancy_observations.csv"
METRICS_PATH = ROOT / "ml" / "reports" / "baseline_metrics.csv"
ML_METRICS_PATH = ROOT / "ml" / "reports" / "ml_experiment_metrics.csv"
ML_PREDICTIONS_PATH = ROOT / "ml" / "reports" / "ml_predictions_sample.csv"
FUTURE_FORECAST_PATH = ROOT / "ml" / "reports" / "future_forecast_7d.csv"
LOCAL_DB_PATH = ROOT / "data" / "gymflow.sqlite3"


def load_project_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = raw.strip().strip('"').strip("'")


load_project_env()


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{LOCAL_DB_PATH.as_posix()}"
