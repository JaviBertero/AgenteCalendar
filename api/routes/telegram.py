import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, verify_telegram_secret
from database.connection import async_session_factory
from telegram.schemas import TelegramUpdate
from telegram.webhook import WebhookHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


async def _process_update(update: TelegramUpdate) -> None:
    async with async_session_factory() as session:
        try:
            handler = WebhookHandler(session)
            await handler.handle_update(update)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to process telegram update %s", update.update_id)


@router.post("/webhook", dependencies=[Depends(verify_telegram_secret)])
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    _session: AsyncSession = Depends(get_db_session),
):
    body = await request.json()
    update = TelegramUpdate.model_validate(body)
    background_tasks.add_task(_process_update, update)
    return {"ok": True}
