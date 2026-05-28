from __future__ import annotations

import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "ml" / "fine_tuning" / "vertex_gemini_tuning_job.template.json"


def main() -> None:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    region = os.getenv("VERTEX_AI_REGION", "us-central1")
    base_model = os.getenv("VERTEX_GEMINI_BASE_MODEL", "gemini-2.5-flash")
    gcs_train_uri = os.getenv("VERTEX_TUNING_TRAIN_URI", "gs://YOUR_BUCKET/gymflow/vertex_gemini_coach_behavior_train.jsonl")
    gcs_eval_uri = os.getenv("VERTEX_TUNING_EVAL_URI", "gs://YOUR_BUCKET/gymflow/vertex_gemini_coach_behavior_eval.jsonl")
    payload = {
        "status": "template_only",
        "project_id": project_id or "SET_GOOGLE_CLOUD_PROJECT",
        "region": region,
        "base_model": base_model,
        "training_data_uri": gcs_train_uri,
        "validation_data_uri": gcs_eval_uri,
        "display_name": "gymflow-coach-behavior-tuning",
        "notes": [
            "This file does not launch a Vertex AI job.",
            "Upload reviewed Vertex Gemini JSONL files to Cloud Storage before tuning.",
            "Run make finetune-eval before upload.",
            "Keep RAG enabled after tuning; tuning changes behavior, not the factual knowledge base.",
        ],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not project_id:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT before launching any real Vertex AI tuning job.")


if __name__ == "__main__":
    main()
