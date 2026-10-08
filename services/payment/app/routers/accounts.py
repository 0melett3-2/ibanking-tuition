from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ibanking_common.errors import AppError, ErrorResponse
from ibanking_common.security import CurrentUser, get_current_user

from ..database import get_db
from ..models import Account
from ..schemas import AccountOut

router = APIRouter(tags=["accounts"])


@router.get("/accounts/me", response_model=AccountOut,
            responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
def get_my_account(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.scalar(select(Account).where(Account.user_id == user.id))
    if account is None:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Chưa có tài khoản thanh toán")
    return AccountOut(account_id=account.id, user_id=account.user_id, balance=account.balance)
