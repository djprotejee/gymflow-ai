from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.app.anatomy import resolve_anatomy_regions, validate_anatomy_assignment

OUTPUT_PATH = ROOT / "data" / "external" / "exercise_import_preview.json"


def first_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "name_en", "full_name", "short_name", "alias", "description_source", "description", "url"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    if isinstance(value, list):
        for item in value:
            text = str(item).strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def normalize_muscle_group(*values: Any) -> str:
    text = " ".join(first_text(value).lower() for value in values if first_text(value))
    rules = [
        (("chest", "pectorals", "serratus"), "Chest"),
        (("back", "lat", "trap", "rhomboid"), "Back"),
        (("quad", "adductor", "abductor", "thigh"), "Legs"),
        (("hamstring",), "Hamstrings"),
        (("glute", "hip"), "Glutes"),
        (("calf", "gastrocnemius", "soleus"), "Calves"),
        (("shoulder", "delt", "rotator"), "Shoulders"),
        (("bicep", "tricep", "forearm", "arm"), "Arms"),
        (("ab", "core", "waist", "oblique"), "Core"),
        (("cardio", "full body", "full-body"), "Conditioning"),
    ]
    for needles, group in rules:
        if any(needle in text for needle in needles):
            return group
    return "Unknown"


def strip_html_tags(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", "\n", value)
    no_zero_width = no_tags.replace("\u200b", "")
    return html.unescape(no_zero_width)


def select_wger_translation(record: dict[str, Any]) -> dict[str, Any]:
    translations = record.get("translations") if isinstance(record.get("translations"), list) else []
    english_translations = [
        item
        for item in translations
        if isinstance(item, dict) and str(item.get("language") or "") == "2"
    ]
    if english_translations:
        return english_translations[0]
    return translations[0] if translations and isinstance(translations[0], dict) else {}


def normalize_media_gallery(
    record: dict[str, Any],
    source_name: str,
    source_license: str,
    exercise_name: str,
) -> list[dict[str, Any]]:
    if isinstance(record.get("images"), list) or isinstance(record.get("videos"), list):
        gallery: list[dict[str, Any]] = []
        for sort_order, image in enumerate(record.get("images") or []):
            if not isinstance(image, dict):
                continue
            image_url = str(image.get("image") or "").strip()
            if not image_url:
                continue
            gallery.append(
                {
                    "media_type": "external_image",
                    "media_url": image_url,
                    "thumbnail_url": image_url,
                    "title": f"{exercise_name} image",
                    "source_name": source_name,
                    "source_url": str(image.get("license_derivative_source_url") or image_url).strip(),
                    "source_license": source_license,
                    "attribution": first_text(image.get("license_author")) or f"Imported preview from {source_name}; verify attribution before production use.",
                    "checked_at": "2026-05-24",
                    "embed_allowed": True,
                    "download_allowed": False,
                    "requires_attribution": True,
                    "sort_order": sort_order,
                    "license_notes": "Preview only. Confirm image-level reuse rights before app import.",
                }
            )
        for image_count, video in enumerate(record.get("videos") or []):
            if not isinstance(video, dict):
                continue
            video_url = str(video.get("video") or video.get("url") or "").strip()
            if not video_url:
                continue
            gallery.append(
                {
                    "media_type": "external_video",
                    "media_url": video_url,
                    "thumbnail_url": "",
                    "title": f"{exercise_name} video",
                    "source_name": source_name,
                    "source_url": video_url,
                    "source_license": source_license,
                    "attribution": first_text(video.get("license_author")) or f"Imported preview from {source_name}; verify attribution before production use.",
                    "checked_at": "2026-05-24",
                    "embed_allowed": True,
                    "download_allowed": False,
                    "requires_attribution": True,
                    "sort_order": len(gallery) + image_count,
                    "license_notes": "Preview only. Confirm video-level reuse rights before app import.",
                }
            )
        return gallery

    gif_url = str(record.get("gifUrl") or record.get("image") or record.get("imageUrl") or "").strip()
    source_url = str(record.get("sourceUrl") or record.get("url") or gif_url).strip()
    if not gif_url and not source_url:
        return []
    media_type = "external_image" if gif_url else "link"
    media_url = gif_url or source_url
    thumbnail_url = str(record.get("thumbnailUrl") or gif_url or "").strip()
    embed_allowed = bool(gif_url) or bool(str(record.get("embedAllowed") or "").strip())
    requires_attribution = True if str(record.get("requiresAttribution") or "").strip() == "" else bool(record.get("requiresAttribution"))
    return [
        {
            "media_type": media_type,
            "media_url": media_url,
            "thumbnail_url": thumbnail_url,
            "title": f"{exercise_name} external media",
            "source_name": source_name,
            "source_url": source_url,
            "source_license": source_license,
            "attribution": f"Imported preview from {source_name}; verify license and attribution before production use.",
            "checked_at": "2026-05-24",
            "embed_allowed": embed_allowed,
            "download_allowed": False,
            "requires_attribution": requires_attribution,
            "sort_order": 0,
            "license_notes": "Preview only. Confirm provider media reuse rights before app import.",
        }
    ]


def flatten_wger_instruction_lines(record: dict[str, Any]) -> list[str]:
    translation = select_wger_translation(record)
    if translation:
        source_text = str(translation.get("description_source") or translation.get("description") or "").strip()
        if source_text:
            text = strip_html_tags(source_text).replace("\r", "\n")
            text = re.sub(r"\n+", "\n", text).strip()
            text = re.sub(r"Notes\s*\(Instructions?\)\s*:\s*", "", text, flags=re.IGNORECASE)
            numbered_steps = re.split(r"(?:^|\n)\s*\d+\.\s*", text)
            cleaned_numbered_steps = [step.strip(" -\t\n") for step in numbered_steps if step.strip(" -\t\n")]
            if len(cleaned_numbered_steps) >= 2:
                return cleaned_numbered_steps
            lines = [line.strip(" -\t") for line in text.split("\n")]
            merged_lines: list[str] = []
            for line in lines:
                if not line:
                    continue
                if merged_lines and not re.match(r"^[A-Z0-9]", line):
                    merged_lines[-1] = f"{merged_lines[-1]} {line}".strip()
                    continue
                merged_lines.append(line)
            return merged_lines
    return []


def normalize_source_license(record: dict[str, Any], fallback_license: str) -> str:
    license_info = record.get("license")
    if isinstance(license_info, dict):
        short_name = str(license_info.get("short_name") or "").strip()
        url = str(license_info.get("url") or "").strip()
        if short_name and url:
            return f"{short_name} - {url}"
        if short_name:
            return short_name
    return fallback_license


def normalize_record(record: dict[str, Any], source_name: str, source_license: str) -> dict[str, Any]:
    preferred_translation = select_wger_translation(record)
    name = str(record.get("name") or record.get("exerciseName") or preferred_translation.get("name") or "").strip()
    target = first_text(record.get("target") or record.get("targetMuscles") or record.get("primaryMuscles") or record.get("muscle") or record.get("muscles"))
    body_part = first_text(record.get("bodyPart") or record.get("bodyParts") or record.get("category"))
    equipment = first_text(record.get("equipment") or record.get("equipments"))
    gif_url = str(record.get("gifUrl") or record.get("image") or record.get("imageUrl") or "").strip()
    source_url = str(record.get("sourceUrl") or record.get("url") or gif_url or f"https://wger.de/api/v2/exerciseinfo/{record.get('id', '')}/").strip()
    instructions = record.get("instructions") or record.get("steps") or flatten_wger_instruction_lines(record)
    if isinstance(instructions, str):
        instructions = [instructions]
    if not isinstance(instructions, list):
        instructions = []
    instructions = [
        re.sub(r"^Step:?\s*\d+\s*", "", str(item).strip(), flags=re.IGNORECASE)
        for item in instructions
        if str(item).strip()
    ]

    slug = (
        name.lower()
        .replace("&", "and")
        .replace("/", " ")
        .replace("_", " ")
        .replace("  ", " ")
        .strip()
        .replace(" ", "-")
    )
    muscle_group = normalize_muscle_group(target, body_part)
    normalized_license = normalize_source_license(record, source_license)
    primary_muscles, secondary_muscles = resolve_anatomy_regions(slug, muscle_group)
    anatomy_note = ""
    try:
        validate_anatomy_assignment(slug, primary_muscles, secondary_muscles)
    except ValueError as error:
        # External APIs use inconsistent muscle labels. Keep the preview usable and let reviewers fix anatomy later.
        anatomy_note = str(error)
        primary_muscles = []
        secondary_muscles = []
    return {
        "slug": slug,
        "name": name,
        "category": body_part or "Uncategorized",
        "muscle_group": muscle_group,
        "difficulty": "Unverified",
        "equipment": equipment,
        "media_type": "external_image" if gif_url else "none",
        "media_url": gif_url,
        "youtube_video_id": "",
        "source_name": source_name,
        "source_url": source_url,
        "source_license": normalized_license,
        "attribution": first_text(record.get("license_author")) or f"Imported preview from {source_name}; verify license and attribution before production use.",
        "checked_at": "2026-05-24",
        "primary_muscles": primary_muscles,
        "secondary_muscles": secondary_muscles,
        "anatomy_note": anatomy_note,
        "instructions": [str(item).strip() for item in instructions if str(item).strip()],
        "cues": [],
        "mistakes": [],
        "video_url": source_url,
        "image_hint": "external-import-preview",
        "media_gallery": normalize_media_gallery(record, source_name=source_name, source_license=normalized_license, exercise_name=name or slug),
        "raw": record,
    }


def is_importable_wger_record(record: dict[str, Any]) -> bool:
    translation = select_wger_translation(record)
    if not translation:
        return False
    translation_name = str(translation.get("name") or "").strip()
    if not translation_name:
        return False
    return str(translation.get("language") or "") == "2"


def fetch_json(url: str, api_key: str, api_host: str | None) -> Any:
    headers = {
        "Accept": "application/json",
        "User-Agent": "GymFlowAI/0.1 thesis prototype",
    }
    if api_key:
        headers["X-RapidAPI-Key"] = api_key
    if api_host:
        headers["X-RapidAPI-Host"] = api_host
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_records(url: str, api_key: str, api_host: str | None, limit: int) -> list[dict[str, Any]]:
    payload = fetch_json(url, api_key=api_key, api_host=api_host)
    if isinstance(payload, list):
        return [record for record in payload[: max(1, limit)] if isinstance(record, dict)]
    if not isinstance(payload, dict):
        return []

    if isinstance(payload.get("results"), list):
        records = [record for record in payload.get("results", []) if isinstance(record, dict)]
        next_url = payload.get("next")
        while next_url and len(records) < max(1, limit):
            next_payload = fetch_json(str(next_url), api_key=api_key, api_host=api_host)
            if not isinstance(next_payload, dict) or not isinstance(next_payload.get("results"), list):
                break
            records.extend(record for record in next_payload["results"] if isinstance(record, dict))
            next_url = next_payload.get("next")
        return records[: max(1, limit)]

    data = payload.get("data")
    if isinstance(data, list):
        records = [record for record in data if isinstance(record, dict)]
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        next_cursor = meta.get("nextCursor")
        has_next_page = bool(meta.get("hasNextPage"))
        while next_cursor and has_next_page and len(records) < max(1, limit):
            separator = "&" if "?" in url else "?"
            next_payload = fetch_json(f"{url}{separator}cursor={next_cursor}", api_key=api_key, api_host=api_host)
            if not isinstance(next_payload, dict) or not isinstance(next_payload.get("data"), list):
                break
            records.extend(record for record in next_payload["data"] if isinstance(record, dict))
            next_meta = next_payload.get("meta") if isinstance(next_payload.get("meta"), dict) else {}
            next_cursor = next_meta.get("nextCursor")
            has_next_page = bool(next_meta.get("hasNextPage"))
        return records[: max(1, limit)]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a checked preview file from an external exercise API. This does not import into the app DB."
    )
    parser.add_argument(
        "--preset",
        default="",
        help="Optional source preset. Supported: exercisedb_oss, wger",
    )
    parser.add_argument("--source-name", default=os.getenv("EXERCISE_SOURCE_NAME", "Exercise API"))
    parser.add_argument("--source-license", default=os.getenv("EXERCISE_SOURCE_LICENSE", "Unverified external API terms"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_url = os.getenv("EXERCISE_API_URL", "").strip()
    api_key = os.getenv("EXERCISE_API_KEY", "").strip()
    api_host = os.getenv("EXERCISE_API_HOST", "").strip() or None

    if args.preset.strip().lower() == "exercisedb_oss":
        if not api_url:
            api_url = "https://oss.exercisedb.dev/api/v1/exercises"
        if args.source_name == "Exercise API":
            args.source_name = "OSS ExerciseDB"
        if args.source_license == "Unverified external API terms":
            args.source_license = "See provider terms; non-commercial restrictions may apply."
    elif args.preset.strip().lower() == "wger":
        if not api_url:
            api_url = "https://wger.de/api/v2/exerciseinfo/?language=2"
        if args.source_name == "Exercise API":
            args.source_name = "wger"
        if args.source_license == "Unverified external API terms":
            args.source_license = "Exercise data: CC BY-SA via wger docs; check image-level provenance before import."

    if not api_url:
        print(
            json.dumps(
                {
                    "status": "missing_config",
                    "required_env": ["EXERCISE_API_URL"],
                    "optional_env": ["EXERCISE_API_KEY", "EXERCISE_API_HOST", "EXERCISE_SOURCE_NAME", "EXERCISE_SOURCE_LICENSE"],
                    "example": "EXERCISE_API_URL=https://exercisedb.p.rapidapi.com/exercises EXERCISE_API_KEY=... EXERCISE_API_HOST=exercisedb.p.rapidapi.com make exercise-source",
                    "presets": ["--preset exercisedb_oss", "--preset wger"],
                },
                indent=2,
            )
        )
        return

    try:
        records = fetch_records(api_url, api_key=api_key, api_host=api_host, limit=args.limit)
    except (HTTPError, URLError, TimeoutError) as error:
        raise SystemExit(f"Could not fetch exercise API preview: {error}") from error

    normalized = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if args.preset.strip().lower() == "wger" and not is_importable_wger_record(record):
            continue
        normalized.append(normalize_record(record, source_name=args.source_name, source_license=args.source_license))

    result = {
        "status": "preview",
        "source_name": args.source_name,
        "source_license": args.source_license,
        "records": normalized,
        "note": "Review source terms, attribution, and media reuse rights before importing these records into the product database.",
    }

    if args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(OUTPUT_PATH), "records": len(normalized)}, indent=2))


if __name__ == "__main__":
    main()
