"""
Annual APScheduler job — fires on January 1 to seed the new tax year.

On trigger:
  1. Seeds tax data for the new year (inflation-adjusted brackets / deductions)
  2. Marks the prior-2 year as "closed" (e.g., on Jan 1 2026 → mark 2023 closed)
  3. Rebuilds the rule engine index (form rules may update)

The scheduler is started from main.py lifespan and shut down cleanly on exit.
"""
from __future__ import annotations

from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = structlog.get_logger("nexus-tax.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _annual_seed_job() -> None:
    """Run on January 1: seed new tax year, close old year."""
    from app.seed import seed_tax_data
    from app.engine import reset_rule_engine
    from app.database import get_db
    from app.models import TaxPeriodModel
    from sqlalchemy import update

    new_year = datetime.now().year - 1   # most recent completed year
    close_year = new_year - 2            # close the year two back

    logger.info("Annual tax seed job firing", new_year=new_year, close_year=close_year)

    try:
        await seed_tax_data(new_year)
        logger.info("Tax year seeded", year=new_year)

        # Mark close_year as closed
        async with get_db() as db:
            await db.execute(
                update(TaxPeriodModel)
                .where(TaxPeriodModel.tax_year == close_year)
                .values(status="closed")
            )
        logger.info("Tax year closed", year=close_year)

        # Rebuild rule engine so any new rules are picked up
        reset_rule_engine()
        logger.info("Rule engine reset after annual seed")
    except Exception as exc:
        logger.error("Annual seed job failed", error=str(exc))


def init_scheduler() -> AsyncIOScheduler:
    """
    Create and start the APScheduler.
    Returns the scheduler so the caller can shut it down on app teardown.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _annual_seed_job,
        trigger=CronTrigger(month=1, day=1, hour=0, minute=5),  # 00:05 UTC Jan 1
        id="annual_tax_seed",
        name="Seed new tax year and close old year",
        replace_existing=True,
        misfire_grace_time=3600,  # allow 1-hour grace for missed fires
    )
    _scheduler.start()
    logger.info("Tax scheduler started (annual seed on Jan 1)")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Tax scheduler stopped")
