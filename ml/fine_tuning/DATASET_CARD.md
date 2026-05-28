# GymFlow Fine-Tuning Dataset Card

## Purpose

Instruction examples for GymFlow Coach behavior: exercise recommendation, cited technique answers, progression explanations, forecast-aware planning, tool-action discipline, and safety refusals.

## Source

Generated from approved local GymFlow exercise records, demo workout history, templates, and deterministic product behavior rules. This is a research artifact, not a trained model.

## Intended Use

Manual review, offline evaluation, and optional Vertex AI Gemini supervised fine-tuning.

## Task Counts

{"citation_discipline": 1, "exercise_recommendation": 260, "forecast_aware_recommendation": 5, "progression_explanation": 10, "rag_cited_technique": 40, "safety_refusal": 5, "tool_action_create_template": 1, "tool_action_log_target_set": 1, "tool_action_manager_promotion_draft": 1, "tool_action_reschedule_workout": 1, "tool_action_schedule_week": 1, "tool_action_template_edit": 1, "tool_action_update_preferences": 1}

## Limitations

The dataset is synthetic/instructional around local records and does not replace expert exercise programming review. Fine-tuning should improve assistant behavior and tool adherence, not replace RAG or numeric progression models.
