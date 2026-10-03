"""Run the restock reconcile shortly after startup and every few hours.

Started from the app lifespan when the Picnic feature is configured. A run
links new inventory EANs to Picnic products and tops up every rule below
its minimum; see app.services.restock.reconcile_all.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.services.picnic.client import (
    PicnicClientProtocol,
    PicnicNotConfigured,
    PicnicReauthRequired,
    get_picnic_client,
)
from app.services.restock import ReconcileSummary, reconcile_all

log = logging.getLogger("restock.schedule")

STARTUP_DELAY_S = 60
INTERVAL_S = 4 * 60 * 60


async def run_reconcile_once(
    session_factory: Callable[[], AsyncSession] = async_session,
    client_factory: Callable[[], PicnicClientProtocol] = get_picnic_client,
) -> ReconcileSummary | None:
    """One reconcile in its own session. Never raises: a failed run is rolled
    back and logged, the next one retries. EAN links survive a failure:
    reconcile_all commits each one as it goes."""
    async with session_factory() as db:
        try:
            summary = await reconcile_all(db, client_factory())
            await db.commit()
            return summary
        except (PicnicNotConfigured, PicnicReauthRequired) as e:
            log.warning("Scheduled reconcile skipped: %s", type(e).__name__)
        except Exception:
            log.exception("Scheduled reconcile failed")
        try:
            await db.rollback()
        except Exception:
            log.exception("Rollback after failed reconcile failed")
        return None


async def reconcile_forever() -> None:
    await asyncio.sleep(STARTUP_DELAY_S)
    while True:
        try:
            await run_reconcile_once()
        except Exception:  # never let the loop die until the next restart
            log.exception("Scheduled reconcile crashed")
        await asyncio.sleep(INTERVAL_S)
