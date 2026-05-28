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
REPORTS_DIR = ROOT / "ml" / "reports"
STATUS_PATH = REPORTS_DIR / "vertex_gemini_tuning_status.json"
GCLOUD_CMD = os.getenv(
    "GCLOUD_CMD",
    r"C:\Users\djprotejee\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
)


def run_gcloud(*args: str) -> str:
    completed = subprocess.run([GCLOUD_CMD, *args], check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def request_json(url: str, token: str, method: str = "GET") -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=b"" if method == "POST" else None,
        headers={"Authorization": f"Bearer {token}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Vertex tuning request failed: HTTP {exc.code}: {details}") from exc


def latest_job_name() -> str:
    if not STATUS_PATH.exists():
        return ""
    data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    value = data.get("tuning_job_name") or data.get("job_name") or ""
    return str(value) if value else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or cancel Vertex AI Gemini tuning jobs.")
    parser.add_argument("action", choices=["list", "get", "cancel"])
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", "gymflow-ai-497521"))
    parser.add_argument("--region", default=os.getenv("VERTEX_AI_REGION", "us-central1"))
    parser.add_argument("--job-name", default=os.getenv("VERTEX_TUNING_JOB_NAME", ""))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = run_gcloud("auth", "print-access-token")
    base = f"https://{args.region}-aiplatform.googleapis.com/v1/projects/{args.project}/locations/{args.region}/tuningJobs"
    job_name = args.job_name or latest_job_name()

    if args.action == "list":
        result = request_json(base, token)
    else:
        if not job_name:
            raise SystemExit("Set --job-name or launch a job first so ml/reports/vertex_gemini_tuning_status.json exists.")
        url = f"https://{args.region}-aiplatform.googleapis.com/v1/{job_name}"
        if args.action == "cancel":
            url = f"{url}:cancel"
            result = request_json(url, token, method="POST")
        else:
            result = request_json(url, token)

    payload = {
        "action": args.action,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "region": args.region,
        "job_name": job_name,
        "result": result,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
