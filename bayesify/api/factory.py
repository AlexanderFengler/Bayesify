"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bayesify.api.config import API_CONFIG
from bayesify.api.db.mongo import mongo
from bayesify.api.routes import archive, calibration, health, overrides, papers, rating, rubrics
from bayesify.api.runtime import BayesifyAPI, api
from bayesify.api.static import mount_web_ui


def create_app(runtime: BayesifyAPI | None = None) -> FastAPI:
    runtime = runtime or api
    cors = API_CONFIG["cors"]
    app = FastAPI(
        title=API_CONFIG["title"],
        version=API_CONFIG["version"],
        lifespan=runtime.lifespan,
    )
    app.state.runtime = runtime
    app.state.db = mongo

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors["allow_origins"]),
        allow_methods=list(cors["allow_methods"]),
        allow_headers=list(cors["allow_headers"]),
    )

    app.include_router(health.router)
    app.include_router(papers.router)
    app.include_router(rubrics.router)
    app.include_router(overrides.router)
    app.include_router(rating.router)
    app.include_router(calibration.router)
    app.include_router(archive.router)
    mount_web_ui(app)

    runtime.app = app
    return app
