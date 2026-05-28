from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINE_TUNING_DIR = ROOT / "ml" / "fine_tuning"
REPORTS_DIR = ROOT / "ml" / "reports"
REQUEST_PATH = FINE_TUNING_DIR / "vertex_gemini_tuning_request.json"
RESPONSE_PATH = FINE_TUNING_DIR / "vertex_gemini_tuning_launch_response.json"
STATUS_PATH = REPORTS_DIR / "vertex_gemini_tuning_status.json"
GCLOUD_CMD = os.getenv(
    "GCLOUD_CMD",
    r"C:\Users\djprotejee\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
)


def run_gcloud(*args: str) -> str:
    command = [GCLOUD_CMD, *args]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def build_payload(args: argparse.Namespace) -> dict[str, object]:
    supervised_spec: dict[str, object] = {
        "trainingDatasetUri": args.train_uri,
        "validationDatasetUri": args.eval_uri,
    }
    if args.epochs or args.adapter_size or args.learning_rate_multiplier:
        hyper_parameters: dict[str, object] = {}
        if args.epochs:
            hyper_parameters["epochCount"] = str(args.epochs)
        if args.adapter_size:
            hyper_parameters["adapterSize"] = args.adapter_size
        if args.learning_rate_multiplier:
            hyper_parameters["learningRateMultiplier"] = args.learning_rate_multiplier
        supervised_spec["hyperParameters"] = hyper_parameters
    if args.export_last_checkpoint_only:
        supervised_spec["exportLastCheckpointOnly"] = True

    return {
        "baseModel": args.base_model,
        "supervisedTuningSpec": supervised_spec,
        "tunedModelDisplayName": args.display_name,
    }


def post_json(url: str, payload: dict[str, object], token: str) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Vertex tuning request failed: HTTP {exc.code}: {details}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a Vertex AI Gemini supervised tuning job.")
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", "gymflow-ai-497521"))
    parser.add_argument("--region", default=os.getenv("VERTEX_AI_REGION", "us-central1"))
    parser.add_argument("--base-model", default=os.getenv("VERTEX_GEMINI_BASE_MODEL", "gemini-2.5-flash"))
    parser.add_argument(
        "--train-uri",
        default=os.getenv(
            "VERTEX_TUNING_TRAIN_URI",
            "gs://gymflow-ai-tuning-a1/gymflow/vertex_gemini_coach_behavior_train.jsonl",
        ),
    )
    parser.add_argument(
        "--eval-uri",
        default=os.getenv(
            "VERTEX_TUNING_EVAL_URI",
            "gs://gymflow-ai-tuning-a1/gymflow/vertex_gemini_coach_behavior_eval.jsonl",
        ),
    )
    parser.add_argument("--display-name", default="gymflow-coach-behavior-tuning")
    parser.add_argument("--epochs", type=int, default=0, help="Leave unset by default so Vertex can auto-select.")
    parser.add_argument(
        "--adapter-size",
        default="",
        choices=["", "ADAPTER_SIZE_ONE", "ADAPTER_SIZE_FOUR", "ADAPTER_SIZE_EIGHT", "ADAPTER_SIZE_SIXTEEN"],
        help="Leave unset by default so Vertex can auto-select.",
    )
    parser.add_argument("--learning-rate-multiplier", type=float, default=0.0)
    parser.add_argument("--export-last-checkpoint-only", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Actually create the paid/credit-consuming tuning job.")
    parser.add_argument(
        "--acknowledge-cost",
        action="store_true",
        help="Required with --submit to confirm that the job can consume Google Cloud credits.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_payload(args)
    FINE_TUNING_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REQUEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    url = f"https://{args.region}-aiplatform.googleapis.com/v1/projects/{args.project}/locations/{args.region}/tuningJobs"
    output = {
        "status": "request_prepared",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "region": args.region,
        "endpoint": url,
        "request_path": str(REQUEST_PATH.relative_to(ROOT)),
        "submit": args.submit,
        "payload": payload,
        "notes": [
            "Submitting this request can consume Google Cloud trial credits.",
            "Default hyperparameters are intentionally omitted so Vertex AI can choose recommended values.",
        ],
    }

    if not args.submit:
        print(json.dumps(output, indent=2))
        return
    if not args.acknowledge_cost:
        raise SystemExit("Refusing to submit without --acknowledge-cost.")

    token = run_gcloud("auth", "print-access-token")
    response = post_json(url, payload, token)
    RESPONSE_PATH.write_text(json.dumps(response, indent=2), encoding="utf-8")
    status_output = {
        "status": "submitted",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "region": args.region,
        "request_path": str(REQUEST_PATH.relative_to(ROOT)),
        "response_path": str(RESPONSE_PATH.relative_to(ROOT)),
        "tuning_job_name": response.get("name"),
        "vertex_response": response,
    }
    STATUS_PATH.write_text(json.dumps(status_output, indent=2), encoding="utf-8")
    print(json.dumps(status_output, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
