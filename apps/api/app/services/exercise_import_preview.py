from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..anatomy import allows_empty_primary_muscles, resolve_anatomy_regions, validate_anatomy_assignment
from ..models import ExerciseMediaORM, ExerciseORM

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PREVIEW_PATH = ROOT / "data" / "external" / "exercise_import_preview.json"


def load_preview(path: Path | None = None) -> dict[str, object]:
    preview_path = path or DEFAULT_PREVIEW_PATH
    return json.loads(preview_path.read_text(encoding="utf-8"))


def summarize_preview_record(record: dict[str, object]) -> dict[str, object]:
    media_gallery = list(record.get("media_gallery") or [])
    has_embed_ready_media = any(bool(item.get("embed_allowed")) for item in media_gallery if isinstance(item, dict))
    requires_anatomy_review = not list(record.get("primary_muscles") or []) and not allows_empty_primary_muscles(
        str(record.get("muscle_group") or ""),
        str(record.get("category") or ""),
    )
    return {
        "slug": str(record.get("slug") or ""),
        "name": str(record.get("name") or ""),
        "category": str(record.get("category") or ""),
        "muscle_group": str(record.get("muscle_group") or ""),
        "difficulty": str(record.get("difficulty") or ""),
        "equipment": str(record.get("equipment") or ""),
        "source_name": str(record.get("source_name") or ""),
        "source_license": str(record.get("source_license") or ""),
        "source_url": str(record.get("source_url") or ""),
        "checked_at": str(record.get("checked_at") or ""),
        "anatomy_note": str(record.get("anatomy_note") or ""),
        "primary_muscles": list(record.get("primary_muscles") or []),
        "secondary_muscles": list(record.get("secondary_muscles") or []),
        "media_gallery_count": len(media_gallery),
        "has_media": bool(media_gallery),
        "has_embed_ready_media": has_embed_ready_media,
        "requires_anatomy_review": requires_anatomy_review,
    }


def summarize_preview(path: Path | None = None, limit: int = 48) -> dict[str, object]:
    preview_path = path or DEFAULT_PREVIEW_PATH
    preview = load_preview(preview_path)
    records = [record for record in preview.get("records", []) if isinstance(record, dict)]
    summaries = [summarize_preview_record(record) for record in records]
    return {
        "path": str(preview_path),
        "status": str(preview.get("status") or "preview"),
        "source_name": str(preview.get("source_name") or ""),
        "source_license": str(preview.get("source_license") or ""),
        "note": str(preview.get("note") or ""),
        "records_total": len(records),
        "records_with_media": sum(1 for item in summaries if bool(item["has_media"])),
        "records_with_embed_ready_media": sum(1 for item in summaries if bool(item["has_embed_ready_media"])),
        "records_needing_anatomy_review": sum(1 for item in summaries if bool(item["requires_anatomy_review"])),
        "records": summaries[: max(1, limit)],
    }


def upsert_exercise_record(session: Session, record: dict[str, object]) -> None:
    slug = str(record["slug"])
    fallback_primary, fallback_secondary = resolve_anatomy_regions(
        slug,
        str(record.get("muscle_group") or "Unknown"),
    )
    allow_empty_primary = allows_empty_primary_muscles(
        str(record.get("muscle_group") or ""),
        str(record.get("category") or ""),
    )
    primary_muscles = list(record.get("primary_muscles") or fallback_primary)
    secondary_muscles = list(record.get("secondary_muscles") or fallback_secondary)
    validate_anatomy_assignment(slug, primary_muscles, secondary_muscles, require_primary=not allow_empty_primary)
    row = session.get(ExerciseORM, slug)
    payload = {
        "name": str(record["name"]),
        "category": str(record.get("category") or "Uncategorized"),
        "muscle_group": str(record.get("muscle_group") or "Unknown"),
        "difficulty": str(record.get("difficulty") or "Unverified"),
        "image_hint": str(record.get("image_hint") or "external-import-preview"),
        "video_url": str(record.get("video_url") or record.get("source_url") or ""),
        "media_type": str(record.get("media_type") or "none"),
        "media_url": str(record.get("media_url") or ""),
        "youtube_video_id": str(record.get("youtube_video_id") or ""),
        "source_name": str(record.get("source_name") or ""),
        "source_url": str(record.get("source_url") or ""),
        "source_license": str(record.get("source_license") or ""),
        "attribution": str(record.get("attribution") or ""),
        "checked_at": str(record.get("checked_at") or ""),
        "primary_muscles_json": json.dumps(primary_muscles),
        "secondary_muscles_json": json.dumps(secondary_muscles),
        "instructions_json": json.dumps(record.get("instructions") or []),
        "cues_json": json.dumps(record.get("cues") or []),
        "mistakes_json": json.dumps(record.get("mistakes") or []),
    }
    if row is None:
        session.add(ExerciseORM(slug=slug, **payload))
        return
    for key, value in payload.items():
        setattr(row, key, value)


def replace_media_gallery(session: Session, slug: str, media_gallery: list[dict[str, object]]) -> int:
    session.execute(delete(ExerciseMediaORM).where(ExerciseMediaORM.exercise_slug == slug))
    created = 0
    for index, item in enumerate(media_gallery):
        session.add(
            ExerciseMediaORM(
                exercise_slug=slug,
                media_type=str(item.get("media_type") or "link"),
                media_url=str(item.get("media_url") or ""),
                thumbnail_url=str(item.get("thumbnail_url") or ""),
                title=str(item.get("title") or ""),
                source_name=str(item.get("source_name") or ""),
                source_url=str(item.get("source_url") or ""),
                source_license=str(item.get("source_license") or ""),
                attribution=str(item.get("attribution") or ""),
                checked_at=str(item.get("checked_at") or ""),
                embed_allowed=1 if bool(item.get("embed_allowed")) else 0,
                download_allowed=1 if bool(item.get("download_allowed")) else 0,
                requires_attribution=1 if bool(item.get("requires_attribution", True)) else 0,
                sort_order=int(item.get("sort_order", index)),
                license_notes=str(item.get("license_notes") or ""),
            )
        )
        created += 1
    return created


def import_preview_records(
    session: Session,
    preview: dict[str, object],
    limit: int = 0,
    only_with_media: bool = False,
    only_embed_ready_media: bool = False,
) -> dict[str, int]:
    records = [record for record in preview.get("records", []) if isinstance(record, dict)]
    filtered: list[dict[str, object]] = []
    skipped_missing_anatomy = 0
    skipped_duplicate_slugs = 0
    deduped_by_slug: dict[str, dict[str, object]] = {}
    for record in records:
        media_gallery = [item for item in list(record.get("media_gallery") or []) if isinstance(item, dict)]
        allow_empty_primary = allows_empty_primary_muscles(
            str(record.get("muscle_group") or ""),
            str(record.get("category") or ""),
        )
        if only_with_media and not media_gallery:
            continue
        if only_embed_ready_media and not any(bool(item.get("embed_allowed")) for item in media_gallery):
            continue
        if not list(record.get("primary_muscles") or []) and not allow_empty_primary:
            skipped_missing_anatomy += 1
            continue
        slug = str(record.get("slug") or "").strip()
        if not slug:
            continue
        if slug in deduped_by_slug:
            skipped_duplicate_slugs += 1
        deduped_by_slug[slug] = record
    filtered = list(deduped_by_slug.values())
    if limit > 0:
        filtered = filtered[:limit]

    imported_media = 0
    for record in filtered:
        upsert_exercise_record(session, record)
        imported_media += replace_media_gallery(session, str(record["slug"]), list(record.get("media_gallery") or []))
    return {
        "imported_records": len(filtered),
        "imported_media_items": imported_media,
        "skipped_missing_anatomy": skipped_missing_anatomy,
        "skipped_duplicate_slugs": skipped_duplicate_slugs,
    }
