"""Gọi các service từ Web/BFF, gắn JWT lấy từ cookie. Tách riêng để route không lặp lại logic gọi HTTP."""
from typing import Any
import httpx

from .config import settings

TIMEOUT = httpx.Timeout(8.0)


async def call(method: str, base: str, path: str, token: str | None = None, **kw: Any) -> httpx.Response:
    req_headers = dict(kw.pop("headers", None) or {})
    if token:
        req_headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(base_url=base, headers=req_headers, timeout=TIMEOUT) as c:
        return await c.request(method, path, **kw)
