"""Shared API runtime state.

FastAPI does not require route handlers, app construction, and process resources to live in one
module. The singleton here owns the small amount of mutable process state the transport layer needs:
the FastAPI app reference, logger, and in-memory job store.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from logging import Logger

from fastapi import FastAPI

from bayesify.api.env import load_env_file
from bayesify.api.jobs.model import JobStore
from bayesify.api.logging import app_logger
from bayesify.api.mongo import start_mongodb, stop_mongodb


@dataclass
class BayesifyAPI:
    logger: Logger = field(default_factory=app_logger)
    store: JobStore = field(default_factory=JobStore)
    app: FastAPI | None = None

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        self.app = app
        env = load_env_file()
        if env.keys:
            self.logger.info(
                f"Loaded {len(env.keys)} setting(s) from {env.path}: {', '.join(env.keys)}"
            )
        mongo_status = await asyncio.to_thread(start_mongodb)
        detail = (
            f"MongoDB status: {mongo_status.message}; "
            f"uri={mongo_status.uri}; db={mongo_status.database}; mode={mongo_status.mode}"
        )
        if mongo_status.server_api:
            detail += f"; server_api=v{mongo_status.server_api}"
        if mongo_status.autostart:
            detail += "; local_autostart=enabled"
        if mongo_status.ready:
            self.logger.info(detail)
        else:
            self.logger.warning(detail)
        try:
            yield
        finally:
            await asyncio.to_thread(stop_mongodb)


api = BayesifyAPI()
