from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gymflow_core.business_hours import is_business_open
from holiday_features import (
    days_to_nearest_major_holiday,
    holiday_effect_multiplier,
    is_gym_closed_holiday,
    is_major_holiday_window,
    is_major_low_traffic_holiday,
    is_public_holiday_ua,
)


RAW_DIR = ROOT / "data" / "raw"
RAW_SOURCE_FILE = RAW_DIR / "occupancy_observations_2026.csv"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "ml" / "reports"


@dataclass(frozen=True)
class DataSummary:
    rows: int
    gyms: int
    min_timestamp: str
    max_timestamp: str
    min_active_people: int
    max_active_people: int
    avg_active_people: float


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")


def safe_int(value: str) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def ensure_dirs() -> None:
    for directory in [RAW_DIR, PROCESSED_DIR, REPORTS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def load_rows() -> list[dict[str, str]]:
    staged_rows: list[dict[str, str]] = []
    if not RAW_SOURCE_FILE.exists():
        raise FileNotFoundError(f"Project-local raw source is missing: {RAW_SOURCE_FILE}")

    with RAW_SOURCE_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            city = (row.get("city") or "").strip()
            address = (row.get("address") or "").strip()
            timestamp = parse_timestamp(row.get("timestamp") or "")
            if timestamp.year != 2026:
                raise ValueError(f"Raw timestamp must already be normalized to 2026: {row.get('timestamp')}")
            active_people = safe_int(row.get("active_people") or "0")
            staged_rows.append(
                {
                    "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "gym_key": f"{city}|{address}",
                    "city": city,
                    "address": address,
                    "active_people": str(active_people),
                    "source_file": (row.get("source_file") or RAW_SOURCE_FILE.name).strip(),
                }
            )

    gym_keys = sorted({row["gym_key"] for row in staged_rows})
    gym_ids = {gym_key: f"gym_{index + 1:03d}" for index, gym_key in enumerate(gym_keys)}

    rows: list[dict[str, str]] = []
    for row in staged_rows:
        normalized = dict(row)
        normalized["gym_id"] = gym_ids[row["gym_key"]]
        del normalized["gym_key"]
        rows.append(normalized)
    return rows


def deduplicate(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["timestamp"], row["gym_id"])
        by_key[key] = row
    return sorted(by_key.values(), key=lambda item: (item["gym_id"], item["timestamp"]))


def add_features(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_gym: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_gym.setdefault(row["gym_id"], []).append(row)

    featured: list[dict[str, str]] = []
    for gym_id, gym_rows in by_gym.items():
        gym_rows = sorted(gym_rows, key=lambda item: item["timestamp"])
        counts = [safe_int(row["active_people"]) for row in gym_rows]
        for index, row in enumerate(gym_rows):
            ts = parse_timestamp(row["timestamp"])
            enriched = dict(row)
            enriched["hour"] = str(ts.hour)
            enriched["day_of_week"] = str(ts.weekday())
            enriched["is_weekend"] = "1" if ts.weekday() >= 5 else "0"
            enriched["month"] = str(ts.month)
            enriched["day_of_month"] = str(ts.day)
            enriched["week_of_year"] = str(ts.isocalendar().week)
            enriched["is_open_estimated"] = str(is_business_open(ts))
            enriched["is_public_holiday_ua"] = str(is_public_holiday_ua(ts))
            enriched["is_gym_closed_holiday"] = str(is_gym_closed_holiday(ts))
            enriched["is_major_low_traffic_holiday"] = str(is_major_low_traffic_holiday(ts))
            enriched["is_major_holiday_window"] = str(is_major_holiday_window(ts))
            enriched["days_to_nearest_major_holiday"] = str(days_to_nearest_major_holiday(ts))
            enriched["holiday_effect_multiplier"] = f"{holiday_effect_multiplier(ts):.3f}"
            enriched["lag_1"] = str(counts[index - 1]) if index >= 1 else ""
            enriched["lag_4"] = str(counts[index - 4]) if index >= 4 else ""
            enriched["lag_96"] = str(counts[index - 96]) if index >= 96 else ""
            enriched["rolling_mean_4"] = rolling_mean(counts, index, 4)
            enriched["rolling_mean_16"] = rolling_mean(counts, index, 16)
            enriched["rolling_mean_96"] = rolling_mean(counts, index, 96)
            featured.append(enriched)
    return featured


def rolling_mean(values: list[int], index: int, window: int) -> str:
    if index <= 0:
        return ""
    start = max(0, index - window)
    sample = values[start:index]
    if not sample:
        return ""
    return f"{sum(sample) / len(sample):.3f}"


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]]) -> DataSummary:
    timestamps = [parse_timestamp(row["timestamp"]) for row in rows]
    counts = [safe_int(row["active_people"]) for row in rows]
    gyms = {row["gym_id"] for row in rows}
    return DataSummary(
        rows=len(rows),
        gyms=len(gyms),
        min_timestamp=min(timestamps).strftime("%Y-%m-%d %H:%M:%S"),
        max_timestamp=max(timestamps).strftime("%Y-%m-%d %H:%M:%S"),
        min_active_people=min(counts),
        max_active_people=max(counts),
        avg_active_people=round(sum(counts) / len(counts), 3),
    )


def main() -> None:
    ensure_dirs()
    rows = deduplicate(load_rows())
    featured = add_features(rows)

    observations_path = PROCESSED_DIR / "occupancy_observations.csv"
    features_path = PROCESSED_DIR / "occupancy_features.csv"
    summary_path = REPORTS_DIR / "data_summary.json"

    write_csv(observations_path, rows)
    write_csv(features_path, featured)

    summary = summarize(rows)
    summary_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
