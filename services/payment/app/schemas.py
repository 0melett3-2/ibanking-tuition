from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TransactionStatus = Literal["PENDING", "DEBITED", "SUCCESS", "FAILED", "EXPIRED"]


class AccountOut(BaseModel):
    account_id: int
    user_id: int
    balance: Decimal


class CreateTransactionRequest(BaseModel):
    tuition_id: int = Field(gt=0)


class TransactionCreated(BaseModel):
    transaction_id: int
    status: TransactionStatus
    amount: Decimal
    student_code: str
    student_name: str
    otp_expires_at: datetime


class TransactionItem(BaseModel):
    transaction_id: int
    student_code: str
    student_name: str
    amount: Decimal
    status: TransactionStatus
    fail_reason: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class TransactionOut(TransactionItem):
    tuition_id: int


class TransactionPage(BaseModel):
    items: list[TransactionItem]
    page: int
    page_size: int
    total: int


class ConfirmRequest(BaseModel):
    otp: str = Field(pattern=r"^\d{6}$")


class ConfirmResult(BaseModel):
    transaction_id: int
    status: TransactionStatus
    amount: Decimal
    completed_at: datetime | None = None


class OtpResent(BaseModel):
    otp_expires_at: datetime
    resends_left: int


class ReconcileResult(BaseModel):
    expired_otps: int = 0
    expired_transactions: int = 0
    interrupted_transactions: int = 0
    retried_confirms: int = 0
    released_reservations: int = 0
    retried_emails: int = 0
