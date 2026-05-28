from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.business_hours import is_business_open


FUTURE_FORECAST_PATH = ROOT / "ml" / "reports" / "future_forecast_7d.csv"
SYNTHETIC_PATH = ROOT / "data" / "synthetic" / "occupancy_synthetic_6m.csv"


def assert_business_hours() -> dict[str, bool]:
    cases = {
        "weekday_before_open": ("2026-05-26 06:40:00", False),
        "weekday_open": ("2026-05-26 07:00:00", True),
        "weekday_last_open_hour": ("2026-05-26 21:40:00", True),
        "weekday_closed": ("2026-05-26 22:00:00", False),
        "weekend_before_open": ("2026-05-30 08:40:00", False),
        "weekend_open": ("2026-05-30 09:00:00", True),
        "weekend_last_open_hour": ("2026-05-30 17:40:00", True),
        "weekend_closed": ("2026-05-30 18:00:00", False),
    }
    results: dict[str, bool] = {}
    for name, (timestamp, expected) in cases.items():
        actual = bool(is_business_open(datetime.fromisoformat(timestamp)))
        results[name] = actual == expected
    return results


def count_nonzero_future_closed_rows() -> int:
    if not FUTURE_FORECAST_PATH.exists():
        raise FileNotFoundError(f"Missing future forecast file: {FUTURE_FORECAST_PATH}")

    count = 0
    with FUTURE_FORECAST_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            prediction = float(row["prediction"])
            timestamp = datetime.fromisoformat(row["timestamp"])
            is_open = int(row.get("is_open_estimated", "1"))
            if (not is_business_open(timestamp) or is_open == 0) and prediction != 0:
                count += 1
    return count


def count_nonzero_synthetic_closed_rows() -> int:
    if not SYNTHETIC_PATH.exists():
        raise FileNotFoundError(f"Missing synthetic file: {SYNTHETIC_PATH}")

    count = 0
    with SYNTHETIC_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            timestamp = datetime.fromisoformat(row["timestamp"])
            active_people = int(float(row["active_people"]))
            if not is_business_open(timestamp) and active_people != 0:
                count += 1
    return count


def main() -> None:
    business_hour_checks = assert_business_hours()
    nonzero_future_closed_rows = count_nonzero_future_closed_rows()
    nonzero_synthetic_closed_rows = count_nonzero_synthetic_closed_rows()
    payload = {
        "business_hour_checks": business_hour_checks,
        "nonzero_future_closed_rows": nonzero_future_closed_rows,
        "nonzero_synthetic_closed_rows": nonzero_synthetic_closed_rows,
        "status": "ok"
        if all(business_hour_checks.values())
        and nonzero_future_closed_rows == 0
        and nonzero_synthetic_closed_rows == 0
        else "fail",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
