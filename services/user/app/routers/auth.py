from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ibanking_common.errors import AppError, ErrorResponse
from ibanking_common.security import create_access_token

from ..database import get_db
from ..models import User
from ..passwords import verify_password
from ..schemas import LoginRequest, TokenResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse,
             responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    # Luôn kiểm tra mật khẩu (kể cả khi không có user) và dùng cùng một thông báo,
    # để không lộ username nào tồn tại.
    if not verify_password(body.password, user.password_hash if user else None) or user is None:
        raise AppError(401, "INVALID_CREDENTIALS", "Tên đăng nhập hoặc mật khẩu không đúng")
    token, expires_in = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token, expires_in=expires_in)
