from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.business_hours import is_business_open

OBSERVATIONS_PATH = ROOT / "data" / "processed" / "occupancy_observations.csv"
FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
SUMMARY_PATH = ROOT / "ml" / "reports" / "data_summary.json"

REQUIRED_OBSERVATION_COLUMNS = {
    "timestamp",
    "gym_id",
    "city",
    "address",
    "active_people",
    "source_file",
}

REQUIRED_FEATURE_COLUMNS = REQUIRED_OBSERVATION_COLUMNS | {
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
}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def main() -> None:
    observations = load_csv(OBSERVATIONS_PATH)
    features = load_csv(FEATURES_PATH)
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    assert_true(bool(observations), "Prepared observations dataset must not be empty.")
    assert_true(bool(features), "Prepared feature dataset must not be empty.")
    assert_true(len(observations) == len(features), "Observation and feature row counts must match.")
    assert_true(set(observations[0].keys()) >= REQUIRED_OBSERVATION_COLUMNS, "Observation dataset is missing required columns.")
    assert_true(set(features[0].keys()) >= REQUIRED_FEATURE_COLUMNS, "Feature dataset is missing required columns.")

    observation_keys = {(row["timestamp"], row["gym_id"]) for row in observations}
    feature_keys = {(row["timestamp"], row["gym_id"]) for row in features}
    assert_true(len(observation_keys) == len(observations), "Observation dataset contains duplicate timestamp/gym rows.")
    assert_true(len(feature_keys) == len(features), "Feature dataset contains duplicate timestamp/gym rows.")
    assert_true(observation_keys == feature_keys, "Feature dataset keys must match observation dataset keys.")

    timestamps = [parse_timestamp(row["timestamp"]) for row in observations]
    gym_ids = {row["gym_id"] for row in observations}
    counts = [int(float(row["active_people"])) for row in observations]

    assert_true(min(ts.year for ts in timestamps) == 2026 and max(ts.year for ts in timestamps) == 2026, "All raw timestamps must live in year 2026.")
    assert_true(summary["rows"] == len(observations), "data_summary rows must match prepared observations.")
    assert_true(summary["gyms"] == len(gym_ids), "data_summary gyms must match prepared observations.")
    assert_true(summary["min_timestamp"] == min(timestamps).strftime("%Y-%m-%d %H:%M:%S"), "data_summary min_timestamp mismatch.")
    assert_true(summary["max_timestamp"] == max(timestamps).strftime("%Y-%m-%d %H:%M:%S"), "data_summary max_timestamp mismatch.")
    assert_true(summary["min_active_people"] == min(counts), "data_summary min_active_people mismatch.")
    assert_true(summary["max_active_people"] == max(counts), "data_summary max_active_people mismatch.")

    by_gym: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in features:
        by_gym[row["gym_id"]].append(row)

    lag_checks = 0
    open_flag_checks = 0
    for gym_rows in by_gym.values():
        gym_rows.sort(key=lambda row: row["timestamp"])
        previous_counts = [int(float(row["active_people"])) for row in gym_rows]
        for index, row in enumerate(gym_rows):
            ts = parse_timestamp(row["timestamp"])
            expected_open_flag = "1" if is_business_open(ts) else "0"
            assert_true(row["is_open_estimated"] == expected_open_flag, f"is_open_estimated mismatch for {row['gym_id']} {row['timestamp']}")
            open_flag_checks += 1

            if index >= 1:
                assert_true(row["lag_1"] == str(previous_counts[index - 1]), f"lag_1 mismatch for {row['gym_id']} {row['timestamp']}")
                lag_checks += 1
            if index >= 4:
                assert_true(row["lag_4"] == str(previous_counts[index - 4]), f"lag_4 mismatch for {row['gym_id']} {row['timestamp']}")
                lag_checks += 1

            for binary_column in [
                "is_weekend",
                "is_open_estimated",
                "is_public_holiday_ua",
                "is_gym_closed_holiday",
                "is_major_low_traffic_holiday",
                "is_major_holiday_window",
            ]:
                assert_true(row[binary_column] in {"0", "1"}, f"{binary_column} must be binary for {row['gym_id']} {row['timestamp']}")

    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(observations),
                "gyms": len(gym_ids),
                "lag_checks": lag_checks,
                "open_flag_checks": open_flag_checks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
