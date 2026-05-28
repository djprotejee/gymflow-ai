from __future__ import annotations

import json
import subprocess
import urllib.request


def read_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def read_status(url: str) -> int:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status


def read_postgres_workout_count() -> int:
    result = subprocess.run(
        [
            "docker-compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "gymflow",
            "-d",
            "gymflow",
            "-t",
            "-A",
            "-c",
            "select count(*) from workout_sets;",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def main() -> None:
    health = read_json("http://127.0.0.1:8000/health")
    summary = read_json("http://127.0.0.1:8000/summary")
    web_status = read_status("http://127.0.0.1:8080")
    workout_sets = read_postgres_workout_count()

    if health.get("status") != "ok":
        raise RuntimeError(f"API health check failed: {health}")
    if int(summary["rows"]) <= 0:
        raise RuntimeError(f"Dataset summary is empty: {summary}")
    if web_status != 200:
        raise RuntimeError(f"Web status is not 200: {web_status}")
    if workout_sets <= 0:
        raise RuntimeError("PostgreSQL workout_sets table is empty.")

    print(
        {
            "api": health,
            "web_status": web_status,
            "dataset_rows": summary["rows"],
            "gyms": summary["gyms"],
            "postgres_workout_sets": workout_sets,
        }
    )


if __name__ == "__main__":
    main()
