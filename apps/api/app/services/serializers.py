from __future__ import annotations

import json
import re

from ..models import ExerciseMediaORM, ExerciseORM, UserAccountORM, WorkoutTemplateORM
from ..schemas import AuthUser, Exercise, ExerciseMedia, WorkoutTemplate


TITLE_CASE_SMALL_WORDS = {"and", "or", "with", "the", "of", "in", "on", "to", "for"}


def display_exercise_name(value: str) -> str:
    if not value or any(char.isupper() for char in value):
        return value
    words = re.split(r"(\s+)", value.strip())
    formatted: list[str] = []
    word_index = 0
    for token in words:
        if token.isspace():
            formatted.append(token)
            continue
        parts = token.split("-")
        next_parts = []
        for part in parts:
            lower = part.lower()
            if word_index > 0 and lower in TITLE_CASE_SMALL_WORDS:
                next_parts.append(lower)
            else:
                next_parts.append(lower[:1].upper() + lower[1:])
            word_index += 1
        formatted.append("-".join(next_parts))
    return "".join(formatted)


def serialize_user(row: UserAccountORM) -> AuthUser:
    return AuthUser(
        user_id=row.user_id,
        email=row.email,
        display_name=row.display_name,
        role=row.role,
    )


def serialize_template(row: WorkoutTemplateORM) -> WorkoutTemplate:
    # Template exercises stay JSON-backed until migrations introduce normalized session tables.
    return WorkoutTemplate(
        id=int(row.id),
        user_id=row.user_id,
        name=display_exercise_name(row.name),
        focus=row.focus,
        estimated_minutes=int(row.estimated_minutes),
        exercises=json.loads(row.exercises_json),
        created_at=row.created_at,
    )


def serialize_exercise_media(row: ExerciseMediaORM) -> ExerciseMedia:
    return ExerciseMedia(
        id=int(row.id),
        exercise_slug=row.exercise_slug,
        media_type=row.media_type,
        media_url=row.media_url,
        thumbnail_url=row.thumbnail_url,
        title=row.title,
        source_name=row.source_name,
        source_url=row.source_url,
        source_license=row.source_license,
        attribution=row.attribution,
        checked_at=row.checked_at,
        embed_allowed=bool(row.embed_allowed),
        download_allowed=bool(row.download_allowed),
        requires_attribution=bool(row.requires_attribution),
        sort_order=int(row.sort_order),
        license_notes=row.license_notes,
    )


def serialize_exercise(row: ExerciseORM, media_rows: list[ExerciseMediaORM] | None = None) -> Exercise:
    # Exercise records carry provenance and media fields because the library must stay source-reviewable.
    return Exercise(
        slug=row.slug,
        name=row.name,
        category=row.category,
        muscle_group=row.muscle_group,
        difficulty=row.difficulty,
        image_hint=row.image_hint,
        video_url=row.video_url,
        source_name=row.source_name,
        source_url=row.source_url,
        source_license=row.source_license,
        attribution=row.attribution,
        checked_at=row.checked_at,
        primary_muscles=json.loads(row.primary_muscles_json),
        secondary_muscles=json.loads(row.secondary_muscles_json),
        media_type=row.media_type,
        media_url=row.media_url,
        youtube_video_id=row.youtube_video_id,
        instructions=json.loads(row.instructions_json),
        cues=json.loads(row.cues_json),
        mistakes=json.loads(row.mistakes_json),
        media_gallery=[serialize_exercise_media(item) for item in (media_rows or [])],
    )
