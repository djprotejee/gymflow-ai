from __future__ import annotations

from datetime import date, datetime

WEEKDAY_OPEN_HOUR = 7
WEEKDAY_CLOSE_HOUR = 22
WEEKEND_OPEN_HOUR = 9
WEEKEND_CLOSE_HOUR = 18


def is_weekend(value: datetime | date) -> bool:
    return value.weekday() >= 5


def opening_hours(value: datetime | date) -> tuple[int, int]:
    if is_weekend(value):
        return WEEKEND_OPEN_HOUR, WEEKEND_CLOSE_HOUR
    return WEEKDAY_OPEN_HOUR, WEEKDAY_CLOSE_HOUR


def is_business_open(value: datetime) -> int:
    open_hour, close_hour = opening_hours(value)
    return 1 if open_hour <= value.hour < close_hour else 0


def business_hours_label(value: datetime | date) -> str:
    open_hour, close_hour = opening_hours(value)
    return f"{open_hour:02d}:00-{close_hour:02d}:00"
