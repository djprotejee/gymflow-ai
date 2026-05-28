from __future__ import annotations

from pathlib import Path

import pandas as pd


WEATHER_FEATURES = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
]


def load_weather_features(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing weather feature file: {path}")
    weather = pd.read_csv(path)
    weather["timestamp_hour"] = pd.to_datetime(weather["timestamp_hour"])
    for column in WEATHER_FEATURES:
        weather[column] = pd.to_numeric(weather[column], errors="coerce")
    return (
        weather.sort_values(["city", "timestamp_hour", "weather_source"])
        .drop_duplicates(subset=["city", "timestamp_hour"], keep="last")
        [["city", "timestamp_hour", *WEATHER_FEATURES]]
    )


def add_timestamp_hour(df: pd.DataFrame) -> pd.DataFrame:
    enriched = df.copy()
    enriched["timestamp_hour"] = pd.to_datetime(enriched["timestamp"]).dt.floor("h")
    return enriched


def join_weather(df: pd.DataFrame, weather_path: Path) -> pd.DataFrame:
    enriched = add_timestamp_hour(df)
    weather = load_weather_features(weather_path)
    joined = enriched.merge(weather, on=["city", "timestamp_hour"], how="left")
    return joined.drop(columns=["timestamp_hour"])
