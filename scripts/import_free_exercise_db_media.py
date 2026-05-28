from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys

from sqlalchemy import delete, select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.app.anatomy import resolve_anatomy_regions, validate_anatomy_assignment
from apps.api.app.database import SessionLocal, init_database
from apps.api.app.models import ExerciseMediaORM, ExerciseORM


DATA_PATH = PROJECT_ROOT / "data" / "external" / "free_exercise_db_yuhonas.json"
RAW_IMAGE_BASE_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises"
SOURCE_NAME = "yuhonas/free-exercise-db"
SOURCE_URL = "https://github.com/yuhonas/free-exercise-db"
SOURCE_LICENSE = "Unlicense public-domain style dataset; verify image provenance before production redistribution."
CHECKED_AT = "2026-05-26"
GENERATED_SOURCE_NAME = "GymFlow AI generated reference"

STOPWORDS = {
    "a",
    "an",
    "and",
    "bar",
    "body",
    "bodyweight",
    "cable",
    "dumbbell",
    "exercise",
    "freeweight",
    "machine",
    "smith",
    "the",
    "with",
}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def titleize(value: str) -> str:
    normalized = re.sub(r"[_\-]+", " ", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    words = re.split(r"([/\s])", normalized)
    keep_upper = {"trx", "jm", "ez", "smr", "tke"}
    return "".join(part.upper() if part.lower() in keep_upper else part.capitalize() for part in words).strip()


def tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 1 and token not in STOPWORDS
    }


def normalize_group(primary_muscles: list[str], category: str) -> str:
    text = " ".join([*primary_muscles, category]).lower()
    rules = [
        (("chest", "pector"), "Chest"),
        (("lats", "middle back", "lower back", "traps"), "Back"),
        (("quadriceps", "adductors", "abductors"), "Legs"),
        (("hamstrings",), "Hamstrings"),
        (("glutes",), "Glutes"),
        (("calves",), "Calves"),
        (("neck",), "Shoulders"),
        (("shoulders", "deltoid"), "Shoulders"),
        (("biceps", "triceps", "forearms"), "Arms"),
        (("abdominals", "obliques"), "Core"),
        (("cardio",), "Conditioning"),
    ]
    for needles, group in rules:
        if any(needle in text for needle in needles):
            return group
    return "Unknown"


def category_label(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "strength":
        return "Hypertrophy"
    if normalized in {"cardio", "plyometrics"}:
        return "Conditioning"
    if normalized == "stretching":
        return "Mobility"
    if normalized == "powerlifting":
        return "Strength"
    return titleize(normalized or "Uncategorized")


def difficulty_label(value: str) -> str:
    normalized = value.strip().lower()
    return {"beginner": "Beginner", "intermediate": "Intermediate", "expert": "Advanced"}.get(normalized, "Unverified")


def clean_instruction(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u200b", " ")).strip()


def media_url(image_path: str) -> str:
    return f"{RAW_IMAGE_BASE_URL}/{image_path}"


def load_records() -> list[dict[str, object]]:
    return [item for item in json.loads(DATA_PATH.read_text(encoding="utf-8")) if isinstance(item, dict)]


def source_record_media(record: dict[str, object], title_prefix: str) -> list[dict[str, object]]:
    images = [str(item) for item in record.get("images") or [] if str(item).strip()]
    return [
        {
            "media_type": "external_image",
            "media_url": media_url(image),
            "thumbnail_url": media_url(image),
            "title": f"{title_prefix} image {index + 1}",
            "source_name": SOURCE_NAME,
            "source_url": f"{SOURCE_URL}/tree/main/exercises/{str(record.get('id') or '').strip()}",
            "source_license": SOURCE_LICENSE,
            "attribution": "Exercise image reference from yuhonas/free-exercise-db.",
            "checked_at": CHECKED_AT,
            "embed_allowed": 1,
            "download_allowed": 0,
            "requires_attribution": 1,
            "sort_order": index,
            "license_notes": "External GitHub raw image reference; do not mirror without a separate production provenance review.",
        }
        for index, image in enumerate(images[:2])
    ]


def has_external_media(media_rows: list[ExerciseMediaORM]) -> bool:
    return any(row.source_name != GENERATED_SOURCE_NAME and row.media_type != "link" and (row.media_url or row.source_url) for row in media_rows)


def add_media_rows(session, slug: str, media_items: list[dict[str, object]], replace_generated_only: bool = False) -> int:
    if replace_generated_only:
        session.execute(
            delete(ExerciseMediaORM)
            .where(ExerciseMediaORM.exercise_slug == slug)
            .where(ExerciseMediaORM.source_name == GENERATED_SOURCE_NAME)
        )
    created = 0
    existing_keys = {
        (row.exercise_slug, row.media_url, row.source_name)
        for row in session.scalars(select(ExerciseMediaORM).where(ExerciseMediaORM.exercise_slug == slug)).all()
    }
    for item in media_items:
        key = (slug, str(item["media_url"]), str(item["source_name"]))
        if key in existing_keys:
            continue
        session.add(
            ExerciseMediaORM(
                exercise_slug=slug,
                media_type=str(item["media_type"]),
                media_url=str(item["media_url"]),
                thumbnail_url=str(item["thumbnail_url"]),
                title=str(item["title"]),
                source_name=str(item["source_name"]),
                source_url=str(item["source_url"]),
                source_license=str(item["source_license"]),
                attribution=str(item["attribution"]),
                checked_at=str(item["checked_at"]),
                embed_allowed=int(item["embed_allowed"]),
                download_allowed=int(item["download_allowed"]),
                requires_attribution=int(item["requires_attribution"]),
                sort_order=int(item["sort_order"]),
                license_notes=str(item["license_notes"]),
            )
        )
        created += 1
    return created


def best_source_match(exercise: ExerciseORM, records: list[dict[str, object]]) -> dict[str, object] | None:
    exercise_tokens = tokens(exercise.name)
    if not exercise_tokens:
        return None
    scored: list[tuple[float, dict[str, object]]] = []
    for record in records:
        record_tokens = tokens(str(record.get("name") or ""))
        if not record_tokens:
            continue
        overlap = len(exercise_tokens & record_tokens)
        if overlap == 0:
            continue
        muscle_bonus = 1 if exercise.muscle_group == normalize_group([str(item) for item in record.get("primaryMuscles") or []], str(record.get("category") or "")) else 0
        score = overlap / max(len(exercise_tokens), len(record_tokens)) + muscle_bonus
        scored.append((score, record))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored[0][0] >= 0.34 else None


def main() -> None:
    if not DATA_PATH.exists():
        raise SystemExit(f"Missing {DATA_PATH}. Download https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json first.")
    init_database()
    source_records = load_records()
    imported_exercises = 0
    attached_existing = 0
    family_refs = 0
    created_media = 0
    with SessionLocal() as session:
        session.execute(delete(ExerciseMediaORM).where(ExerciseMediaORM.source_name == GENERATED_SOURCE_NAME))
        for path in (PROJECT_ROOT / "apps" / "web" / "public" / "exercise-media" / "generated").glob("*.svg"):
            path.unlink()

        existing_by_slug = {row.slug: row for row in session.scalars(select(ExerciseORM)).all()}
        existing_name_keys = {slugify(row.name): row for row in existing_by_slug.values()}
        for record in source_records:
            name = titleize(str(record.get("name") or ""))
            if not name:
                continue
            slug = slugify(name)
            media_items = source_record_media(record, name)
            if not media_items:
                continue
            existing = existing_by_slug.get(slug) or existing_name_keys.get(slugify(name))
            if existing is not None:
                created_media += add_media_rows(session, existing.slug, media_items, replace_generated_only=True)
                existing.name = titleize(existing.name)
                if existing.source_name == SOURCE_NAME or not json.loads(existing.primary_muscles_json or "[]"):
                    muscle_group = normalize_group([str(item) for item in record.get("primaryMuscles") or []], str(record.get("category") or ""))
                    primary_muscles, secondary_muscles = resolve_anatomy_regions(existing.slug, muscle_group)
                    existing.muscle_group = muscle_group
                    existing.primary_muscles_json = json.dumps(primary_muscles)
                    existing.secondary_muscles_json = json.dumps(secondary_muscles)
                attached_existing += 1
                continue
            muscle_group = normalize_group([str(item) for item in record.get("primaryMuscles") or []], str(record.get("category") or ""))
            primary_muscles, secondary_muscles = resolve_anatomy_regions(slug, muscle_group)
            try:
                validate_anatomy_assignment(slug, primary_muscles, secondary_muscles, require_primary=muscle_group != "Conditioning")
            except ValueError:
                primary_muscles, secondary_muscles = resolve_anatomy_regions(slug, muscle_group)
            instructions = [clean_instruction(str(item)) for item in record.get("instructions") or [] if clean_instruction(str(item))]
            row = ExerciseORM(
                slug=slug,
                name=name,
                category=category_label(str(record.get("category") or "")),
                muscle_group=muscle_group,
                difficulty=difficulty_label(str(record.get("level") or "")),
                image_hint=str(record.get("id") or slug),
                video_url=f"{SOURCE_URL}/tree/main/exercises/{str(record.get('id') or '').strip()}",
                media_type="external_image",
                media_url=str(media_items[0]["media_url"]),
                youtube_video_id="",
                source_name=SOURCE_NAME,
                source_url=f"{SOURCE_URL}/tree/main/exercises/{str(record.get('id') or '').strip()}",
                source_license=SOURCE_LICENSE,
                attribution="Exercise record and image reference from yuhonas/free-exercise-db.",
                checked_at=CHECKED_AT,
                primary_muscles_json=json.dumps(primary_muscles),
                secondary_muscles_json=json.dumps(secondary_muscles),
                instructions_json=json.dumps(instructions[:8] or ["Use controlled range of motion and stop the set when technique breaks."]),
                cues_json=json.dumps(["Controlled reps", "Full range", "No unnecessary cheating"]),
                mistakes_json=json.dumps(["Rushing reps", "Cutting range short", "Using load that breaks technique"]),
            )
            session.add(row)
            existing_by_slug[slug] = row
            existing_name_keys[slugify(name)] = row
            created_media += add_media_rows(session, slug, media_items)
            imported_exercises += 1

        session.flush()
        all_media = session.scalars(select(ExerciseMediaORM)).all()
        media_by_slug: dict[str, list[ExerciseMediaORM]] = {}
        for media in all_media:
            media_by_slug.setdefault(media.exercise_slug, []).append(media)
        visible_exercises = [row for row in session.scalars(select(ExerciseORM)).all() if row.source_name.lower() != "wger"]
        for exercise in visible_exercises:
            if has_external_media(media_by_slug.get(exercise.slug, [])):
                exercise.name = titleize(exercise.name)
                continue
            match = best_source_match(exercise, source_records)
            if match is None:
                continue
            match_name = titleize(str(match.get("name") or exercise.name))
            media_items = source_record_media(match, f"{exercise.name} family reference")
            for item in media_items:
                item["title"] = f"{exercise.name} family reference from {match_name}"
                item["license_notes"] = (
                    "External family reference selected by name/muscle overlap; verify exact variation before production use."
                )
            created_media += add_media_rows(session, exercise.slug, media_items, replace_generated_only=True)
            family_refs += 1
        session.commit()

    print(
        json.dumps(
            {
                "status": "ok",
                "source_records": len(source_records),
                "imported_exercises": imported_exercises,
                "attached_existing": attached_existing,
                "family_references": family_refs,
                "created_media_items": created_media,
                "source": SOURCE_URL,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
