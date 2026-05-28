from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExerciseORM
from ..schemas import Exercise
from .serializers import serialize_exercise


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ExerciseKnowledgeHit:
    exercise: Exercise
    score: int
    matched_fields: tuple[str, ...]


def tokenize_query(query: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(query.lower()))


def build_exercise_search_text(exercise: Exercise) -> dict[str, str]:
    # Keep field-level text separate so chat sources can explain why a record was retrieved.
    return {
        "name": exercise.name,
        "slug": exercise.slug.replace("-", " "),
        "muscle_group": exercise.muscle_group,
        "category": exercise.category,
        "difficulty": exercise.difficulty,
        "instructions": " ".join(exercise.instructions),
        "cues": " ".join(exercise.cues),
        "mistakes": " ".join(exercise.mistakes),
    }


def score_exercise_match(exercise: Exercise, query: str, query_tokens: set[str]) -> tuple[int, tuple[str, ...]]:
    fields = build_exercise_search_text(exercise)
    score = 0
    matched_fields: list[str] = []
    normalized_query = query.lower().strip()

    for field_name, raw_text in fields.items():
        text = raw_text.lower()
        field_tokens = set(TOKEN_PATTERN.findall(text))
        overlap = query_tokens & field_tokens
        if not overlap and normalized_query not in text:
            continue
        matched_fields.append(field_name)
        score += len(overlap)
        if normalized_query and normalized_query in text:
            score += 3
        if field_name in {"name", "slug"}:
            score += 4
        elif field_name in {"muscle_group", "category"}:
            score += 2

    return score, tuple(matched_fields)


def retrieve_exercise_knowledge(session: Session, query: str, limit: int = 5) -> list[ExerciseKnowledgeHit]:
    rows = session.scalars(select(ExerciseORM).order_by(ExerciseORM.name.asc())).all()
    exercises = [serialize_exercise(row) for row in rows]
    query_tokens = tokenize_query(query)
    hits: list[ExerciseKnowledgeHit] = []

    for exercise in exercises:
        score, matched_fields = score_exercise_match(exercise, query, query_tokens)
        if score > 0:
            hits.append(ExerciseKnowledgeHit(exercise=exercise, score=score, matched_fields=matched_fields))

    # If the query is broad or not exercise-specific, seed the context with stable starter records.
    if not hits:
        return [
            ExerciseKnowledgeHit(exercise=exercise, score=0, matched_fields=("fallback_seed",))
            for exercise in exercises[:limit]
        ]

    return sorted(hits, key=lambda hit: (-hit.score, hit.exercise.name))[: max(1, min(limit, 10))]


def format_exercise_context(hit: ExerciseKnowledgeHit) -> str:
    exercise = hit.exercise
    # Source fields stay in the prompt so provider answers can remain grounded and auditable.
    return (
        f"- {exercise.name} ({exercise.muscle_group}, {exercise.difficulty}). "
        f"Matched fields: {', '.join(hit.matched_fields)}. "
        f"Instructions: {' '.join(exercise.instructions[:3])} "
        f"Cues: {', '.join(exercise.cues[:4])}. "
        f"Common mistakes: {', '.join(exercise.mistakes[:3])}. "
        f"Source: {exercise.source_name or 'local seed'} {exercise.source_url or ''}. "
        f"License: {exercise.source_license or 'not specified'}. "
        f"Attribution: {exercise.attribution or 'not specified'}."
    )
