from __future__ import annotations

from datetime import date, datetime


PUBLIC_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "New Year",
    date(2026, 3, 8): "International Women's Day",
    date(2026, 4, 12): "Easter",
    date(2026, 5, 1): "Labor Day",
    date(2026, 5, 8): "Victory over Nazism in World War II Day",
    date(2026, 5, 31): "Trinity",
    date(2026, 6, 28): "Constitution Day",
    date(2026, 7, 15): "Ukrainian Statehood Day",
    date(2026, 8, 24): "Independence Day",
    date(2026, 10, 1): "Defenders Day",
    date(2026, 12, 25): "Christmas",
}

MAJOR_LOW_TRAFFIC_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "New Year",
    date(2026, 4, 12): "Easter",
    date(2026, 5, 31): "Trinity",
    date(2026, 12, 25): "Christmas",
}

GYM_CLOSED_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "New Year",
    date(2026, 4, 12): "Easter",
    date(2026, 12, 25): "Christmas",
}


def coerce_date(value: datetime | date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def is_public_holiday_ua(value: datetime | date | str) -> int:
    return 1 if coerce_date(value) in PUBLIC_HOLIDAYS_2026 else 0


def is_major_low_traffic_holiday(value: datetime | date | str) -> int:
    return 1 if coerce_date(value) in MAJOR_LOW_TRAFFIC_HOLIDAYS_2026 else 0


def is_gym_closed_holiday(value: datetime | date | str) -> int:
    return 1 if coerce_date(value) in GYM_CLOSED_HOLIDAYS_2026 else 0


def days_to_nearest_major_holiday(value: datetime | date | str) -> int:
    current = coerce_date(value)
    distances = [abs((holiday - current).days) for holiday in MAJOR_LOW_TRAFFIC_HOLIDAYS_2026]
    return min(distances) if distances else 365


def is_major_holiday_window(value: datetime | date | str, window_days: int = 2) -> int:
    return 1 if days_to_nearest_major_holiday(value) <= window_days else 0


def holiday_effect_multiplier(value: datetime | date | str) -> float:
    current = coerce_date(value)
    if current in GYM_CLOSED_HOLIDAYS_2026:
        return 0.0
    if current in {date(2026, 5, 31)}:
        return 0.68
    if current in PUBLIC_HOLIDAYS_2026:
        return 0.78
    if is_major_holiday_window(current, window_days=2):
        return 0.86
    return 1.0
