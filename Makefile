PYTHON := .venv/Scripts/python.exe
PIP := .venv/Scripts/python.exe -m pip
WEB_DIR := apps/web

.PHONY: help setup torch-setup doctor data test-data research-summary rag-eval media-coverage exercise-open-media finetune-dataset finetune-eval vertex-finetune-template vertex-finetune-request vertex-finetune-launch vertex-finetune-status vertex-finetune-eval vertex-finetune-cancel progression-train scientific-check synthetic future weather baseline train ablation sequence deep sarimax synthetic-experiment registry figures validate test api web build smoke exercise-source exercise-import reset-demo db-shell docker-smoke docker-config docker-build docker-up docker-up-d docker-rebuild docker-down clean

help:
	@echo "GymFlow AI commands"
	@echo "  make setup          Install Python and web dependencies"
	@echo "  make torch-setup    Install optional PyTorch dependency for LSTM/Transformer"
	@echo "  make doctor         Check whether the project is ready to resume"
	@echo "  make data           Prepare normalized 2026 project dataset"
	@echo "  make test-data      Validate prepared data outputs and feature engineering invariants"
	@echo "  make research-summary Build thesis-ready research findings summary from experiment artifacts"
	@echo "  make rag-eval       Evaluate current non-vector RAG retrieval layer"
	@echo "  make media-coverage Check member-visible exercise rich-media coverage"
	@echo "  make exercise-open-media Import open external exercise image refs from yuhonas/free-exercise-db"
	@echo "  make finetune-dataset Build reviewed fine-tuning JSONL candidate files"
	@echo "  make finetune-eval    Validate Coach fine-tuning dataset task coverage"
	@echo "  make vertex-finetune-template Write Vertex AI Gemini tuning job template"
	@echo "  make vertex-finetune-request  Write Vertex AI REST request JSON without launching"
	@echo "  make vertex-finetune-launch   Submit Vertex AI tuning job after cost acknowledgment"
	@echo "  make vertex-finetune-status   Fetch latest Vertex AI tuning job status"
	@echo "  make vertex-finetune-eval     Compare base Gemini and tuned endpoint on Coach prompts"
	@echo "  make vertex-finetune-cancel   Cancel latest Vertex AI tuning job"
	@echo "  make progression-train Train and evaluate supervised next-set progression model"
	@echo "  make scientific-check Run data checks, regression tests, and research summary generation"
	@echo "  make synthetic      Generate six-month synthetic occupancy extension"
	@echo "  make future         Generate seven-day future forecast"
	@echo "  make weather        Fetch future weather feature cache"
	@echo "  make weather-observed Fetch observation-period weather cache"
	@echo "  make weather-ablation Run weather/no-weather experiment"
	@echo "  make sequence       Run compact neural sequence experiment"
	@echo "  make deep           Run PyTorch LSTM and Transformer forecasting experiments"
	@echo "  make sarimax        Run SARIMAX exogenous forecasting experiment"
	@echo "  make synthetic-experiment Compare real-only vs real+synthetic training"
	@echo "  make registry       Build unified model registry table"
	@echo "  make baseline       Run baseline forecasting backtest"
	@echo "  make train          Run extended ML experiments"
	@echo "  make ablation       Run feature ablation experiment"
	@echo "  make figures        Generate thesis-ready figures"
	@echo "  make validate       Validate project business rules"
	@echo "  make test           Run regression tests for API rules and personalization"
	@echo "  make smoke          Run API smoke test"
	@echo "  make exercise-source Build external exercise API preview JSON"
	@echo "  make exercise-import Import the reviewed exercise preview JSON into the local database"
	@echo "  make reset-demo     Reset local demo database state and reseed demo records"
	@echo "  make api            Start FastAPI dev server"
	@echo "  make web            Start Vite dev server"
	@echo "  make build          Build frontend"
	@echo "  make db-shell       Open PostgreSQL shell inside Docker"
	@echo "  make docker-smoke   Verify running Docker Compose stack"
	@echo "  make docker-config  Validate Docker Compose config"
	@echo "  make docker-build   Build Docker images"
	@echo "  make docker-up      Start Docker Compose stack with live logs"
	@echo "  make docker-up-d    Start Docker Compose stack in background"
	@echo "  make docker-rebuild Rebuild and start Docker Compose stack"
	@echo "  make docker-down    Stop Docker Compose stack"
	@echo "  make clean          Remove generated caches"

setup:
	$(PIP) install -r requirements.txt
	cd $(WEB_DIR) && npm.cmd install

torch-setup:
	$(PIP) install -r requirements-torch.txt

doctor:
	$(PYTHON) scripts/doctor.py

data:
	$(PYTHON) scripts/prepare_data.py

test-data:
	$(PYTHON) scripts/test_data_preparation.py

research-summary:
	$(PYTHON) scripts/build_research_summary.py

rag-eval:
	$(PYTHON) scripts/evaluate_rag_retrieval.py

media-coverage:
	$(PYTHON) scripts/check_exercise_media_coverage.py

exercise-open-media:
	$(PYTHON) scripts/import_free_exercise_db_media.py

finetune-dataset:
	$(PYTHON) scripts/build_finetuning_dataset.py

finetune-eval:
	$(PYTHON) scripts/evaluate_coach_tuning_dataset.py

vertex-finetune-template:
	$(PYTHON) scripts/prepare_vertex_finetuning_job.py

vertex-finetune-request:
	$(PYTHON) scripts/launch_vertex_tuning_job.py

vertex-finetune-launch:
	$(PYTHON) scripts/launch_vertex_tuning_job.py --submit --acknowledge-cost

vertex-finetune-status:
	$(PYTHON) scripts/manage_vertex_tuning_job.py get

vertex-finetune-eval:
	$(PYTHON) scripts/evaluate_vertex_tuned_coach.py

vertex-finetune-cancel:
	$(PYTHON) scripts/manage_vertex_tuning_job.py cancel

progression-train:
	$(PYTHON) scripts/train_progression_model.py

scientific-check:
	$(PYTHON) scripts/test_data_preparation.py
	$(PYTHON) scripts/run_regression_tests.py
	$(PYTHON) scripts/build_research_summary.py
	$(PYTHON) scripts/evaluate_rag_retrieval.py

synthetic:
	$(PYTHON) scripts/generate_synthetic_occupancy.py

future:
	$(PYTHON) scripts/generate_future_forecast.py

weather:
	$(PYTHON) scripts/fetch_weather_features.py

weather-observed:
	$(PYTHON) scripts/fetch_weather_features.py observations

weather-ablation:
	$(PYTHON) scripts/run_weather_ablation.py

sequence:
	$(PYTHON) scripts/run_sequence_neural_experiment.py

deep:
	$(PYTHON) scripts/run_deep_forecasting_experiments.py

sarimax:
	$(PYTHON) scripts/run_sarimax_experiment.py

synthetic-experiment:
	$(PYTHON) scripts/run_synthetic_training_experiment.py

registry:
	$(PYTHON) scripts/build_model_registry.py

baseline:
	$(PYTHON) scripts/run_baseline_backtest.py

train:
	$(PYTHON) scripts/run_ml_experiments.py

ablation:
	$(PYTHON) scripts/run_feature_ablation.py

figures:
	$(PYTHON) scripts/generate_thesis_figures.py

validate:
	$(PYTHON) scripts/validate_business_rules.py

test:
	$(PYTHON) scripts/run_regression_tests.py

smoke:
	$(PYTHON) scripts/api_smoke_test.py

exercise-source:
	$(PYTHON) scripts/import_exercise_source.py $(EXERCISE_SOURCE_ARGS)

exercise-import:
	$(PYTHON) scripts/import_exercise_preview.py $(EXERCISE_IMPORT_ARGS)

reset-demo:
	$(PYTHON) scripts/reset_demo_state.py

api:
	$(PYTHON) -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000 --reload

web:
	cd $(WEB_DIR) && npm.cmd run dev -- --host 127.0.0.1 --port 5173

build:
	cd $(WEB_DIR) && npm.cmd run build

db-shell:
	docker-compose exec db psql -U gymflow -d gymflow

docker-smoke:
	$(PYTHON) scripts/docker_smoke_test.py

docker-config:
	docker-compose config

docker-build:
	docker-compose build

docker-up:
	docker-compose up

docker-up-d:
	docker-compose up -d

docker-rebuild:
	docker-compose up --build

docker-down:
	docker-compose down

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; shutil.rmtree('.pytest_cache', ignore_errors=True)"
