import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import engine, get_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(lifespan=lifespan)



@app.get("/health")
async def health(db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        result = await db.execute(text("SELECT 1"))
        for r in result:
            logger.debug(r)

        return JSONResponse(status_code=200, content={"status": "ok"})
    except (SQLAlchemyError, OSError):
        logger.exception("Database Health Check. Server Unreachable")
        return JSONResponse(status_code=503, content={"status": "Unavailable"})
    

