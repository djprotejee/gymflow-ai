from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from apps.api.app.database import SessionLocal, init_database
from apps.api.app.models import ExerciseMediaORM, ExerciseORM
from apps.api.app.services.exercise_import_preview import (
    DEFAULT_PREVIEW_PATH,
    import_preview_records,
    load_preview,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a reviewed exercise preview JSON into the local exercise library.")
    parser.add_argument("--path", default=str(DEFAULT_PREVIEW_PATH))
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on how many preview records to import.")
    parser.add_argument("--only-with-media", action="store_true", help="Import only records that contain media_gallery items.")
    parser.add_argument(
        "--only-embed-ready-media",
        action="store_true",
        help="Import only records that contain media_gallery items with embed_allowed=true.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    preview_path = Path(args.path)
    if not preview_path.exists():
        raise SystemExit(f"Preview file not found: {preview_path}")

    preview = load_preview(preview_path)
    records = preview.get("records", [])
    if not isinstance(records, list) or not records:
        raise SystemExit("Preview file does not contain any records.")

    normalized_records = [record for record in records if isinstance(record, dict)]
    if args.limit > 0:
        normalized_records = normalized_records[: args.limit]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "path": str(preview_path),
                    "records": len(normalized_records),
                    "source_name": preview.get("source_name", ""),
                    "only_with_media": bool(args.only_with_media),
                    "only_embed_ready_media": bool(args.only_embed_ready_media),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    init_database()
    imported_media = 0
    with SessionLocal() as session:
        result = import_preview_records(
            session,
            {"records": normalized_records},
            only_with_media=bool(args.only_with_media),
            only_embed_ready_media=bool(args.only_embed_ready_media),
        )
        imported_media += int(result["imported_media_items"])
        session.commit()

        total_exercises = session.scalar(select(func.count()).select_from(ExerciseORM)) or 0
        total_media = session.scalar(select(func.count()).select_from(ExerciseMediaORM)) or 0

    print(
        json.dumps(
            {
                "status": "ok",
                "path": str(preview_path),
                "requested_records": len(normalized_records),
                "imported_records": int(result["imported_records"]),
                "imported_media_items": imported_media,
                "skipped_missing_anatomy": int(result["skipped_missing_anatomy"]),
                "skipped_duplicate_slugs": int(result["skipped_duplicate_slugs"]),
                "only_with_media": bool(args.only_with_media),
                "only_embed_ready_media": bool(args.only_embed_ready_media),
                "total_exercises": total_exercises,
                "total_media_items": total_media,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
