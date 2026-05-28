from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.app.database import SessionLocal, init_database
from apps.api.app.services.rag_retrieval import retrieve_rag_context


REPORT_DIR = Path("ml/reports")
JSON_PATH = REPORT_DIR / "rag_retrieval_eval.json"
MD_PATH = REPORT_DIR / "rag_retrieval_eval.md"


EVAL_QUERIES = [
    {
        "query": "bench press technique",
        "expected_source_type": "exercise_library",
        "expected_title_terms": ["bench", "press"],
    },
    {
        "query": "lat pulldown common mistakes",
        "expected_source_type": "exercise_library",
        "expected_title_terms": ["lat", "pulldown"],
    },
    {
        "query": "my recent workout progress",
        "expected_source_type": "workout_history",
        "expected_title_terms": ["recent", "workout"],
    },
    {
        "query": "saved workout template",
        "expected_source_type": "workout_template",
        "expected_title_terms": [],
    },
    {
        "query": "preferred quiet training time",
        "expected_source_type": "user_preferences",
        "expected_title_terms": ["training", "preferences"],
    },
    {
        "query": "scheduled workouts this week",
        "expected_source_type": "scheduled_workouts",
        "expected_title_terms": ["scheduled", "workouts"],
    },
]


def is_relevant(hit: object, expected_source_type: str, expected_title_terms: list[str]) -> bool:
    title = hit.chunk.title.lower()
    source_match = hit.chunk.source_type == expected_source_type
    title_match = not expected_title_terms or all(term in title for term in expected_title_terms)
    return source_match and title_match


def evaluate_query(session, item: dict[str, object]) -> dict[str, object]:
    hits = retrieve_rag_context(
        session=session,
        query=str(item["query"]),
        user_id="demo",
        gym_id="gym_008",
        limit=6,
    )
    expected_source_type = str(item["expected_source_type"])
    expected_title_terms = [str(term) for term in item["expected_title_terms"]]
    relevant_rank = 0
    for index, hit in enumerate(hits, start=1):
        if is_relevant(hit, expected_source_type, expected_title_terms):
            relevant_rank = index
            break
    return {
        "query": item["query"],
        "expected_source_type": expected_source_type,
        "hit_at_1": relevant_rank == 1,
        "hit_at_3": 0 < relevant_rank <= 3,
        "hit_at_6": 0 < relevant_rank <= 6,
        "reciprocal_rank": round(1 / relevant_rank, 4) if relevant_rank else 0,
        "relevant_rank": relevant_rank,
        "top_hits": [
            {
                "chunk_id": hit.chunk.chunk_id,
                "title": hit.chunk.title,
                "source_type": hit.chunk.source_type,
                "score": hit.score,
                "matched_terms": list(hit.matched_terms),
            }
            for hit in hits[:6]
        ],
    }


def main() -> None:
    init_database()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as session:
        rows = [evaluate_query(session, item) for item in EVAL_QUERIES]
    total = max(1, len(rows))
    summary = {
        "queries": total,
        "hit_at_1": round(sum(1 for row in rows if row["hit_at_1"]) / total, 4),
        "hit_at_3": round(sum(1 for row in rows if row["hit_at_3"]) / total, 4),
        "hit_at_6": round(sum(1 for row in rows if row["hit_at_6"]) / total, 4),
        "mrr": round(sum(float(row["reciprocal_rank"]) for row in rows) / total, 4),
        "retrieval_method": "BM25-style lexical retrieval over GymFlow chunks",
        "note": "This evaluates the current non-vector RAG retrieval layer; it is not a fine-tuned model evaluation.",
    }
    JSON_PATH.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    md_lines = [
        "# RAG Retrieval Evaluation",
        "",
        f"- Method: {summary['retrieval_method']}",
        f"- Queries: {summary['queries']}",
        f"- Hit@1: {summary['hit_at_1']}",
        f"- Hit@3: {summary['hit_at_3']}",
        f"- Hit@6: {summary['hit_at_6']}",
        f"- MRR: {summary['mrr']}",
        "",
        "| Query | Expected source | Relevant rank | Top hit |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        top_hit = row["top_hits"][0] if row["top_hits"] else {"title": "none", "source_type": "none"}
        md_lines.append(
            f"| {row['query']} | {row['expected_source_type']} | {row['relevant_rank'] or 'miss'} | "
            f"{top_hit['title']} ({top_hit['source_type']}) |"
        )
    md_lines.extend(["", f"Note: {summary['note']}"])
    MD_PATH.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
