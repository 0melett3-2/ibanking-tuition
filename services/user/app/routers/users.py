from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ibanking_common.errors import AppError, ErrorResponse
from ibanking_common.security import CurrentUser, get_current_user, require_internal_key

from ..database import get_db
from ..models import User
from ..schemas import UserOut

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserOut, responses={401: {"model": ErrorResponse}})
def get_me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, current.id)
    if user is None:  # token hợp lệ nhưng người dùng đã bị xóa
        raise AppError(401, "UNAUTHORIZED", "Phiên đăng nhập không hợp lệ hoặc đã hết hạn")
    return user


@router.get("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_internal_key)],
            responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Nội bộ: Payment dùng để lấy email người nộp tiền."""
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng")
    return user
