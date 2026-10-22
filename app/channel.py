"""Saqlash kanaliga yozishni navbatga qo'yadi.

Telegram bitta chatga daqiqasiga ~20 xabar yuborishga ruxsat beradi (aks holda "Flood control exceeded").
Bu modul kanalga yozishlar orasida kamida MIN_GAP soniya tanaffus qoladi va Telegram
"retry after N" desa, shuncha kutib qayta urinadi.
"""
import asyncio
import logging
import time
from typing import Awaitable, Callable, TypeVar

from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

log = logging.getLogger(__name__)

MIN_GAP = 3.2  # soniya: ~18 xabar/daqiqa — chegaradan pastda
MAX_RETRIES = 5

T = TypeVar("T")
_lock = asyncio.Lock()
_next_at = 0.0
_waiting = 0
_background: set[asyncio.Task] = set()


def waiting() -> int:
    """Navbatda (kutayotgan va bajarilayotgan) so'rovlar soni."""
    return _waiting


async def call(factory: Callable[[], Awaitable[T]]) -> T:
    """factory() ni navbat bilan, tezlik cheklovi va qayta urinish bilan bajaradi."""
    global _next_at, _waiting
    _waiting += 1
    try:
        async with _lock:
            for attempt in range(MAX_RETRIES + 1):
                delay = _next_at - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    return await factory()
                except TelegramRetryAfter as e:
                    _next_at = time.monotonic() + e.retry_after + 1
                    log.warning("Flood control: %s soniya kutaman (urinish %s/%s)", e.retry_after, attempt + 1, MAX_RETRIES)
                    if attempt == MAX_RETRIES:
                        raise
                finally:
                    _next_at = max(_next_at, time.monotonic() + MIN_GAP)
    finally:
        _waiting -= 1


def spawn(coro: Awaitable) -> None:
    """Javobni kutmasdan fonda bajaradi (xatolar jurnalga yoziladi)."""

    async def runner():
        try:
            await coro
        except TelegramAPIError as e:
            log.warning("Kanalga fon yozuvi bajarilmadi: %s", e)
        except Exception:
            log.exception("Kanalga fon yozuvida kutilmagan xato")

    task = asyncio.create_task(runner())
    _background.add(task)
    task.add_done_callback(_background.discard)
