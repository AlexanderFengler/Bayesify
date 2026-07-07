"""Static UI mounting for the single-process deployment."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


class SPAStaticFiles(StaticFiles):
    """Serve the built SPA and fall back to index.html for client-side routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api"):
                return await super().get_response("index.html", scope)
            raise


def mount_web_ui(app: FastAPI) -> None:
    default_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    web_dist = Path(os.environ.get("BAYESIFY_WEB_DIST", str(default_dist)))
    if web_dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(web_dist), html=True), name="web")
        return

    @app.get("/", include_in_schema=False)
    async def api_root() -> dict[str, str]:
        return {
            "service": "Bayesify API",
            "status": "ok",
            "health": "/healthz",
            "docs": "/docs",
        }
