from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ibanking_common.errors import AppError, ErrorResponse
from ibanking_common.security import CurrentUser, get_current_user, require_internal_key

from ..database import get_db
from ..models import Student, Tuition
from ..schemas import PaymentOut, ReservationOut, TransactionRef, TuitionDetail, TuitionLookup

router = APIRouter(tags=["tuition"])
ERR = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}
internal = [Depends(require_internal_key)]


def _not_found() -> AppError:
    return AppError(404, "TUITION_NOT_FOUND", "Không tìm thấy khoản học phí")


def _load(db: Session, tuition_id: int) -> tuple[Student, Tuition]:
    """Đọc mới từ DB (không dùng cache của session) để thấy đúng trạng thái sau các UPDATE có điều kiện."""
    row = db.execute(
        select(Student, Tuition).join(Tuition, Tuition.student_id == Student.id).where(Tuition.id == tuition_id)
    ).first()
    if row is None:
        raise _not_found()
    return row[0], row[1]


@router.get("/students/{mssv}/tuition", response_model=TuitionLookup, responses=ERR)
def lookup_by_mssv(mssv: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # Học phí PAID/RESERVED vẫn trả 200 kèm status (không dùng 409).
    student = db.scalar(select(Student).where(Student.student_code == mssv))
    if student is None:
        raise AppError(404, "STUDENT_NOT_FOUND", "MSSV không hợp lệ")
    tuition = db.scalar(select(Tuition).where(Tuition.student_id == student.id))
    if tuition is None:
        raise _not_found()
    return TuitionLookup(tuition_id=tuition.id, student_code=student.student_code,
                         student_name=student.full_name, amount=tuition.amount, status=tuition.status)


@router.get("/tuitions/{tuition_id}", response_model=TuitionDetail, dependencies=internal, responses=ERR)
def get_tuition(tuition_id: int, db: Session = Depends(get_db)):
    student, tuition = _load(db, tuition_id)
    return TuitionDetail(tuition_id=tuition.id, student_code=student.student_code,
                         student_name=student.full_name, amount=tuition.amount,
                         status=tuition.status, reserved_by=tuition.reserved_by)


@router.post("/tuitions/{tuition_id}/reservation", response_model=ReservationOut, dependencies=internal,
             responses=ERR)
def reserve(tuition_id: int, body: TransactionRef, db: Session = Depends(get_db)):
    # Một câu UPDATE có điều kiện là toàn bộ cơ chế chống tranh chấp (Seq 3): PostgreSQL khóa dòng cho câu
    # đến trước; câu đến sau chờ, rồi đánh giá lại WHERE trên dòng đã đổi nên không khớp -> 0 dòng.
    row = db.execute(
        update(Tuition)
        .where(Tuition.id == tuition_id, Tuition.status == "UNPAID")
        .values(status="RESERVED", reserved_by=body.transaction_id, reserved_at=func.now())
        .execution_options(synchronize_session=False)
        .returning(Tuition.reserved_at)
    ).first()
    if row is not None:
        db.commit()
        return ReservationOut(tuition_id=tuition_id, status="RESERVED",
                              reserved_by=body.transaction_id, reserved_at=row[0])
    db.rollback()
    _, tuition = _load(db, tuition_id)  # 404 nếu không tồn tại
    if tuition.status == "RESERVED" and tuition.reserved_by == body.transaction_id:  # gọi lại: idempotent
        return ReservationOut(tuition_id=tuition_id, status="RESERVED",
                              reserved_by=tuition.reserved_by, reserved_at=tuition.reserved_at)
    raise AppError(409, "TUITION_NOT_AVAILABLE", "Học phí đã được thanh toán hoặc đang được xử lý")


@router.delete("/tuitions/{tuition_id}/reservation", status_code=204, dependencies=internal, responses=ERR)
def release(tuition_id: int, transaction_id: int = Query(gt=0), db: Session = Depends(get_db)):
    # Chỉ nhả chỗ do chính giao dịch này giữ; không bao giờ nhả chỗ của giao dịch khác.
    row = db.execute(
        update(Tuition)
        .where(Tuition.id == tuition_id, Tuition.status == "RESERVED", Tuition.reserved_by == transaction_id)
        .values(status="UNPAID", reserved_by=None, reserved_at=None)
        .execution_options(synchronize_session=False)
        .returning(Tuition.id)
    ).first()
    db.commit()
    if row is None:  # không có gì để nhả: kiểm tra học phí có tồn tại / đã PAID không
        _, tuition = _load(db, tuition_id)
        if tuition.status == "PAID":
            raise AppError(409, "TUITION_ALREADY_PAID", "Học phí đã được thanh toán")
    return Response(status_code=204)


@router.post("/tuitions/{tuition_id}/payment", response_model=PaymentOut, dependencies=internal, responses=ERR)
def confirm_payment(tuition_id: int, body: TransactionRef, db: Session = Depends(get_db)):
    row = db.execute(
        update(Tuition)
        .where(Tuition.id == tuition_id, Tuition.status == "RESERVED", Tuition.reserved_by == body.transaction_id)
        .values(status="PAID", paid_at=func.now())
        .execution_options(synchronize_session=False)
        .returning(Tuition.paid_at)
    ).first()
    if row is not None:
        db.commit()
        return PaymentOut(tuition_id=tuition_id, status="PAID", paid_at=row[0])
    db.rollback()
    _, tuition = _load(db, tuition_id)  # 404 nếu không tồn tại
    # reserved_by được giữ lại khi PAID để lần gọi lại (job đối soát thử lại) vẫn nhận ra đúng giao dịch.
    if tuition.status == "PAID" and tuition.reserved_by == body.transaction_id:
        return PaymentOut(tuition_id=tuition_id, status="PAID", paid_at=tuition.paid_at)
    raise AppError(409, "RESERVATION_MISMATCH", "Học phí không đang được giữ chỗ bởi giao dịch này")
