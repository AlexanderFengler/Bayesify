"""Background task supervision for fire-and-forget API work."""

from __future__ import annotations

import asyncio

from bayesify.api.runtime import api

background_tasks: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(on_task_done)
    return task


def on_task_done(task: asyncio.Task) -> None:
    background_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        api.logger.error("background task failed", exc_info=task.exception())
