"""SSE event streaming for jobs."""

from __future__ import annotations

import asyncio
import json

from bayesify.api.jobs.model import TERMINAL_EVENTS, Job


async def event_stream(job: Job):
    queue = asyncio.Queue()
    job.subscribers.add(queue)
    try:
        replayed_through = 0
        for event in list(job.events):
            replayed_through = event["seq"]
            yield {"data": dump_event(event)}
            if event["type"] in TERMINAL_EVENTS:
                return

        while True:
            event = await queue.get()
            if event["seq"] <= replayed_through:
                continue
            yield {"data": dump_event(event)}
            if event["type"] in TERMINAL_EVENTS:
                return
    finally:
        job.subscribers.discard(queue)


def dump_event(event: dict) -> str:
    return json.dumps(event)
