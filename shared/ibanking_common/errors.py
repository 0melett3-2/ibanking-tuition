"""Định dạng lỗi chung theo hợp đồng REST API (mục 1):
{ "error": { "code": "...", "message": "...", "details": {} } }
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("ibanking")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    """Dùng cho responses={...} để Swagger hiển thị đúng định dạng lỗi."""
    error: ErrorBody


class AppError(Exception):
    """Ném lỗi nghiệp vụ: raise AppError(409, "TUITION_NOT_AVAILABLE", "Học phí đã được thanh toán")."""

    def __init__(self, status_code: int, code: str, message: str,
                 details: dict | None = None, headers: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def not_implemented(todo: str) -> AppError:
    return AppError(501, "NOT_IMPLEMENTED", todo)


def error_response(status_code: int, code: str, message: str,
                   details: dict | None = None, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path")),
             "message": e["msg"]}
            for e in exc.errors()
        ]
        return error_response(422, "VALIDATION_ERROR", "Dữ liệu không hợp lệ", {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, f"HTTP_{exc.status_code}")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Lỗi không xử lý: %s %s", request.method, request.url.path)
        return error_response(500, "INTERNAL_ERROR", "Lỗi hệ thống")
