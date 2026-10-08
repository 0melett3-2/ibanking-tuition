"""Băm và kiểm tra mật khẩu bằng bcrypt."""
import bcrypt

_MAX_BYTES = 72  # bcrypt chỉ dùng 72 byte đầu; bản mới từ chối chuỗi dài hơn
# Băm giả để mất thời gian kiểm tra như nhau khi username không tồn tại (tránh lộ username qua thời gian phản hồi).
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:_MAX_BYTES], bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    raw = password.encode()
    if len(raw) > _MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, (password_hash or _DUMMY_HASH).encode()) and password_hash is not None
    except ValueError:
        return False
