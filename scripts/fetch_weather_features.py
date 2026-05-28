from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


FUTURE_FORECAST_PATH = ROOT / "ml" / "reports" / "future_forecast_7d.csv"
OBSERVATION_FEATURES_PATH = ROOT / "data" / "processed" / "occupancy_features.csv"
EXTERNAL_DIR = ROOT / "data" / "external"
COORDINATES_PATH = EXTERNAL_DIR / "city_coordinates.json"
WEATHER_FEATURES_PATH = EXTERNAL_DIR / "weather_future_features.csv"
WEATHER_OBSERVATION_FEATURES_PATH = EXTERNAL_DIR / "weather_observation_features.csv"
WEATHER_SUMMARY_PATH = ROOT / "ml" / "reports" / "weather_feature_summary.json"
WEATHER_OBSERVATION_SUMMARY_PATH = ROOT / "ml" / "reports" / "weather_observation_feature_summary.json"

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEZONE = "Europe/Kyiv"
HOURLY_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
]


@dataclass(frozen=True)
class WeatherSummary:
    cities: int
    rows: int
    min_timestamp: str
    max_timestamp: str
    source: str
    mode: str


def read_future_context() -> tuple[list[str], date, date]:
    if not FUTURE_FORECAST_PATH.exists():
        raise FileNotFoundError(f"Missing future forecast file: {FUTURE_FORECAST_PATH}. Run make future first.")

    cities: set[str] = set()
    dates: list[date] = []
    with FUTURE_FORECAST_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            cities.add(row["city"])
            dates.append(date.fromisoformat(row["timestamp"][:10]))
    if not cities or not dates:
        raise ValueError("Future forecast file does not contain city/date rows.")
    return sorted(cities), min(dates), max(dates)


def read_observation_context() -> tuple[list[str], date, date]:
    if not OBSERVATION_FEATURES_PATH.exists():
        raise FileNotFoundError(f"Missing observation features file: {OBSERVATION_FEATURES_PATH}. Run make data first.")

    cities: set[str] = set()
    dates: list[date] = []
    with OBSERVATION_FEATURES_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            cities.add(row["city"])
            dates.append(date.fromisoformat(row["timestamp"][:10]))
    if not cities or not dates:
        raise ValueError("Observation features file does not contain city/date rows.")
    return sorted(cities), min(dates), max(dates)


def load_coordinate_cache() -> dict[str, dict[str, Any]]:
    if COORDINATES_PATH.exists():
        return json.loads(COORDINATES_PATH.read_text(encoding="utf-8"))
    return {}


def save_coordinate_cache(cache: dict[str, dict[str, Any]]) -> None:
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    COORDINATES_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def geocode_city(client: httpx.Client, city: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if city in cache:
        return cache[city]

    response = client.get(
        GEOCODING_URL,
        params={"name": f"{city}, Ukraine", "count": 10, "language": "uk", "format": "json"},
        timeout=20,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ValueError(f"Open-Meteo geocoding returned no results for city: {city}")

    selected = next((item for item in results if item.get("country_code") == "UA"), results[0])
    cache[city] = {
        "name": selected.get("name"),
        "admin1": selected.get("admin1"),
        "country_code": selected.get("country_code"),
        "latitude": selected["latitude"],
        "longitude": selected["longitude"],
        "source": "Open-Meteo Geocoding API",
    }
    save_coordinate_cache(cache)
    time.sleep(0.1)
    return cache[city]


def fetch_city_weather(client: httpx.Client, city: str, coordinates: dict[str, Any], start_date: date, end_date: date) -> list[dict[str, Any]]:
    response = client.get(
        FORECAST_URL,
        params={
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": TIMEZONE,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        timeout=30,
    )
    response.raise_for_status()
    hourly = response.json().get("hourly") or {}
    times = hourly.get("time") or []
    rows: list[dict[str, Any]] = []
    for index, timestamp in enumerate(times):
        row: dict[str, Any] = {
            "timestamp_hour": timestamp.replace("T", " "),
            "city": city,
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
            "weather_source": "Open-Meteo Forecast API",
        }
        for variable in HOURLY_VARIABLES:
            values = hourly.get(variable) or []
            row[variable] = values[index] if index < len(values) else ""
        rows.append(row)
    time.sleep(0.1)
    return rows


def fetch_city_weather_from_url(
    client: httpx.Client,
    url: str,
    source_label: str,
    city: str,
    coordinates: dict[str, Any],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    response = client.get(
        url,
        params={
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": TIMEZONE,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        timeout=30,
    )
    response.raise_for_status()
    hourly = response.json().get("hourly") or {}
    times = hourly.get("time") or []
    rows: list[dict[str, Any]] = []
    for index, timestamp in enumerate(times):
        row: dict[str, Any] = {
            "timestamp_hour": timestamp.replace("T", " "),
            "city": city,
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
            "weather_source": source_label,
        }
        for variable in HOURLY_VARIABLES:
            values = hourly.get(variable) or []
            row[variable] = values[index] if index < len(values) else ""
        rows.append(row)
    time.sleep(0.1)
    return rows


def write_weather_features(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("No weather rows to write.")
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with WEATHER_FEATURES_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def split_observation_ranges(start_date: date, end_date: date) -> list[tuple[str, str, date, date]]:
    today = datetime.now().date()
    ranges: list[tuple[str, str, date, date]] = []
    if start_date <= today:
        ranges.append(("archive", ARCHIVE_URL, start_date, min(end_date, today)))
    if end_date > today:
        ranges.append(("forecast", FORECAST_URL, max(start_date, today), end_date))
    return ranges


def fetch_observation_weather() -> WeatherSummary:
    cities, start_date, end_date = read_observation_context()
    cache = load_coordinate_cache()
    rows: list[dict[str, Any]] = []
    with httpx.Client(headers={"User-Agent": "GymFlowAI/0.1 thesis weather observation adapter"}) as client:
        for city in cities:
            coordinates = geocode_city(client, city, cache)
            for mode, url, range_start, range_end in split_observation_ranges(start_date, end_date):
                source_label = "Open-Meteo Historical Weather API" if mode == "archive" else "Open-Meteo Forecast API"
                rows.extend(fetch_city_weather_from_url(client, url, source_label, city, coordinates, range_start, range_end))

    rows = sorted(rows, key=lambda row: (row["city"], row["timestamp_hour"], row["weather_source"]))
    write_rows(WEATHER_OBSERVATION_FEATURES_PATH, rows)
    summary = WeatherSummary(
        cities=len(cities),
        rows=len(rows),
        min_timestamp=min(row["timestamp_hour"] for row in rows),
        max_timestamp=max(row["timestamp_hour"] for row in rows),
        source="Open-Meteo Historical Weather API, Forecast API, and Geocoding API",
        mode="observation_weather_features",
    )
    WEATHER_OBSERVATION_SUMMARY_PATH.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "future"
    if mode == "observations":
        fetch_observation_weather()
        return
    if mode != "future":
        raise SystemExit(f"Unknown mode: {mode}. Use 'future' or 'observations'.")

    cities, start_date, end_date = read_future_context()
    cache = load_coordinate_cache()
    rows: list[dict[str, Any]] = []
    with httpx.Client(headers={"User-Agent": "GymFlowAI/0.1 thesis weather feature adapter"}) as client:
        for city in cities:
            coordinates = geocode_city(client, city, cache)
            rows.extend(fetch_city_weather(client, city, coordinates, start_date, end_date))

    write_weather_features(rows)
    summary = WeatherSummary(
        cities=len(cities),
        rows=len(rows),
        min_timestamp=min(row["timestamp_hour"] for row in rows),
        max_timestamp=max(row["timestamp_hour"] for row in rows),
        source="Open-Meteo Forecast API and Geocoding API",
        mode="future_forecast_weather_features",
    )
    WEATHER_SUMMARY_PATH.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
