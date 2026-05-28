from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.database import SessionLocal, init_database
from apps.api.app.models import (
    AchievementORM,
    ExerciseORM,
    PromotionORM,
    ScheduledWorkoutORM,
    UserAccountORM,
    UserPreferenceORM,
    VisitORM,
    WorkoutSetORM,
    WorkoutTemplateORM,
)


RESET_TABLES = [
    WorkoutSetORM,
    ScheduledWorkoutORM,
    PromotionORM,
    AchievementORM,
    WorkoutTemplateORM,
    VisitORM,
    UserPreferenceORM,
    UserAccountORM,
    ExerciseORM,
]


def table_count(session, model: type) -> int:
    # The dry run is meant for demos, so counts stay simple and human-checkable.
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the local demo state and reseed deterministic GymFlow AI records.")
    parser.add_argument("--dry-run", action="store_true", help="Show table counts without deleting anything.")
    args = parser.parse_args()

    with SessionLocal() as session:
        before = {model.__tablename__: table_count(session, model) for model in RESET_TABLES}
        if args.dry_run:
            print(json.dumps({"status": "dry_run", "before": before}, indent=2))
            return

        # Keep the reset narrow: only mutable demo tables are wiped before reseeding.
        for model in RESET_TABLES:
            session.execute(delete(model))
        session.commit()

    init_database()

    with SessionLocal() as session:
        after = {model.__tablename__: table_count(session, model) for model in RESET_TABLES}

    print(json.dumps({"status": "ok", "before": before, "after": after}, indent=2))


if __name__ == "__main__":
    main()
