"""
queue/scheduler.py — Humanized response delay scheduler
"""
import asyncio
import logging
import random
from typing import Callable, Coroutine
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler():
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("APScheduler started")


def stop_scheduler():
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)


def schedule_reply(
    coroutine_fn,
    delay_min: int,
    delay_max: int,
    **kwargs,
):
    """
    Schedule an async reply to fire after a random delay
    between delay_min and delay_max seconds.
    This makes the bot feel like a real person "typing and thinking."
    """
    delay_seconds = random.randint(delay_min, delay_max)
    run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

    sched = get_scheduler()

    async def _job():
        try:
            await coroutine_fn(**kwargs)
        except Exception as e:
            logger.error(f"Scheduled reply job failed: {e}")

    sched.add_job(
        _job,
        trigger="date",
        run_date=run_at,
        misfire_grace_time=60,
    )
    logger.info(f"Reply scheduled in {delay_seconds}s (at {run_at.isoformat()})")
    return delay_seconds
