from __future__ import annotations

import csv
from datetime import datetime

from fastapi import HTTPException

from gymflow_core.business_hours import is_business_open

from ..config import FUTURE_FORECAST_PATH, OBSERVATIONS_PATH


def read_observation_rows() -> list[dict[str, object]]:
    if not OBSERVATIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="Processed observations not found.")

    rows: list[dict[str, object]] = []
    with OBSERVATIONS_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            rows.append(
                {
                    "timestamp": datetime.fromisoformat(row["timestamp"]),
                    "gym_id": row["gym_id"],
                    "city": row["city"],
                    "address": row["address"],
                    "active_people": float(row["active_people"]),
                }
            )
    return rows


def read_future_rows(model: str = "hist_gradient_boosting", days: int = 7) -> list[dict[str, object]]:
    if not FUTURE_FORECAST_PATH.exists():
        raise HTTPException(status_code=404, detail="Future forecast not found. Run scripts/generate_future_forecast.py.")

    # Product horizons are capped to the generated forecast window instead of trusting UI input blindly.
    safe_days = max(1, min(days, 7))
    max_points_per_gym = safe_days * 72
    counters: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    with FUTURE_FORECAST_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row["model"] != model:
                continue
            gym_id = row["gym_id"]
            counters[gym_id] = counters.get(gym_id, 0)
            if counters[gym_id] >= max_points_per_gym:
                continue
            counters[gym_id] += 1
            timestamp = datetime.fromisoformat(row["timestamp"])
            rows.append(
                {
                    "timestamp": timestamp,
                    "gym_id": gym_id,
                    "city": row["city"],
                    "address": row["address"],
                    "prediction": float(row["prediction"]),
                    "model": row["model"],
                    "is_open_estimated": int(row.get("is_open_estimated", 1)),
                    "business_hours": row.get("business_hours", ""),
                    "is_gym_closed_holiday": int(row.get("is_gym_closed_holiday", 0)),
                    "is_major_low_traffic_holiday": int(row.get("is_major_low_traffic_holiday", 0)),
                    "is_major_holiday_window": int(row.get("is_major_holiday_window", 0)),
                }
            )
    return rows


def is_open_forecast_row(row: dict[str, object]) -> bool:
    timestamp = row["timestamp"]
    # Slot recommendations must respect both model flags and the shared network schedule.
    return (
        isinstance(timestamp, datetime)
        and int(row.get("is_open_estimated", 0)) == 1
        and int(row.get("is_gym_closed_holiday", 0)) == 0
        and is_business_open(timestamp)
    )
