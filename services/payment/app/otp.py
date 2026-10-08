"""OTP: sinh mã 6 chữ số và băm bằng HMAC-SHA256 (secret của server).
Dùng HMAC thay vì SHA-256 thường vì OTP chỉ có 1 triệu khả năng (dò ngược gần như tức thì),
nhưng vẫn cần kết quả xác định để kiểm tra "không trùng OTP ACTIVE" bằng unique index."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .config import settings


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hmac.new(settings.otp_hmac_secret.encode(), code.encode(), hashlib.sha256).hexdigest()  # 64 ký tự


def new_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=settings.otp_ttl_seconds)
