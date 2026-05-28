from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExerciseORM, ScheduledWorkoutORM, UserPreferenceORM, WorkoutSetORM, WorkoutTemplateORM
from .serializers import serialize_exercise, serialize_template


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "next",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "what",
    "with",
}


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    title: str
    source_type: str
    text: str
    source_url: str = ""
    license: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RagHit:
    chunk: RagChunk
    score: float
    matched_terms: tuple[str, ...]


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(text.lower()) if token not in STOPWORDS and len(token) > 1]


def build_exercise_chunks(session: Session) -> list[RagChunk]:
    rows = session.scalars(select(ExerciseORM).order_by(ExerciseORM.name.asc())).all()
    chunks: list[RagChunk] = []
    for row in rows:
        exercise = serialize_exercise(row)
        chunks.append(
            RagChunk(
                chunk_id=f"exercise:{exercise.slug}:technique",
                title=exercise.name,
                source_type="exercise_library",
                text=(
                    f"{exercise.name}. Muscle group: {exercise.muscle_group}. Category: {exercise.category}. "
                    f"Difficulty: {exercise.difficulty}. Primary muscles: {', '.join(exercise.primary_muscles)}. "
                    f"Secondary muscles: {', '.join(exercise.secondary_muscles)}. "
                    f"Instructions: {' '.join(exercise.instructions)} "
                    f"Cues: {', '.join(exercise.cues)}. Common mistakes: {', '.join(exercise.mistakes)}."
                ),
                source_url=exercise.source_url,
                license=exercise.source_license,
                metadata={
                    "slug": exercise.slug,
                    "muscle_group": exercise.muscle_group,
                    "category": exercise.category,
                    "source_name": exercise.source_name,
                    "attribution": exercise.attribution,
                },
            )
        )
    return chunks


def build_user_training_chunks(session: Session, user_id: str, gym_id: str | None) -> list[RagChunk]:
    chunks: list[RagChunk] = []
    workouts = session.scalars(
        select(WorkoutSetORM)
        .where(WorkoutSetORM.user_id == user_id)
        .order_by(WorkoutSetORM.performed_at.desc(), WorkoutSetORM.id.desc())
        .limit(20)
    ).all()
    if workouts:
        chunks.append(
            RagChunk(
                chunk_id=f"user:{user_id}:recent_workouts",
                title="Recent workout history",
                source_type="workout_history",
                text=" ".join(
                    f"{row.performed_at}: {row.exercise} set {row.set_index}, {row.weight_kg} kg x {row.reps}, notes {row.notes}."
                    for row in workouts
                ),
                metadata={"user_id": user_id, "rows": len(workouts)},
            )
        )

    templates = session.scalars(
        select(WorkoutTemplateORM)
        .where(WorkoutTemplateORM.user_id == user_id)
        .order_by(WorkoutTemplateORM.created_at.desc(), WorkoutTemplateORM.id.desc())
        .limit(8)
    ).all()
    for row in templates:
        template = serialize_template(row)
        chunks.append(
            RagChunk(
                chunk_id=f"user:{user_id}:template:{template.id}",
                title=template.name,
                source_type="workout_template",
                text=(
                    f"Template {template.name}. Focus {template.focus}. Estimated minutes {template.estimated_minutes}. "
                    + " ".join(
                        f"{item.exercise}: {item.sets} sets x {item.reps} reps at {item.target_weight_kg} kg, rest {item.rest_seconds} seconds."
                        for item in template.exercises
                    )
                ),
                metadata={"template_id": template.id, "focus": template.focus},
            )
        )

    scheduled = session.scalars(
        select(ScheduledWorkoutORM)
        .where(ScheduledWorkoutORM.user_id == user_id)
        .order_by(ScheduledWorkoutORM.scheduled_at.asc(), ScheduledWorkoutORM.id.asc())
        .limit(12)
    ).all()
    if scheduled:
        chunks.append(
            RagChunk(
                chunk_id=f"user:{user_id}:scheduled_workouts",
                title="Scheduled workouts",
                source_type="scheduled_workouts",
                text=" ".join(
                    f"{row.scheduled_at}: {row.title}, gym {row.gym_id}, expected people {row.expected_people}, status {row.status}, notes {row.notes}."
                    for row in scheduled
                    if gym_id is None or row.gym_id == gym_id
                ),
                metadata={"user_id": user_id, "gym_id": gym_id or ""},
            )
        )

    preference = session.get(UserPreferenceORM, user_id)
    if preference is not None:
        chunks.append(
            RagChunk(
                chunk_id=f"user:{user_id}:preferences",
                title="Training preferences",
                source_type="user_preferences",
                text=(
                    f"Preferred training hours {preference.preferred_min_hour}:00 to {preference.preferred_max_hour}:00. "
                    f"Maximum crowd tolerance {preference.max_crowd_people}. Weekly goal {preference.weekly_goal_sessions}. "
                    f"Preferred weekdays {preference.preferred_weekdays}. Off-peak bonus enabled {preference.off_peak_bonus_enabled}."
                ),
                metadata={"user_id": user_id},
            )
        )

    return chunks


def build_rag_corpus(session: Session, user_id: str, gym_id: str | None) -> list[RagChunk]:
    return [*build_user_training_chunks(session, user_id, gym_id), *build_exercise_chunks(session)]


def source_intent_boost(query_terms: set[str], source_type: str) -> float:
    if source_type == "workout_template" and query_terms & {"template", "saved"}:
        return 3.0
    if source_type == "scheduled_workouts" and query_terms & {"scheduled", "schedule", "week"}:
        return 3.0
    if source_type == "user_preferences" and query_terms & {"prefer", "preferred", "preference", "quiet", "crowd", "time"}:
        return 3.0
    if source_type == "workout_history" and query_terms & {"recent", "progress", "history", "workout"}:
        return 3.0
    return 0.0


def retrieve_rag_context(
    session: Session,
    query: str,
    user_id: str,
    gym_id: str | None = None,
    limit: int = 6,
) -> list[RagHit]:
    corpus = build_rag_corpus(session, user_id=user_id, gym_id=gym_id)
    query_terms = tokenize(query)
    query_term_set = set(query_terms)
    if not corpus or not query_terms:
        return []

    documents = [tokenize(f"{chunk.title} {chunk.text}") for chunk in corpus]
    document_lengths = [max(1, len(tokens)) for tokens in documents]
    average_length = sum(document_lengths) / len(document_lengths)
    document_frequency: Counter[str] = Counter()
    for tokens in documents:
        document_frequency.update(set(tokens))

    query_counter = Counter(query_terms)
    hits: list[RagHit] = []
    for chunk, tokens, length in zip(corpus, documents, document_lengths, strict=True):
        term_counts = Counter(tokens)
        score = 0.0
        matched: list[str] = []
        for term, query_weight in query_counter.items():
            frequency = term_counts.get(term, 0)
            if not frequency:
                continue
            matched.append(term)
            inverse_document_frequency = math.log(1 + (len(corpus) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            denominator = frequency + 1.2 * (1 - 0.75 + 0.75 * length / average_length)
            score += inverse_document_frequency * ((frequency * 2.2) / denominator) * query_weight
        if score > 0:
            title_terms = set(tokenize(chunk.title))
            title_overlap = query_term_set & title_terms
            if title_overlap:
                score += 1.5 * len(title_overlap)
            score += source_intent_boost(query_term_set, chunk.source_type)
            hits.append(RagHit(chunk=chunk, score=round(score, 4), matched_terms=tuple(sorted(set(matched)))))

    return sorted(hits, key=lambda hit: (-hit.score, hit.chunk.source_type, hit.chunk.title))[: max(1, min(limit, 12))]


def format_rag_context(hit: RagHit) -> str:
    source = hit.chunk.source_url or hit.chunk.source_type
    license_text = hit.chunk.license or "not specified"
    return (
        f"- [{hit.chunk.chunk_id}] {hit.chunk.title}. Source type: {hit.chunk.source_type}. "
        f"Matched terms: {', '.join(hit.matched_terms)}. Score: {hit.score}. "
        f"Content: {hit.chunk.text[:900]} Source: {source}. License: {license_text}."
    )
