from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import UserPreferenceORM
from ..schemas import UserPreference


def parse_weekdays(value: str) -> list[int]:
    # Preferences are stored compactly in SQLite/PostgreSQL but exposed as typed lists to the UI.
    items: list[int] = []
    for part in value.split(","):
        try:
            items.append(int(part.strip()))
        except ValueError:
            continue
    return items or [0, 2, 4]


def serialize_preference(row: UserPreferenceORM) -> UserPreference:
    return UserPreference(
        user_id=row.user_id,
        preferred_min_hour=int(row.preferred_min_hour),
        preferred_max_hour=int(row.preferred_max_hour),
        max_crowd_people=float(row.max_crowd_people),
        weekly_goal_sessions=int(row.weekly_goal_sessions),
        preferred_weekdays=parse_weekdays(row.preferred_weekdays),
        off_peak_bonus_enabled=bool(row.off_peak_bonus_enabled),
        preferred_gym_id=row.preferred_gym_id or "gym_008",
        preferred_rep_mode=row.preferred_rep_mode or "auto",
        preferred_rep_min=int(row.preferred_rep_min or 8),
        preferred_rep_max=int(row.preferred_rep_max or 10),
    )


def get_or_create_preferences(user_id: str, session: Session) -> UserPreferenceORM:
    row = session.scalar(select(UserPreferenceORM).where(UserPreferenceORM.user_id == user_id))
    if row is not None:
        return row
    # New demo users should immediately receive sensible forecast-aware defaults.
    row = UserPreferenceORM(
        user_id=user_id,
        preferred_min_hour=9,
        preferred_max_hour=17,
        max_crowd_people=45.0,
        weekly_goal_sessions=3,
        preferred_weekdays="0,2,4",
        off_peak_bonus_enabled=1,
        preferred_gym_id="gym_008",
        preferred_rep_mode="auto",
        preferred_rep_min=8,
        preferred_rep_max=10,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
