"""Gọi User và Tuition service (kèm X-Internal-Key, timeout 3 giây, không tự thử lại trong request).
Lỗi mạng/timeout -> AppError(503, "DEPENDENCY_UNAVAILABLE"); nơi gọi tự đổi mã nếu cần
(ví dụ khi giữ chỗ lỗi dùng "TUITION_SERVICE_ERROR"). Mã HTTP khác (404, 409, ...) trả nguyên Response."""
import httpx

from ibanking_common.errors import AppError

from .config import settings

_HEADERS = {"X-Internal-Key": settings.internal_api_key}


def _call(method: str, base: str, path: str, **kw) -> httpx.Response:
    try:
        with httpx.Client(base_url=base, headers=_HEADERS, timeout=settings.http_timeout_seconds) as c:
            return c.request(method, path, **kw)
    except httpx.TransportError as exc:  # gồm timeout, connect error
        raise AppError(503, "DEPENDENCY_UNAVAILABLE", "Hệ thống đang bận, vui lòng thử lại") from exc


def get_user(user_id: int) -> httpx.Response:
    return _call("GET", settings.user_service_url, f"/users/{user_id}")


def get_tuition(tuition_id: int) -> httpx.Response:
    return _call("GET", settings.tuition_service_url, f"/tuitions/{tuition_id}")


def reserve_tuition(tuition_id: int, transaction_id: int) -> httpx.Response:
    return _call("POST", settings.tuition_service_url, f"/tuitions/{tuition_id}/reservation",
                 json={"transaction_id": transaction_id})


def release_tuition(tuition_id: int, transaction_id: int) -> httpx.Response:
    return _call("DELETE", settings.tuition_service_url, f"/tuitions/{tuition_id}/reservation",
                 params={"transaction_id": transaction_id})


def confirm_tuition_payment(tuition_id: int, transaction_id: int) -> httpx.Response:
    return _call("POST", settings.tuition_service_url, f"/tuitions/{tuition_id}/payment",
                 json={"transaction_id": transaction_id})
