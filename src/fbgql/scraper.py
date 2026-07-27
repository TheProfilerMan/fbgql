"""The Scraper facade — one entry point over both engines."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterator

from . import runner
from .engine import base, get_engine
from .models import PostResult, Result, ScrapeJob


class Scraper:
    """Run a :class:`ScrapeJob`. Selects the engine from ``job.engine``."""

    def run(self, job: ScrapeJob, on_post: Callable[[PostResult], None] | None = None) -> Result:
        plan = runner.prepare(job)
        engine = get_engine(job.engine)
        if on_post is None:
            return engine.run(plan)
        # Stream so a caller (e.g. the CLI) can report per-post progress, then roll
        # the same per-post results up through the shared aggregation path.
        t0 = time.perf_counter()
        results: list[PostResult] = []
        for result in engine.stream(plan):
            results.append(result)
            on_post(result)
        return base.assemble_result(job, plan, results, time.perf_counter() - t0)

    def stream(self, job: ScrapeJob) -> Iterator[PostResult]:
        """Yield each post result as it completes (native for engine='threads')."""
        plan = runner.prepare(job)
        yield from get_engine(job.engine).stream(plan)

    async def astream(self, job: ScrapeJob) -> AsyncIterator[PostResult]:
        """Async streaming — the natural path for the Apify actor.

        Post discovery (blocking HTTP) is offloaded to a thread so it doesn't stall
        the event loop. Works with either engine; true concurrency needs engine='async'.
        """
        plan = await asyncio.to_thread(runner.prepare, job)
        engine = get_engine(job.engine)
        astream = getattr(engine, "astream", None)
        if astream is not None:
            async for item in astream(plan):
                yield item
        else:
            for item in engine.stream(plan):
                yield item
