import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ibanking_common.errors import register_error_handlers

from .config import settings
from .database import SessionLocal, init_db
from .jobs import reconcile_loop
from .routers import accounts, internal, transactions
from .seed import seed_missing


# Log của ứng dụng (các logger 'ibanking.*'): mặc định chỉ hiện cảnh báo, nên bật mức INFO để thấy job làm gì.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_missing(db)
    task = asyncio.create_task(reconcile_loop(settings.reconcile_interval_seconds))
    yield
    task.cancel()


app = FastAPI(title="Payment service", version="1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(internal.router)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}
