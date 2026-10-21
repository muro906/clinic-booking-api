from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from typing import Annotated
from .database import engine, get_db
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import logging

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
    except (SQLAlchemyError, OSError) as e:
        logger.exception(e)
        return JSONResponse(status_code=503, content={"status": "Unavailable"})
    

