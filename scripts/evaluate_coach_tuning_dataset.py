from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "ml" / "fine_tuning"
TRAIN_PATH = DATASET_DIR / "coach_behavior_train.jsonl"
EVAL_PATH = DATASET_DIR / "coach_behavior_eval.jsonl"
REPORT_JSON = ROOT / "ml" / "reports" / "coach_tuning_dataset_eval.json"
REPORT_MD = ROOT / "ml" / "reports" / "coach_tuning_dataset_eval.md"
REQUIRED_TASKS = {
    "exercise_recommendation",
    "rag_cited_technique",
    "progression_explanation",
    "tool_action_schedule_week",
    "tool_action_log_target_set",
    "forecast_aware_recommendation",
    "safety_refusal",
    "citation_discipline",
}
MIN_NON_RECOMMENDATION_EXAMPLES = 50


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset file: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    return rows


def validate_example(example: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    messages = example.get("messages")
    if not isinstance(messages, list) or len(messages) < 3:
        return ["messages must contain system, user, and assistant turns"]
    roles = [item.get("role") for item in messages if isinstance(item, dict)]
    if roles[:3] != ["system", "user", "assistant"]:
        issues.append("first three roles must be system, user, assistant")
    for item in messages:
        if not isinstance(item, dict) or not str(item.get("content", "")).strip():
            issues.append("all messages need non-empty content")
    task = str(example.get("metadata", {}).get("task", ""))
    assistant = str(messages[-1].get("content", ""))
    if task.startswith("tool_action") and "tool" not in assistant.lower():
        issues.append("tool-action examples should explicitly mention tool use")
    if task in {"rag_cited_technique", "citation_discipline"} and "source" not in assistant.lower() and "citation" not in assistant.lower():
        issues.append("citation examples should mention source or citation discipline")
    if task == "safety_refusal" and "diagnose" not in assistant.lower():
        issues.append("safety refusal should explicitly avoid diagnosis")
    if task == "progression_explanation" and "aim" not in assistant.lower():
        issues.append("progression examples should include an aim target")
    return issues


def main() -> None:
    train = read_jsonl(TRAIN_PATH)
    eval_rows = read_jsonl(EVAL_PATH)
    all_rows = train + eval_rows
    task_counts = Counter(str(row.get("metadata", {}).get("task", "unknown")) for row in all_rows)
    issues: list[dict[str, Any]] = []
    for index, row in enumerate(all_rows):
        for issue in validate_example(row):
            issues.append({"index": index, "task": row.get("metadata", {}).get("task", "unknown"), "issue": issue})
    missing_tasks = sorted(REQUIRED_TASKS - set(task_counts))
    non_recommendation_count = len(all_rows) - task_counts.get("exercise_recommendation", 0)
    readiness_score = max(0.0, 100.0 - len(issues) * 2.5 - len(missing_tasks) * 8.0)
    if non_recommendation_count < MIN_NON_RECOMMENDATION_EXAMPLES:
        readiness_score = max(0.0, readiness_score - 10.0)
    report = {
        "status": "ok" if not issues and not missing_tasks else "needs_review",
        "train_examples": len(train),
        "eval_examples": len(eval_rows),
        "total_examples": len(all_rows),
        "task_counts": dict(sorted(task_counts.items())),
        "missing_tasks": missing_tasks,
        "non_recommendation_examples": non_recommendation_count,
        "minimum_non_recommendation_examples": MIN_NON_RECOMMENDATION_EXAMPLES,
        "issue_count": len(issues),
        "issues": issues[:40],
        "readiness_score": round(readiness_score, 1),
        "note": "This validates local dataset structure and task coverage. It does not execute a Vertex AI fine-tuning job.",
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Coach Fine-Tuning Dataset Evaluation",
        "",
        f"- Status: `{report['status']}`",
        f"- Train examples: `{len(train)}`",
        f"- Eval examples: `{len(eval_rows)}`",
        f"- Readiness score: `{report['readiness_score']}`",
        f"- Issue count: `{len(issues)}`",
        "",
        "## Task Counts",
        "",
    ]
    for task, count in sorted(task_counts.items()):
        lines.append(f"- `{task}`: `{count}`")
    if missing_tasks:
        lines.extend(["", "## Missing Tasks", ""])
        lines.extend(f"- `{task}`" for task in missing_tasks)
    if issues:
        lines.extend(["", "## First Issues", ""])
        lines.extend(f"- `{item['task']}`: {item['issue']}" for item in issues[:20])
    lines.extend(["", str(report["note"]), ""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
