from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
REPORTS_DIR = ROOT / "ml" / "reports"


@dataclass(frozen=True)
class MetricRow:
    model: str
    rows: int
    mae: float
    rmse: float
    wape: float


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def safe_float(value: str) -> float | None:
    try:
        if value == "":
            return None
        return float(value)
    except ValueError:
        return None


def safe_int(value: str) -> int:
    try:
        return int(float(value))
    except ValueError:
        return 0


def load_features() -> list[dict[str, str]]:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"Missing features file: {FEATURES_PATH}. Run scripts/prepare_data.py first."
        )
    with FEATURES_PATH.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def train_test_split(rows: list[dict[str, str]], train_ratio: float = 0.8) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    ordered = sorted(rows, key=lambda row: row["timestamp"])
    split = max(1, int(len(ordered) * train_ratio))
    return ordered[:split], ordered[split:]


def previous_observation_predictions(test_rows: list[dict[str, str]]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in test_rows:
        prediction = safe_float(row.get("lag_1", ""))
        if prediction is None:
            continue
        pairs.append((safe_int(row["active_people"]), prediction))
    return pairs


def seasonal_lag_predictions(test_rows: list[dict[str, str]]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in test_rows:
        prediction = safe_float(row.get("lag_96", ""))
        if prediction is None:
            continue
        pairs.append((safe_int(row["active_people"]), prediction))
    return pairs


def rolling_mean_predictions(test_rows: list[dict[str, str]]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in test_rows:
        prediction = safe_float(row.get("rolling_mean_16", ""))
        if prediction is None:
            continue
        pairs.append((safe_int(row["active_people"]), prediction))
    return pairs


def calendar_profile_predictions(train_rows: list[dict[str, str]], test_rows: list[dict[str, str]]) -> list[tuple[float, float]]:
    buckets: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    gym_defaults: dict[str, list[int]] = defaultdict(list)
    global_values: list[int] = []

    for row in train_rows:
        count = safe_int(row["active_people"])
        key = (row["gym_id"], row["day_of_week"], row["hour"])
        buckets[key].append(count)
        gym_defaults[row["gym_id"]].append(count)
        global_values.append(count)

    global_mean = sum(global_values) / len(global_values)
    pairs: list[tuple[float, float]] = []

    for row in test_rows:
        actual = safe_int(row["active_people"])
        key = (row["gym_id"], row["day_of_week"], row["hour"])
        if buckets.get(key):
            prediction = sum(buckets[key]) / len(buckets[key])
        elif gym_defaults.get(row["gym_id"]):
            prediction = sum(gym_defaults[row["gym_id"]]) / len(gym_defaults[row["gym_id"]])
        else:
            prediction = global_mean
        pairs.append((actual, prediction))
    return pairs


def metrics(model: str, pairs: list[tuple[float, float]]) -> MetricRow:
    if not pairs:
        return MetricRow(model=model, rows=0, mae=0.0, rmse=0.0, wape=0.0)
    errors = [actual - predicted for actual, predicted in pairs]
    abs_errors = [abs(error) for error in errors]
    squared_errors = [error * error for error in errors]
    actual_total = sum(abs(actual) for actual, _ in pairs)
    return MetricRow(
        model=model,
        rows=len(pairs),
        mae=round(sum(abs_errors) / len(abs_errors), 4),
        rmse=round(math.sqrt(sum(squared_errors) / len(squared_errors)), 4),
        wape=round(sum(abs_errors) / actual_total, 4) if actual_total else 0.0,
    )


def write_metrics(rows: list[MetricRow]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS_DIR / "baseline_metrics.csv"
    json_path = REPORTS_DIR / "baseline_metrics.json"

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["model", "rows", "mae", "rmse", "wape"])
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    json_path.write_text(
        json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    rows = load_features()
    by_gym: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_gym[row["gym_id"]].append(row)

    all_train: list[dict[str, str]] = []
    all_test: list[dict[str, str]] = []
    for gym_rows in by_gym.values():
        train_rows, test_rows = train_test_split(gym_rows)
        all_train.extend(train_rows)
        all_test.extend(test_rows)

    metric_rows = [
        metrics("previous_observation", previous_observation_predictions(all_test)),
        metrics("seasonal_lag_1d", seasonal_lag_predictions(all_test)),
        metrics("rolling_mean_16", rolling_mean_predictions(all_test)),
        metrics("calendar_profile_gym_weekday_hour", calendar_profile_predictions(all_train, all_test)),
    ]
    metric_rows = sorted(metric_rows, key=lambda row: row.mae)
    write_metrics(metric_rows)
    print(json.dumps([asdict(row) for row in metric_rows], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

