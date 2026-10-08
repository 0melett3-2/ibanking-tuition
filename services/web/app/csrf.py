"""CSRF kiểu double-submit: cấp token ký, đặt vào cookie và vào input ẩn của form/header HTMX;
khi nhận POST thì so hai giá trị và kiểm tra chữ ký. Cookie phiên dùng SameSite=Lax."""
import hmac
import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import settings

_ser = URLSafeTimedSerializer(settings.secret_key, salt="csrf")


def issue() -> str:
    return _ser.dumps(secrets.token_hex(16))


def verify(cookie_value: str | None, submitted_value: str | None, max_age: int = 3600) -> bool:
    if not cookie_value or not submitted_value or not hmac.compare_digest(cookie_value, submitted_value):
        return False
    try:
        _ser.loads(cookie_value, max_age=max_age)
        return True
    except BadSignature:
        return False
