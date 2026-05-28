from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_database
from .routes import router


def create_app() -> FastAPI:
    # Keep framework wiring separate from domain routes so the API can grow by modules.
    app = FastAPI(title="GymFlow AI API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()


@app.on_event("startup")
def startup() -> None:
    # Startup owns schema backfills and deterministic demo seed data for local thesis runs.
    init_database()
