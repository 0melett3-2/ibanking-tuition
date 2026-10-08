import logging
from math import ceil
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import extract, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ibanking_common.errors import AppError, ErrorResponse, not_implemented
from ibanking_common.security import CurrentUser, get_current_user

from .. import clients, otp
from ..config import settings
from ..database import get_db
from ..email_service import send_confirmation_email, send_otp_email
from ..models import Account, EmailLog, Otp, Transaction
from ..schemas import (ConfirmRequest, ConfirmResult, CreateTransactionRequest, OtpResent,
                       TransactionCreated, TransactionItem, TransactionOut, TransactionPage)

log = logging.getLogger("ibanking.payment")
router = APIRouter(tags=["transactions"])
E = {c: {"model": ErrorResponse} for c in (400, 401, 404, 409, 422, 429, 503)}


def _read(resp, name: str, not_found: AppError | None = None) -> dict:
    """Đọc phản hồi từ service khác: 200 -> dữ liệu; 404 -> lỗi nghiệp vụ nếu có; còn lại -> 503."""
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404 and not_found is not None:
        raise not_found
    log.error("%s trả về %s: %s", name, resp.status_code, resp.text[:200])
    raise AppError(503, "DEPENDENCY_UNAVAILABLE", "Hệ thống đang bận, vui lòng thử lại")


def _created_view(txn: Transaction, otp_expires_at: datetime) -> TransactionCreated:
    return TransactionCreated(transaction_id=txn.id, status=txn.status, amount=txn.amount,
                              student_code=txn.student_code, student_name=txn.student_name,
                              otp_expires_at=otp_expires_at)


@router.post("/transactions", status_code=201, response_model=TransactionCreated, responses=E)
def create_transaction(body: CreateTransactionRequest, response: Response, background: BackgroundTasks,
                       user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Seq 1. Gọi service khác TRƯỚC khi ghi DB (không giữ transaction hay khóa trong lúc gọi mạng);
    toàn bộ ghi DB gói trong một commit; email gửi nền sau khi đã trả response."""
    account = db.scalar(select(Account).where(Account.user_id == user.id))
    if account is None:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Chưa có tài khoản thanh toán")
    account_id, balance = account.id, account.balance
    db.rollback()  # kết thúc transaction đọc: không giữ kết nối/transaction trong lúc chờ service khác

    tuition = _read(clients.get_tuition(body.tuition_id), "Tuition",
                    not_found=AppError(404, "TUITION_NOT_FOUND", "Không tìm thấy khoản học phí"))
    profile = _read(clients.get_user(user.id), "User")

    # Server tự kiểm tra lại mọi điều kiện; giao diện chỉ là lớp hỗ trợ.
    amount = Decimal(tuition["amount"])
    if tuition["status"] != "UNPAID":
        raise AppError(409, "TUITION_NOT_AVAILABLE", "Học phí đã được thanh toán hoặc đang được xử lý")
    if balance < amount:
        raise AppError(422, "INSUFFICIENT_BALANCE", "Số dư không đủ để thanh toán")

    txn = Transaction(account_id=account_id, tuition_id=body.tuition_id, student_code=tuition["student_code"],
                      student_name=tuition["student_name"], amount=amount, status="PENDING")
    try:
        db.add(txn)
        db.flush()
    except IntegrityError:
        # Bấm đúp: unique index (account_id, tuition_id) WHERE status='PENDING' từ chối dòng thứ hai.
        db.rollback()
        existing = db.scalar(select(Transaction).where(
            Transaction.account_id == account_id, Transaction.tuition_id == body.tuition_id,
            Transaction.status == "PENDING"))
        if existing is None:
            raise
        expiry = db.scalar(select(Otp.expires_at).where(Otp.transaction_id == existing.id)
                           .order_by(Otp.id.desc()).limit(1))
        response.status_code = 200  # giao dịch cũ, không sinh OTP mới
        return _created_view(existing, expiry or datetime.now(timezone.utc))

    # Sinh OTP không trùng OTP ACTIVE khác; unique index là chốt chặn cuối khi hai request trùng nhau.
    for _ in range(5):
        code = otp.generate_code()
        expires_at = otp.new_expiry()
        try:
            with db.begin_nested():  # savepoint: trùng mã thì chỉ hoàn tác riêng dòng OTP
                db.add(Otp(transaction_id=txn.id, code_hash=otp.hash_code(code), status="ACTIVE",
                           expires_at=expires_at))
                db.flush()
            break
        except IntegrityError:
            continue
    else:
        raise AppError(500, "INTERNAL_ERROR", "Không tạo được OTP, vui lòng thử lại")

    email_log = EmailLog(transaction_id=txn.id, email_type="OTP", recipient=profile["email"], status="PENDING")
    db.add(email_log)
    db.commit()

    background.add_task(send_otp_email, email_log.id, profile["email"], txn.student_code, txn.student_name,
                        amount, code)
    return _created_view(txn, expires_at)


STATUSES = {"PENDING", "DEBITED", "SUCCESS", "FAILED", "EXPIRED"}


def _owned(transaction_id: int, user: CurrentUser):
    """Chỉ giao dịch của chính người dùng; của người khác coi như không tồn tại (404)."""
    return (select(Transaction).join(Account, Account.id == Transaction.account_id)
            .where(Transaction.id == transaction_id, Account.user_id == user.id))


def _item(t: Transaction) -> dict:
    return dict(transaction_id=t.id, student_code=t.student_code, student_name=t.student_name, amount=t.amount,
                status=t.status, fail_reason=t.fail_reason, created_at=t.created_at, completed_at=t.completed_at)


@router.get("/transactions", response_model=TransactionPage, responses=E)
def list_transactions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                      status: str | None = None,
                      user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    conds = [Account.user_id == user.id]
    if status:
        status = status.upper()
        if status not in STATUSES:
            raise AppError(422, "VALIDATION_ERROR", "Dữ liệu không hợp lệ",
                           {"fields": [{"field": "status", "message": f"phải là một trong {sorted(STATUSES)}"}]})
        conds.append(Transaction.status == status)
    total = db.scalar(select(func.count(Transaction.id)).join(Account, Account.id == Transaction.account_id)
                      .where(*conds)) or 0
    rows = db.scalars(select(Transaction).join(Account, Account.id == Transaction.account_id).where(*conds)
                      .order_by(Transaction.created_at.desc(), Transaction.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return TransactionPage(items=[TransactionItem(**_item(t)) for t in rows], page=page, page_size=page_size,
                           total=total)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut, responses=E)
def get_transaction(transaction_id: int, user: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    t = db.scalar(_owned(transaction_id, user))
    if t is None:
        raise AppError(404, "TRANSACTION_NOT_FOUND", "Không tìm thấy giao dịch")
    return TransactionOut(**_item(t), tuition_id=t.tuition_id)


# ----------------------------------------------------------------------------------------------
# Xác nhận OTP và thanh toán (Seq 2, 3, 4)
# ----------------------------------------------------------------------------------------------
def _upd(db: Session, stmt):
    return db.execute(stmt.execution_options(synchronize_session=False))


def _fail(db: Session, tid: int, reason: str) -> None:
    """Đưa giao dịch PENDING sang FAILED trong transaction MỚI (sau khi đã rollback/commit bước trước)."""
    _upd(db, update(Transaction).where(Transaction.id == tid, Transaction.status == "PENDING")
         .values(status="FAILED", fail_reason=reason, completed_at=func.now()))
    db.commit()


def _release_quietly(tuition_id: int, tid: int) -> None:
    """Nhả giữ chỗ cố gắng hết sức; lỗi thì job đối soát sẽ nhả sau (học phí RESERVED treo)."""
    try:
        clients.release_tuition(tuition_id, tid)
    except Exception:  # noqa: BLE001
        log.warning("Chưa nhả được giữ chỗ học phí %s của giao dịch %s; job đối soát sẽ xử lý", tuition_id, tid)


def _abort(db: Session, tid: int, tuition_id: int, reason: str, release: bool) -> None:
    _fail(db, tid, reason)
    if release:
        _release_quietly(tuition_id, tid)


def _reject_otp(db: Session, tid: int) -> AppError:
    """OTP sai/hết hạn: tăng attempts của OTP ACTIVE; đủ OTP_MAX_ATTEMPTS lần thì OTP REVOKED, giao dịch FAILED."""
    cur = _upd(db, update(Otp).where(Otp.transaction_id == tid, Otp.status == "ACTIVE")
               .values(attempts=Otp.attempts + 1).returning(Otp.attempts)).first()
    attempts = cur[0] if cur else settings.otp_max_attempts
    left = max(0, settings.otp_max_attempts - attempts)
    details: dict = {"attempts_left": left}
    if left == 0:
        _upd(db, update(Otp).where(Otp.transaction_id == tid, Otp.status == "ACTIVE").values(status="REVOKED"))
        _upd(db, update(Transaction).where(Transaction.id == tid, Transaction.status == "PENDING")
             .values(status="FAILED", fail_reason="OTP_ATTEMPTS_EXCEEDED", completed_at=func.now()))
        details["transaction_status"] = "FAILED"
    db.commit()
    return AppError(400, "OTP_INVALID", "OTP không đúng hoặc đã hết hạn", details)


@router.post("/transactions/{transaction_id}/confirm", response_model=ConfirmResult, responses=E)
def confirm_transaction(transaction_id: int, body: ConfirmRequest, response: Response,
                        background: BackgroundTasks, user: CurrentUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Thứ tự: kiểm tra chủ sở hữu/trạng thái -> OTP -> giữ chỗ học phí -> trừ tiền + DEBITED (MỘT commit,
    không gọi mạng khi đang giữ khóa dòng) -> Tuition xác nhận -> SUCCESS -> email xác nhận (nền)."""
    txn = db.scalar(_owned(transaction_id, user))
    if txn is None:
        raise AppError(404, "TRANSACTION_NOT_FOUND", "Không tìm thấy giao dịch")
    tid, tuition_id, account_id, amount = txn.id, txn.tuition_id, txn.account_id, txn.amount
    student_code, student_name = txn.student_code, txn.student_name

    # --- Gọi lại (idempotent) và giao dịch đã kết thúc ---
    if txn.status == "SUCCESS":
        return ConfirmResult(transaction_id=tid, status="SUCCESS", amount=amount, completed_at=txn.completed_at)
    if txn.status == "DEBITED":
        response.status_code = 202
        return ConfirmResult(transaction_id=tid, status="DEBITED", amount=amount)
    if txn.status != "PENDING":
        raise AppError(409, "TRANSACTION_NOT_PENDING", "Giao dịch đã kết thúc, vui lòng tạo giao dịch mới",
                       {"status": txn.status, "fail_reason": txn.fail_reason})

    # --- OTP: một câu UPDATE nguyên tử; dùng được đúng một lần ---
    used = _upd(db, update(Otp).where(
        Otp.transaction_id == tid, Otp.status == "ACTIVE", Otp.expires_at > func.now(),
        Otp.code_hash == otp.hash_code(body.otp)).values(status="USED").returning(Otp.id)).first()
    if used is None:
        raise _reject_otp(db, tid)
    db.commit()  # từ đây OTP đã dùng; mọi lỗi phía sau kết thúc giao dịch ở FAILED

    # --- Giữ chỗ học phí (Seq 3: chỉ một giao dịch thắng) ---
    try:
        r = clients.reserve_tuition(tuition_id, tid)
    except AppError:  # timeout hoặc lỗi mạng: có thể Tuition đã giữ chỗ nên vẫn thử nhả
        _abort(db, tid, tuition_id, "TUITION_SERVICE_ERROR", release=True)
        raise AppError(503, "TUITION_SERVICE_ERROR", "Hệ thống đang bận, vui lòng tạo giao dịch mới")
    if r.status_code == 409:
        _abort(db, tid, tuition_id, "TUITION_NOT_AVAILABLE", release=False)
        raise AppError(409, "TUITION_NOT_AVAILABLE", "Học phí đã được thanh toán hoặc đang được xử lý")
    if r.status_code != 200:
        log.error("Tuition giữ chỗ trả %s: %s", r.status_code, r.text[:200])
        _abort(db, tid, tuition_id, "TUITION_SERVICE_ERROR", release=True)
        raise AppError(503, "TUITION_SERVICE_ERROR", "Hệ thống đang bận, vui lòng tạo giao dịch mới")

    # --- Trừ tiền + DEBITED trong MỘT commit (Seq 4: UPDATE có điều kiện, khóa dòng tài khoản) ---
    try:
        debited = _upd(db, update(Account).where(Account.id == account_id, Account.balance >= amount)
                       .values(balance=Account.balance - amount).returning(Account.id)).first()
        if debited is None:
            db.rollback()
            _abort(db, tid, tuition_id, "INSUFFICIENT_BALANCE", release=True)
            raise AppError(422, "INSUFFICIENT_BALANCE", "Số dư không đủ để thanh toán")
        moved = _upd(db, update(Transaction).where(Transaction.id == tid, Transaction.status == "PENDING")
                     .values(status="DEBITED").returning(Transaction.id)).first()
        if moved is None:  # trạng thái vừa bị đổi bởi tiến trình khác: hoàn tác việc trừ tiền
            db.rollback()
            raise AppError(409, "TRANSACTION_NOT_PENDING", "Giao dịch đã kết thúc, vui lòng tạo giao dịch mới")
        db.commit()
    except AppError:
        raise
    except IntegrityError:  # unique index: đã có giao dịch khác DEBITED/SUCCESS cho học phí này
        db.rollback()
        _abort(db, tid, tuition_id, "TUITION_NOT_AVAILABLE", release=True)
        raise AppError(409, "TUITION_NOT_AVAILABLE", "Học phí đã được thanh toán hoặc đang được xử lý")

    # --- Tuition xác nhận PAID. Lỗi thì GIỮ DEBITED (tiền đã trừ), trả 202; job đối soát sẽ thử lại ---
    confirmed = False
    try:
        c = clients.confirm_tuition_payment(tuition_id, tid)
        confirmed = c.status_code == 200
        if not confirmed:
            log.error("Tuition xác nhận trả %s: %s", c.status_code, c.text[:200])
    except AppError:
        log.warning("Chưa xác nhận được với Tuition cho giao dịch %s; giữ DEBITED", tid)
    if not confirmed:
        response.status_code = 202
        return ConfirmResult(transaction_id=tid, status="DEBITED", amount=amount)

    done = _upd(db, update(Transaction).where(Transaction.id == tid, Transaction.status == "DEBITED")
                .values(status="SUCCESS", completed_at=func.now()).returning(Transaction.completed_at)).first()
    completed_at = done[0] if done else db.scalar(select(Transaction.completed_at).where(Transaction.id == tid))
    # Email xác nhận gửi tới cùng địa chỉ đã nhận OTP của giao dịch này
    otp_mail = db.scalar(select(EmailLog).where(EmailLog.transaction_id == tid, EmailLog.email_type == "OTP")
                         .order_by(EmailLog.id.desc()).limit(1))
    email_log = None
    if otp_mail is not None:
        email_log = EmailLog(transaction_id=tid, email_type="CONFIRMATION", recipient=otp_mail.recipient,
                             status="PENDING")
        db.add(email_log)
    db.commit()
    if email_log is not None:
        background.add_task(send_confirmation_email, email_log.id, email_log.recipient, tid, student_code,
                            student_name, amount, completed_at)
    return ConfirmResult(transaction_id=tid, status="SUCCESS", amount=amount, completed_at=completed_at)


# ----------------------------------------------------------------------------------------------
# Gửi lại OTP (UC08, Seq 5)
# ----------------------------------------------------------------------------------------------
def _resend_state(db: Session, tid: int) -> tuple[int, float | None]:
    """(số lần đã gửi lại, số giây kể từ OTP mới nhất). OTP gốc không tính là gửi lại nhưng tính cho khoảng cách."""
    total = db.scalar(select(func.count(Otp.id)).where(Otp.transaction_id == tid)) or 0
    elapsed = db.scalar(select(extract("epoch", func.clock_timestamp() - Otp.created_at))
                        .where(Otp.transaction_id == tid).order_by(Otp.id.desc()).limit(1))
    return max(0, total - 1), (float(elapsed) if elapsed is not None else None)


def _resend_block(used: int, elapsed: float | None) -> AppError | None:
    if used >= settings.otp_max_resends:
        return AppError(429, "OTP_RESEND_LIMIT", "Đã hết lượt gửi lại OTP, vui lòng tạo giao dịch mới",
                        {"resends_left": 0})
    if elapsed is not None and elapsed < settings.otp_resend_cooldown_seconds:
        wait = ceil(settings.otp_resend_cooldown_seconds - elapsed)
        return AppError(429, "OTP_RESEND_COOLDOWN", f"Vui lòng chờ {wait} giây rồi thử lại",
                        {"retry_after": wait}, headers={"Retry-After": str(wait)})
    return None


@router.post("/transactions/{transaction_id}/otps", status_code=201, response_model=OtpResent, responses=E)
def resend_otp(transaction_id: int, background: BackgroundTasks,
               user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Thứ tự: kiểm tra nhanh (không gọi mạng) -> lấy email từ User service -> khóa dòng giao dịch và KIỂM TRA LẠI
    giới hạn dưới khóa (để bấm đúp không vượt giới hạn) -> OTP cũ REVOKED, OTP mới ACTIVE, email_logs -> commit."""
    txn = db.scalar(_owned(transaction_id, user))
    if txn is None:
        raise AppError(404, "TRANSACTION_NOT_FOUND", "Không tìm thấy giao dịch")
    tid, student_code, student_name, amount = txn.id, txn.student_code, txn.student_name, txn.amount
    if txn.status != "PENDING":
        raise AppError(409, "TRANSACTION_NOT_PENDING", "Giao dịch đã kết thúc, vui lòng tạo giao dịch mới",
                       {"status": txn.status, "fail_reason": txn.fail_reason})
    blocked = _resend_block(*_resend_state(db, tid))
    if blocked:
        raise blocked
    db.rollback()  # kết thúc transaction đọc trước khi gọi mạng (không giữ kết nối/khóa khi chờ service khác)

    profile = _read(clients.get_user(user.id), "User")

    locked = db.scalar(select(Transaction).where(Transaction.id == tid).with_for_update()
                       .execution_options(populate_existing=True))
    if locked is None or locked.status != "PENDING":
        status, reason = (locked.status, locked.fail_reason) if locked else ("UNKNOWN", None)
        db.rollback()
        raise AppError(409, "TRANSACTION_NOT_PENDING", "Giao dịch đã kết thúc, vui lòng tạo giao dịch mới",
                       {"status": status, "fail_reason": reason})
    used, elapsed = _resend_state(db, tid)
    blocked = _resend_block(used, elapsed)
    if blocked:
        db.rollback()
        raise blocked

    _upd(db, update(Otp).where(Otp.transaction_id == tid, Otp.status == "ACTIVE").values(status="REVOKED"))
    for _ in range(5):  # OTP mới không trùng OTP ACTIVE khác; unique index là chốt chặn cuối
        code = otp.generate_code()
        expires_at = otp.new_expiry()
        try:
            with db.begin_nested():
                db.add(Otp(transaction_id=tid, code_hash=otp.hash_code(code), status="ACTIVE", expires_at=expires_at))
                db.flush()
            break
        except IntegrityError:
            continue
    else:
        db.rollback()
        raise AppError(500, "INTERNAL_ERROR", "Không tạo được OTP, vui lòng thử lại")
    email_log = EmailLog(transaction_id=tid, email_type="OTP", recipient=profile["email"], status="PENDING")
    db.add(email_log)
    db.commit()

    background.add_task(send_otp_email, email_log.id, profile["email"], student_code, student_name, amount, code)
    return OtpResent(otp_expires_at=expires_at, resends_left=settings.otp_max_resends - (used + 1))
