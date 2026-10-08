"""Bốn bảng của payment_db theo ERD v3 (docs/diagrams/erd-v3.png), gồm các ràng buộc quan trọng:
- CHECK balance >= 0 và các CHECK trạng thái;
- unique index MỘT PHẦN: một học phí chỉ có một giao dịch DEBITED/SUCCESS, không có hai giao dịch PENDING
  giống nhau (bấm đúp), mỗi giao dịch một OTP ACTIVE, không có hai OTP ACTIVE trùng mã băm."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_accounts_balance"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # khóa ngoại logic sang user_db (khác database nên không có ràng buộc ở DB)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','DEBITED','SUCCESS','FAILED','EXPIRED')", name="ck_transactions_status"),
        CheckConstraint("amount > 0", name="ck_transactions_amount"),
        Index("uq_transactions_tuition_paid", "tuition_id", unique=True,
              postgresql_where=text("status IN ('DEBITED','SUCCESS')")),
        Index("uq_transactions_pending", "account_id", "tuition_id", unique=True,
              postgresql_where=text("status = 'PENDING'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    tuition_id: Mapped[int] = mapped_column(Integer, nullable=False)  # khóa ngoại logic sang tuition_db
    student_code: Mapped[str] = mapped_column(String(20), nullable=False)   # snapshot để hiển thị lịch sử, email
    student_name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PENDING")
    fail_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Otp(Base):
    __tablename__ = "otps"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','USED','REVOKED','EXPIRED')", name="ck_otps_status"),
        Index("uq_otps_code_active", "code_hash", unique=True, postgresql_where=text("status = 'ACTIVE'")),
        Index("uq_otps_transaction_active", "transaction_id", unique=True, postgresql_where=text("status = 'ACTIVE'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # HMAC-SHA256, không lưu OTP gốc
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ACTIVE")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmailLog(Base):
    __tablename__ = "email_logs"
    __table_args__ = (
        CheckConstraint("email_type IN ('OTP','CONFIRMATION')", name="ck_email_logs_type"),
        CheckConstraint("status IN ('PENDING','SENT','FAILED')", name="ck_email_logs_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    email_type: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
