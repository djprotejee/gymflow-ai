# Fine-Tuning Research Branch

The supervisor recommended studying fine-tuning so the AI trainer does not rely only on generic model advice.

## Purpose

Investigate whether a small domain-adapted instruction dataset can improve the assistant's behavior for:

- exercise explanation;
- safe training-plan adaptation;
- progressive overload suggestions;
- forecast-aware training recommendations;
- safe refusal for medical or injury-related questions.

## Preferred Order

1. Build a controlled RAG-based assistant first.
2. Create a curated exercise and training knowledge base.
3. Define an instruction dataset.
4. Compare:
   - base assistant;
   - RAG assistant;
   - fine-tuned or LoRA-adapted assistant.

## Current Artifact State

- `scripts/build_finetuning_dataset.py` creates a Coach behavior dataset from approved GymFlow exercise records, demo workout history, templates, and deterministic tool-action rules.
- Latest generated files:
  - `ml/fine_tuning/coach_behavior_train.jsonl`
  - `ml/fine_tuning/coach_behavior_eval.jsonl`
  - `ml/fine_tuning/vertex_gemini_coach_behavior_train.jsonl`
  - `ml/fine_tuning/vertex_gemini_coach_behavior_eval.jsonl`
  - `ml/reports/fine_tuning_readiness.json`
  - `ml/reports/coach_tuning_dataset_eval.json`
- Latest generated counts: `278` train examples, `50` eval examples, `328` total examples, `13` task groups, readiness score `100.0`.
- Vertex cloud inputs are prepared for project `gymflow-ai-497521`: bucket `gs://gymflow-ai-tuning-a1` in `us-central1`, uploaded Vertex train/eval JSONL, and a real-URI template at `ml/fine_tuning/vertex_gemini_tuning_job.template.json`.
- First Vertex AI Gemini supervised tuning job `projects/1029322077032/locations/us-central1/tuningJobs/3295631880572895232` failed immediately because Vertex rejected an unsupported `metadata` field in the uploaded JSONL.
- The Vertex-only JSONL writer now omits `metadata`, while the local review dataset keeps metadata for task coverage analysis.
- Replacement job `projects/1029322077032/locations/us-central1/tuningJobs/4324141445473632256` was submitted after the schema fix and finished with `JOB_STATE_SUCCEEDED`. Tuned model resource: `projects/1029322077032/locations/us-central1/models/4009681961743286272@1`; final endpoint: `projects/1029322077032/locations/us-central1/endpoints/6122406748654403584`; total billable tokens reported by Vertex: `38276`.
- Compact post-tuning evaluation is available in `ml/reports/vertex_tuned_coach_eval.json` and `ml/reports/vertex_tuned_coach_eval.md`. The base model scored higher on the small keyword metric (`0.736` vs `0.639`), while the tuned endpoint showed useful task behavior on target-set tool action and safety refusal. This should be documented as an implemented and evaluated fine-tuning research branch, not as a replacement for RAG or the base model.
- `scripts/prepare_vertex_finetuning_job.py` writes a template-only Vertex AI Gemini tuning config.
- `scripts/launch_vertex_tuning_job.py` writes the REST request JSON by default and only submits when called with `--submit --acknowledge-cost`.
- `scripts/manage_vertex_tuning_job.py` lists, fetches, or cancels Vertex tuning jobs through the official REST endpoints.

## Vertex Commands

Prepare a request without launching:

```powershell
make vertex-finetune-request
```

Submit the job after confirming that Google Cloud credits may be consumed:

```powershell
make vertex-finetune-launch
```

Poll or cancel the latest recorded job:

```powershell
make vertex-finetune-status
make vertex-finetune-cancel
```

Run the compact base-versus-tuned evaluation:

```powershell
make vertex-finetune-eval
```

The request path is `ml/fine_tuning/vertex_gemini_tuning_request.json`. Launch and status responses are written to `ml/fine_tuning/vertex_gemini_tuning_launch_response.json` and `ml/reports/vertex_gemini_tuning_status.json`.

## Dataset Schema

The local review dataset uses chat-style `messages` JSONL with `system`, `user`, and `assistant` roles. The script also writes Vertex Gemini-style JSONL with `systemInstruction` and `contents`.

Current task groups cover exercise recommendation, cited technique answers, progression explanations, forecast-aware recommendations, tool-action discipline, citation discipline, and safety refusal.

## Safety Rules

The fine-tuned assistant must not diagnose injuries, prescribe medical treatment, or invent citations. If pain, injury, or medical conditions are mentioned, it must recommend consulting a qualified professional.
