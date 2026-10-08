"""Bảng STUDENTS, TUITIONS theo ERD v3 (docs/diagrams/erd-v3.png).
Quan hệ: một sinh viên có tối đa một khoản học phí (tuitions.student_id là UNIQUE)."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)


class Tuition(Base):
    __tablename__ = "tuitions"
    __table_args__ = (
        CheckConstraint("status IN ('UNPAID','RESERVED','PAID')", name="ck_tuitions_status"),
        CheckConstraint("amount > 0", name="ck_tuitions_amount"),
        # Đang RESERVED thì phải biết giao dịch nào giữ chỗ.
        CheckConstraint("status <> 'RESERVED' OR reserved_by IS NOT NULL", name="ck_tuitions_reserved_by"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), unique=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="UNPAID")
    # id giao dịch (bên payment_db) đang giữ chỗ hoặc đã thanh toán; khóa ngoại logic, không ràng buộc ở DB.
    reserved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
