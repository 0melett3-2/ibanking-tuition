from contextlib import asynccontextmanager

from fastapi import FastAPI

from ibanking_common.errors import register_error_handlers

from .database import SessionLocal, init_db
from .routers import tuitions
from .seed import seed_missing


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_missing(db)
    yield


app = FastAPI(title="Tuition service", version="1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(tuitions.router)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}
