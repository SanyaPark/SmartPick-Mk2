from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.backend.api.routes.agent import router as agent_router


def get_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ALLOW_ORIGINS")
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="SmartPick API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(agent_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("apps.backend.main:app", host="0.0.0.0", port=8000, reload=True)
