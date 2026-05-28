from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.database import SessionLocal, build_demo_workout_history_records
from apps.api.app.models import WorkoutSetORM


def main() -> None:
    records = build_demo_workout_history_records()
    inserted = 0
    with SessionLocal() as session:
        existing_keys = {
            (row.exercise, row.performed_at, row.set_index)
            for row in session.scalars(select(WorkoutSetORM).where(WorkoutSetORM.user_id == "demo")).all()
        }
        for record in records:
            key = (str(record["exercise"]), str(record["performed_at"]), int(record["set_index"]))
            if key in existing_keys:
                continue
            session.add(WorkoutSetORM(**record))
            existing_keys.add(key)
            inserted += 1
        session.commit()
        total = int(
            session.scalar(select(func.count()).select_from(WorkoutSetORM).where(WorkoutSetORM.user_id == "demo"))
            or 0
        )
    print(json.dumps({"status": "ok", "inserted": inserted, "demo_workout_sets": total}, indent=2))


if __name__ == "__main__":
    main()
