from __future__ import annotations

import json
from pathlib import Path
import sys

from sqlalchemy import delete


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.app.database import SessionLocal, init_database
from apps.api.app.models import ExerciseMediaORM


GENERATED_MEDIA_DIR = PROJECT_ROOT / "apps" / "web" / "public" / "exercise-media" / "generated"


def main() -> None:
    init_database()
    with SessionLocal() as session:
        result = session.execute(
            delete(ExerciseMediaORM).where(ExerciseMediaORM.source_name == "GymFlow AI generated reference")
        )
        session.commit()
    deleted_files = 0
    if GENERATED_MEDIA_DIR.exists():
        for path in GENERATED_MEDIA_DIR.glob("*.svg"):
            path.unlink()
            deleted_files += 1
    print(
        json.dumps(
            {
                "status": "ok",
                "deleted_media_rows": int(result.rowcount or 0),
                "deleted_generated_files": deleted_files,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
