from __future__ import annotations

import json
from pathlib import Path
import re
import sys

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.app.database import SessionLocal, init_database
from apps.api.app.models import ExerciseMediaORM, ExerciseORM


REPORT_DIR = PROJECT_ROOT / "ml" / "reports"
JSON_PATH = REPORT_DIR / "exercise_media_coverage.json"
MD_PATH = REPORT_DIR / "exercise_media_coverage.md"
TARGET_RICH_COVERAGE = 0.8

RICH_MEDIA_TYPES = {
    "external_image",
    "local_image",
    "image",
    "external_gif",
    "local_gif",
    "gif",
    "external_video",
    "local_video",
    "video",
    "youtube",
}


def is_member_visible(row: ExerciseORM) -> bool:
    # Mirrors the member API filter until this rule moves into a shared service.
    return row.source_name.lower() != "wger"


def exercise_key(row: ExerciseORM) -> str:
    return re.sub(r"[^a-z0-9]+", " ", row.name.lower()).strip()


def exercise_priority(row: ExerciseORM, media_by_slug: dict[str, list[ExerciseMediaORM]]) -> tuple[int, int, int]:
    gallery = media_by_slug.get(row.slug, [])
    has_external_media = any(item.source_name != "GymFlow AI generated reference" and is_rich_media(item) for item in gallery)
    is_project_seed = row.source_name in {"GymFlow AI local seed", "Renaissance Periodization YouTube"}
    has_anatomy = bool(row.primary_muscles_json and row.primary_muscles_json != "[]")
    return (1 if has_external_media else 0, 1 if is_project_seed else 0, 1 if has_anatomy else 0)


def dedupe_member_exercises(
    exercises: list[ExerciseORM],
    media_by_slug: dict[str, list[ExerciseMediaORM]],
) -> list[ExerciseORM]:
    preferred: dict[str, ExerciseORM] = {}
    for exercise in exercises:
        key = exercise_key(exercise)
        current = preferred.get(key)
        if current is None or exercise_priority(exercise, media_by_slug) > exercise_priority(current, media_by_slug):
            preferred[key] = exercise
    return sorted(preferred.values(), key=lambda row: (row.muscle_group, row.name))


def has_youtube_id(value: str) -> bool:
    if len(value.strip()) == 11 and all(char.isalnum() or char in "_-" for char in value.strip()):
        return True
    return any(marker in value for marker in ("youtube.com/watch", "youtu.be/", "youtube-nocookie.com/embed/"))


def is_rich_media(row: ExerciseMediaORM) -> bool:
    media_type = row.media_type.strip().lower()
    media_url = row.media_url.strip()
    source_url = row.source_url.strip()
    if not media_url and not source_url:
        return False
    if has_youtube_id(media_url or source_url):
        return bool(row.embed_allowed)
    if media_type in {"external_video", "local_video", "video"}:
        return bool(row.embed_allowed)
    return media_type in RICH_MEDIA_TYPES


def media_kind(row: ExerciseMediaORM) -> str:
    value = row.media_type.strip().lower()
    if has_youtube_id(row.media_url or row.source_url):
        return "youtube"
    if "gif" in value:
        return "gif"
    if "video" in value:
        return "video"
    if "image" in value or value == "image":
        return "image"
    return value or "unknown"


def build_report() -> dict[str, object]:
    init_database()
    with SessionLocal() as session:
        raw_exercises = [row for row in session.scalars(select(ExerciseORM).order_by(ExerciseORM.name.asc())).all() if is_member_visible(row)]
        media_rows = session.scalars(
            select(ExerciseMediaORM).order_by(ExerciseMediaORM.exercise_slug.asc(), ExerciseMediaORM.sort_order.asc(), ExerciseMediaORM.id.asc())
        ).all()

    media_by_slug: dict[str, list[ExerciseMediaORM]] = {}
    for row in media_rows:
        media_by_slug.setdefault(row.exercise_slug, []).append(row)
    exercises = dedupe_member_exercises(raw_exercises, media_by_slug)

    rows = []
    rich_count = 0
    external_demo_count = 0
    generated_reference_count = 0
    fallback_count = 0
    kind_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for exercise in exercises:
        gallery = media_by_slug.get(exercise.slug, [])
        rich_gallery = [item for item in gallery if is_rich_media(item)]
        has_primary_youtube = bool(exercise.youtube_video_id.strip())
        has_rich = bool(rich_gallery or has_primary_youtube)
        has_fallback = bool(exercise.video_url.strip())
        if has_rich:
            rich_count += 1
        if any(item.source_name != "GymFlow AI generated reference" for item in rich_gallery) or has_primary_youtube:
            external_demo_count += 1
        if any(item.source_name == "GymFlow AI generated reference" for item in rich_gallery):
            generated_reference_count += 1
        if has_fallback:
            fallback_count += 1
        for item in rich_gallery:
            kind_counts[media_kind(item)] = kind_counts.get(media_kind(item), 0) + 1
            source_name = item.source_name.strip() or "unknown"
            source_counts[source_name] = source_counts.get(source_name, 0) + 1
        rows.append(
            {
                "slug": exercise.slug,
                "name": exercise.name,
                "muscle_group": exercise.muscle_group,
                "category": exercise.category,
                "difficulty": exercise.difficulty,
                "source_name": exercise.source_name,
                "rich_media": has_rich,
                "fallback_link": has_fallback,
                "rich_media_items": len(rich_gallery) + (1 if has_primary_youtube else 0),
                "media_kinds": sorted({media_kind(item) for item in rich_gallery} | ({"youtube"} if has_primary_youtube else set())),
            }
        )

    total = max(1, len(exercises))
    rich_coverage = rich_count / total
    fallback_coverage = fallback_count / total
    missing = [row for row in rows if not row["rich_media"]]
    summary = {
        "status": "ok" if (external_demo_count / total) >= TARGET_RICH_COVERAGE else "below_target",
        "target_rich_media_coverage": TARGET_RICH_COVERAGE,
        "member_visible_exercises": len(exercises),
        "rich_media_exercises": rich_count,
        "rich_media_coverage": round(rich_coverage, 4),
        "external_demo_media_exercises": external_demo_count,
        "external_demo_media_coverage": round(external_demo_count / total, 4),
        "generated_reference_exercises": generated_reference_count,
        "generated_reference_coverage": round(generated_reference_count / total, 4),
        "fallback_link_exercises": fallback_count,
        "fallback_link_coverage": round(fallback_coverage, 4),
        "missing_rich_media": len(missing),
        "media_kind_counts": dict(sorted(kind_counts.items())),
        "source_counts": dict(sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))),
        "note": "The target is measured against external image/GIF/video/YouTube media. Generated reference cards are intentionally removed; YouTube search links count only as fallback.",
    }
    return {"summary": summary, "missing": missing[:120], "rows": rows}


def write_report(report: dict[str, object]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary = report["summary"]
    missing = report["missing"]
    lines = [
        "# Exercise Media Coverage",
        "",
        f"- Status: {summary['status']}",
        f"- Target rich-media coverage: {summary['target_rich_media_coverage']:.0%}",
        f"- Member-visible exercises: {summary['member_visible_exercises']}",
        f"- Rich-media exercises: {summary['rich_media_exercises']}",
        f"- Rich-media coverage: {summary['rich_media_coverage']:.2%}",
        f"- Third-party demo media coverage: {summary['external_demo_media_coverage']:.2%}",
        f"- Generated reference exercises: {summary['generated_reference_exercises']}",
        f"- Fallback-link coverage: {summary['fallback_link_coverage']:.2%}",
        "",
        f"Note: {summary['note']}",
        "",
        "## Missing Rich Media Sample",
        "",
        "| Exercise | Group | Category | Source |",
        "|---|---|---|---|",
    ]
    for row in missing[:40]:
        lines.append(f"| {row['name']} | {row['muscle_group']} | {row['category']} | {row['source_name']} |")
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_report(report)
    print(json.dumps(report["summary"], indent=2))
    if report["summary"]["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
