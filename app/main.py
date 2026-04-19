import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine
from app.routers import prices, products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    yield
    logger.info("Shutting down")
    await engine.dispose()


app = FastAPI(title="Price Tracker", lifespan=lifespan)

app.include_router(products.router)
app.include_router(prices.router)
