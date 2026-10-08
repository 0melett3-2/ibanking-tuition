"""Xác thực dùng chung.
- JWT người dùng (HS256, secret chung): Authorization: Bearer <jwt>
- Khóa nội bộ giữa service: X-Internal-Key
Dùng làm dependency: Depends(get_current_user) hoặc Depends(require_internal_key).
"""
import hmac
import os
import time

import jwt
from fastapi import Header
from pydantic import BaseModel

from .errors import AppError

ALGORITHM = "HS256"


class CurrentUser(BaseModel):
    id: int
    username: str


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: int, username: str) -> tuple[str, int]:
    """Trả về (token, expires_in_giây). Chỉ User service gọi hàm này."""
    seconds = int(os.getenv("JWT_EXPIRES_MINUTES", "60")) * 60
    now = int(time.time())
    payload = {"sub": str(user_id), "username": username, "iat": now, "exp": now + seconds}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), seconds


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    unauthorized = AppError(401, "UNAUTHORIZED", "Phiên đăng nhập không hợp lệ hoặc đã hết hạn")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized
    token = authorization[7:].strip()
    try:
        data = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
        return CurrentUser(id=int(data["sub"]), username=data.get("username", ""))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    expected = os.environ["INTERNAL_API_KEY"]
    if not x_internal_key or not hmac.compare_digest(x_internal_key, expected):
        raise AppError(401, "UNAUTHORIZED", "Thiếu hoặc sai khóa gọi nội bộ")
