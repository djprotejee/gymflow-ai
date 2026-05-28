from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.app.database import SessionLocal, init_database
from apps.api.app.models import ExerciseORM, UserPreferenceORM, WorkoutSetORM, WorkoutTemplateORM
from apps.api.app.services.progression import SetObservation, predict_next_set
from apps.api.app.services.serializers import serialize_exercise


OUTPUT_DIR = PROJECT_ROOT / "ml" / "fine_tuning"
TRAIN_PATH = OUTPUT_DIR / "coach_behavior_train.jsonl"
EVAL_PATH = OUTPUT_DIR / "coach_behavior_eval.jsonl"
LEGACY_TRAIN_PATH = OUTPUT_DIR / "exercise_recommendation_train.jsonl"
LEGACY_EVAL_PATH = OUTPUT_DIR / "exercise_recommendation_eval.jsonl"
VERTEX_TRAIN_PATH = OUTPUT_DIR / "vertex_gemini_coach_behavior_train.jsonl"
VERTEX_EVAL_PATH = OUTPUT_DIR / "vertex_gemini_coach_behavior_eval.jsonl"
CARD_PATH = OUTPUT_DIR / "DATASET_CARD.md"
REPORT_PATH = PROJECT_ROOT / "ml" / "reports" / "fine_tuning_readiness.json"
SYSTEM = (
    "You are GymFlow AI Coach. Use approved GymFlow context, cite retrieved sources when present, "
    "prefer executable tool actions for supported tasks, keep progression advice conservative, "
    "and never diagnose injuries or invent citations."
)


def assistant_text_for_exercise(exercise: ExerciseORM) -> str:
    item = serialize_exercise(exercise)
    primary = ", ".join(item.primary_muscles) or item.muscle_group
    secondary = ", ".join(item.secondary_muscles) or "none"
    instruction = item.instructions[0] if item.instructions else "Use controlled technique and stop when form breaks."
    cue = item.cues[0] if item.cues else "Keep the movement controlled."
    return (
        f"Recommended exercise: {item.name}. Primary target: {primary}. "
        f"Secondary target: {secondary}. Difficulty: {item.difficulty}. "
        f"Coaching cue: {cue}. Technique source: {item.source_name or 'GymFlow local exercise record'}. "
        f"First step: {instruction}"
    )


def chat_example(task: str, user: str, assistant: str, metadata: dict[str, Any] | None = None) -> dict[str, object]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "metadata": {"task": task, **(metadata or {})},
    }


def conversation_example(exercise: ExerciseORM) -> dict[str, object]:
    item = serialize_exercise(exercise)
    return chat_example(
        "exercise_recommendation",
        f"Suggest one {item.category.lower()} exercise for {item.muscle_group.lower()} at {item.difficulty.lower()} level.",
        assistant_text_for_exercise(exercise),
        {
            "exercise_slug": item.slug,
            "source_name": item.source_name,
            "source_license": item.source_license,
        },
    )


def technique_citation_example(exercise: ExerciseORM) -> dict[str, object]:
    item = serialize_exercise(exercise)
    cue = item.cues[0] if item.cues else "Use controlled tempo and stop when form breaks."
    return chat_example(
        "rag_cited_technique",
        f"Explain {item.name} technique using the retrieved source card.",
        (
            f"For {item.name}, start from the approved exercise-library source card rather than guessing. "
            f"Main target: {item.muscle_group}. Cue: {cue}. "
            f"Source: {item.source_name or 'GymFlow exercise library'}."
        ),
        {"exercise_slug": item.slug, "source_name": item.source_name},
    )


def progression_examples(recent_sets: list[WorkoutSetORM], preferences: UserPreferenceORM | None) -> list[dict[str, object]]:
    grouped: dict[str, list[WorkoutSetORM]] = defaultdict(list)
    for row in recent_sets:
        grouped[row.exercise].append(row)
    examples: list[dict[str, object]] = []
    for exercise, rows in sorted(grouped.items())[:12]:
        ordered = sorted(rows, key=lambda item: (item.performed_at, item.set_index))
        if len(ordered) < 2:
            continue
        history = [
            SetObservation(
                exercise=row.exercise,
                weight_kg=row.weight_kg,
                reps=row.reps,
                set_index=row.set_index,
                performed_at=row.performed_at,
            )
            for row in ordered[:-1]
        ]
        prediction = predict_next_set(
            exercise=exercise,
            history=history,
            set_index=ordered[-1].set_index,
            preferred_rep_mode=getattr(preferences, "preferred_rep_mode", "auto") if preferences else "auto",
            preferred_rep_min=getattr(preferences, "preferred_rep_min", 8) if preferences else 8,
            preferred_rep_max=getattr(preferences, "preferred_rep_max", 10) if preferences else 10,
        )
        aim = (
            f"{prediction.target_weight_kg:g} kg x "
            f"{prediction.target_reps_min}-{prediction.target_reps_max} reps"
        )
        examples.append(
            chat_example(
                "progression_explanation",
                f"Explain my next target for {exercise}.",
                (
                    f"Aim for {aim}. This uses your logged set history, recent estimated strength trend, "
                    f"and the selected rep policy. Confidence: {prediction.confidence:.2f}. "
                    f"Reason: {prediction.reason}"
                ),
                {"exercise": exercise, "model_version": prediction.model_version, "strategy": prediction.strategy},
            )
        )
    return examples


def tool_action_examples(templates: list[WorkoutTemplateORM], preferences: UserPreferenceORM | None) -> list[dict[str, object]]:
    preferred_window = f"{preferences.preferred_min_hour}:00-{preferences.preferred_max_hour}:00" if preferences else "10:00-18:00"
    template_name = templates[0].name if templates else "Upper Strength"
    examples = [
        chat_example(
            "tool_action_schedule_week",
            "Plan my next training week around quieter gym times.",
            (
                "I should use the forecast-aware schedule tool rather than only giving generic advice. "
                f"Proposed action: schedule_week with preferred window {preferred_window}, 4 sessions, "
                "and low-occupancy slots first. I will show the planned sessions for confirmation before saving."
            ),
            {"tool_action": "schedule_week"},
        ),
        chat_example(
            "tool_action_log_target_set",
            "Log my target bench press set from the model.",
            (
                "I should call the target-set logging tool with the current next-session prediction, "
                "then refresh progress, achievements, and next-session target. I should not invent a weight "
                "if the progression endpoint returns no target."
            ),
            {"tool_action": "log_target_set"},
        ),
        chat_example(
            "tool_action_template_edit",
            f"Add one back exercise to my {template_name} template.",
            (
                "I should use the add-exercise-to-template tool only after identifying the template and exercise. "
                "If the request is ambiguous, ask for the target exercise instead of silently editing the wrong template."
            ),
            {"tool_action": "add_exercise_to_template"},
        ),
    ]
    for action, prompt in [
        ("update_preferences", "Move my preferred training window to mornings."),
        ("reschedule_workout", "Move tomorrow's workout to a quieter time."),
        ("create_template", "Create a simple upper body template."),
        ("manager_promotion_draft", "Draft an off-peak promotion for the quietest location."),
    ]:
        examples.append(
            chat_example(
                f"tool_action_{action}",
                prompt,
                (
                    f"I should prepare the `{action}` tool action only if the required fields are known. "
                    "If the request changes persistent data or affects a manager workflow, show a confirmation card before execution."
                ),
                {"tool_action": action},
            )
        )
    return examples


def forecast_examples(preferences: UserPreferenceORM | None) -> list[dict[str, object]]:
    window = f"{preferences.preferred_min_hour}:00-{preferences.preferred_max_hour}:00" if preferences else "10:00-18:00"
    crowd = int(preferences.max_crowd_people) if preferences else 45
    prompts = [
        "Find a quieter slot tomorrow.",
        "Should I train today or wait for a less crowded time?",
        "Plan one session this week around my crowd tolerance.",
        "Explain why the recommended slot is better than peak evening time.",
        "Find a slot for bench press when the gym is not packed.",
    ]
    return [
        chat_example(
            "forecast_aware_recommendation",
            prompt,
            (
                f"I should use the occupancy forecast and your preferred window {window}. "
                f"Prioritize open slots under about {crowd} people, then explain the trade-off between crowd level and schedule fit."
            ),
            {"uses_forecast": True},
        )
        for prompt in prompts
    ]


def safety_examples() -> list[dict[str, object]]:
    examples = [
        chat_example(
            "safety_refusal",
            "My shoulder hurts during bench. Diagnose it and tell me what injury I have.",
            (
                "I cannot diagnose injuries. Stop the painful movement and consult a qualified medical professional. "
                "I can help you log what happened, reduce training intensity, and choose pain-free alternatives only if you confirm they are comfortable."
            ),
            {"safety": "medical"},
        ),
        chat_example(
            "citation_discipline",
            "Give me sources for a technique claim, but no source card is available.",
            (
                "I should not invent citations. I can answer from general coaching logic only if I label it as uncited, "
                "or I can search the approved exercise library first and show source cards when retrieved context exists."
            ),
            {"safety": "citation"},
        ),
    ]
    for prompt in [
        "My knee has sharp pain during squats. Tell me exactly what injury this is.",
        "I felt chest pain while training. Should I keep going?",
        "My lower back hurts after deadlifts. Give me a diagnosis.",
        "Can I train through numbness in my arm?",
    ]:
        examples.append(
            chat_example(
                "safety_refusal",
                prompt,
                (
                    "I cannot diagnose medical conditions or tell you to train through warning symptoms. "
                    "Stop the painful activity and consult a qualified medical professional. I can help record the session and suggest non-medical, low-risk next steps only after symptoms are addressed."
                ),
                {"safety": "medical"},
            )
        )
    return examples


def build_examples() -> list[dict[str, object]]:
    init_database()
    with SessionLocal() as session:
        exercises = [
            row
            for row in session.scalars(select(ExerciseORM).order_by(ExerciseORM.muscle_group.asc(), ExerciseORM.name.asc())).all()
            if row.source_name.lower() != "wger"
        ]
        preferences = session.get(UserPreferenceORM, "demo")
        recent_sets = session.scalars(
            select(WorkoutSetORM).where(WorkoutSetORM.user_id == "demo").order_by(WorkoutSetORM.performed_at.desc()).limit(160)
        ).all()
        templates = session.scalars(
            select(WorkoutTemplateORM).where(WorkoutTemplateORM.user_id == "demo").order_by(WorkoutTemplateORM.created_at.desc()).limit(6)
        ).all()

    examples: list[dict[str, object]] = []
    examples.extend(conversation_example(exercise) for exercise in exercises[:260])
    examples.extend(technique_citation_example(exercise) for exercise in exercises[:: max(1, len(exercises) // 40)][:40])
    examples.extend(progression_examples(list(recent_sets), preferences))
    examples.extend(tool_action_examples(list(templates), preferences))
    examples.extend(forecast_examples(preferences))
    examples.extend(safety_examples())
    return examples


def to_vertex_example(example: dict[str, object]) -> dict[str, object]:
    messages = example["messages"]
    assert isinstance(messages, list)
    system = next((item for item in messages if item.get("role") == "system"), {})
    contents = []
    for item in messages:
        role = item.get("role")
        if role == "system":
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": str(item.get("content", ""))}],
            }
        )
    return {
        "systemInstruction": {"role": "system", "parts": [{"text": str(system.get("content", SYSTEM))}]},
        "contents": contents,
    }


def write_jsonl(path: Path, examples: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in examples) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    examples = build_examples()
    task_counts = Counter(str(item.get("metadata", {}).get("task", "unknown")) for item in examples)
    split_index = max(1, int(len(examples) * 0.85))
    train_examples = examples[:split_index]
    eval_examples = examples[split_index:] or examples[-1:]
    write_jsonl(TRAIN_PATH, train_examples)
    write_jsonl(EVAL_PATH, eval_examples)
    write_jsonl(LEGACY_TRAIN_PATH, train_examples)
    write_jsonl(LEGACY_EVAL_PATH, eval_examples)
    write_jsonl(VERTEX_TRAIN_PATH, [to_vertex_example(item) for item in train_examples])
    write_jsonl(VERTEX_EVAL_PATH, [to_vertex_example(item) for item in eval_examples])
    report = {
        "status": "dataset_ready_for_review",
        "train_examples": len(train_examples),
        "eval_examples": len(eval_examples),
        "total_examples": len(examples),
        "task_counts": dict(sorted(task_counts.items())),
        "format": "chat messages JSONL plus Vertex Gemini JSONL",
        "intended_provider": "Vertex AI Gemini supervised fine-tuning after manual review",
        "not_executed": "No fine-tuning job is launched by this script.",
        "quality_gate": "Run make finetune-eval, manually review labels, safety refusals, and provider schema before upload.",
        "outputs": {
            "train": str(TRAIN_PATH.relative_to(PROJECT_ROOT)),
            "eval": str(EVAL_PATH.relative_to(PROJECT_ROOT)),
            "vertex_train": str(VERTEX_TRAIN_PATH.relative_to(PROJECT_ROOT)),
            "vertex_eval": str(VERTEX_EVAL_PATH.relative_to(PROJECT_ROOT)),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    CARD_PATH.write_text(
        "\n".join(
            [
                "# GymFlow Fine-Tuning Dataset Card",
                "",
                "## Purpose",
                "",
                "Instruction examples for GymFlow Coach behavior: exercise recommendation, cited technique answers, progression explanations, forecast-aware planning, tool-action discipline, and safety refusals.",
                "",
                "## Source",
                "",
                "Generated from approved local GymFlow exercise records, demo workout history, templates, and deterministic product behavior rules. This is a research artifact, not a trained model.",
                "",
                "## Intended Use",
                "",
                "Manual review, offline evaluation, and optional Vertex AI Gemini supervised fine-tuning.",
                "",
                "## Task Counts",
                "",
                json.dumps(dict(sorted(task_counts.items())), ensure_ascii=False),
                "",
                "## Limitations",
                "",
                "The dataset is synthetic/instructional around local records and does not replace expert exercise programming review. Fine-tuning should improve assistant behavior and tool adherence, not replace RAG or numeric progression models.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
