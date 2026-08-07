import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes.auth import router as auth_router
from api.routes.health import router as health_router
from api.routes.telegram import router as telegram_router
from config.settings import settings
from database.connection import init_db

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)
    await init_db()
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Agente de IA para gestionar Google Calendar vía Telegram",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(telegram_router)
app.include_router(auth_router)
