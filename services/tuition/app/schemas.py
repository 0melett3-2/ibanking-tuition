from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TuitionStatus = Literal["UNPAID", "RESERVED", "PAID"]


class TransactionRef(BaseModel):
    transaction_id: int = Field(gt=0)


class TuitionLookup(BaseModel):
    tuition_id: int
    student_code: str
    student_name: str
    amount: Decimal
    status: TuitionStatus


class TuitionDetail(TuitionLookup):
    reserved_by: int | None = None


class ReservationOut(BaseModel):
    tuition_id: int
    status: TuitionStatus
    reserved_by: int
    reserved_at: datetime


class PaymentOut(BaseModel):
    tuition_id: int
    status: TuitionStatus
    paid_at: datetime
