from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.app.anatomy import resolve_anatomy_regions, validate_anatomy_assignment
from apps.api.app.database import SessionLocal, init_database
from apps.api.app.models import ExerciseORM


USER_CUSTOM_SOURCE = "GymFlow AI user custom exercise"


def resolve_muscle_group_pattern(slug: str, current_group: str) -> str:
    if "wrist-curl" in slug or slug.startswith("wrist-"):
        return "Arms"
    if "leg-curl" in slug or "hamstring-curl" in slug:
        return "Hamstrings"
    if "lower-back-curl" in slug:
        return "Back"
    if "glute-kickback" in slug or "cable-kickback" in slug or "cable-hip-extension" in slug:
        return "Glutes"
    if "curl" in slug and "leg-curl" not in slug and "wrist-curl" not in slug:
        return "Arms"
    if any(token in slug for token in ("tricep", "triceps", "pushdown", "skull-crusher")) or slug == "dumbbell-kickback":
        return "Arms"
    if "shrug" in slug:
        return "Back"
    if "kettlebell-swing" in slug or "sled-push" in slug:
        return "Legs"
    if "calf-raise" in slug:
        return "Calves"
    if "hip-abduction" in slug or "abductor" in slug:
        return "Glutes"
    if "hip-adduction" in slug or "adductor" in slug or "leg-extension" in slug:
        return "Legs"
    return current_group


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute exercise primary/secondary anatomy from current resolver rules.")
    parser.add_argument("--include-custom", action="store_true", help="Also overwrite user-created exercise anatomy.")
    args = parser.parse_args()

    updated = 0
    skipped_custom = 0
    examples: list[dict[str, object]] = []
    init_database()
    with SessionLocal() as session:
        rows = session.scalars(select(ExerciseORM).order_by(ExerciseORM.name)).all()
        for row in rows:
            if row.source_name == USER_CUSTOM_SOURCE and not args.include_custom:
                skipped_custom += 1
                continue
            previous_group = row.muscle_group
            next_group = resolve_muscle_group_pattern(row.slug, previous_group)
            previous_primary = json.loads(row.primary_muscles_json or "[]")
            previous_secondary = json.loads(row.secondary_muscles_json or "[]")
            primary, secondary = resolve_anatomy_regions(row.slug, next_group)
            validate_anatomy_assignment(row.slug, primary, secondary, require_primary=bool(primary or row.muscle_group != "Conditioning"))
            if primary == previous_primary and secondary == previous_secondary and next_group == previous_group:
                continue
            row.muscle_group = next_group
            row.primary_muscles_json = json.dumps(primary)
            row.secondary_muscles_json = json.dumps(secondary)
            updated += 1
            if len(examples) < 12:
                examples.append(
                    {
                        "slug": row.slug,
                        "name": row.name,
                        "previous_group": previous_group,
                        "next_group": next_group,
                        "previous_primary": previous_primary,
                        "previous_secondary": previous_secondary,
                        "next_primary": primary,
                        "next_secondary": secondary,
                    }
                )
        session.commit()

    print(
        json.dumps(
            {
                "status": "ok",
                "updated": updated,
                "skipped_custom": skipped_custom,
                "examples": examples,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
