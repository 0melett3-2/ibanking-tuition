"""Job đối soát: đưa hệ thống về trạng thái nhất quán sau sự cố. Chạy nền theo chu kỳ RECONCILE_INTERVAL_SECONDS
và theo yêu cầu qua POST /internal/jobs/reconcile. Mọi bước đều IDEMPOTENT và dùng chuyển trạng thái có điều kiện
(UPDATE ... WHERE status = ...) nên chạy chồng nhau hay chạy song song với request thật vẫn an toàn.

Các bước theo thứ tự:
 1. OTP ACTIVE hết hạn                         -> OTP EXPIRED
 2. Giao dịch PENDING quá hạn (hết OTP + grace) -> EXPIRED; PENDING có OTP USED nhưng treo -> FAILED (PROCESSING_INTERRUPTED)
 3. Giao dịch DEBITED                          -> thử xác nhận với Tuition; thành công -> SUCCESS + email xác nhận
 4. Giao dịch FAILED/EXPIRED vừa kết thúc      -> nếu Tuition còn giữ chỗ cho đúng giao dịch đó thì nhả
 5. Email xác nhận gửi lỗi                     -> thử lại (tối đa 3 lần)
Chưa tự xử lý: DEBITED mà Tuition trả 409 (học phí đã thuộc người khác) - cần hoàn tiền thủ công; job chỉ ghi log."""
import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import clients
from .config import settings
from .database import SessionLocal
from .email_service import send_confirmation_email
from .models import EmailLog, Otp, Transaction
from .schemas import ReconcileResult

log = logging.getLogger("ibanking.jobs")
_lock = threading.Lock()
BATCH = 100
RELEASE_REASONS = ("TUITION_SERVICE_ERROR", "INSUFFICIENT_BALANCE", "PROCESSING_INTERRUPTED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upd(db: Session, stmt):
    return db.execute(stmt.execution_options(synchronize_session=False))


def _expire_otps(db: Session) -> int:
    rows = _upd(db, update(Otp).where(Otp.status == "ACTIVE", Otp.expires_at < func.now())
                .values(status="EXPIRED").returning(Otp.id)).all()
    db.commit()
    return len(rows)


def _sweep_pending(db: Session) -> tuple[int, int]:
    """Trả về (số giao dịch EXPIRED, số giao dịch bị gián đoạn -> FAILED). Mỗi giao dịch khóa dòng riêng rồi
    đánh giá lại dưới khóa, nên không đè lên một lần 'Gửi lại OTP' đang diễn ra cùng lúc."""
    ids = db.scalars(select(Transaction.id).where(Transaction.status == "PENDING")
                     .order_by(Transaction.id).limit(BATCH)).all()
    db.rollback()
    expired = interrupted = 0
    grace = timedelta(seconds=settings.transaction_expire_grace_seconds)
    stuck = timedelta(seconds=settings.reconcile_stuck_seconds)
    for tid in ids:
        row = db.execute(select(Transaction.id, Transaction.status).where(Transaction.id == tid)
                         .with_for_update(skip_locked=True)).first()
        if row is None or row.status != "PENDING":
            db.rollback()
            continue
        otps = db.execute(select(Otp.status, Otp.expires_at).where(Otp.transaction_id == tid)).all()
        statuses = {o.status for o in otps}
        now = _now()
        if "USED" in statuses and "ACTIVE" not in statuses:
            used_exp = max(o.expires_at for o in otps if o.status == "USED")
            if used_exp + stuck < now:
                _upd(db, update(Transaction).where(Transaction.id == tid, Transaction.status == "PENDING")
                     .values(status="FAILED", fail_reason="PROCESSING_INTERRUPTED", completed_at=func.now()))
                db.commit()
                interrupted += 1
                continue
        elif "ACTIVE" not in statuses and otps:
            if max(o.expires_at for o in otps) + grace < now:
                _upd(db, update(Transaction).where(Transaction.id == tid, Transaction.status == "PENDING")
                     .values(status="EXPIRED", fail_reason="OTP_EXPIRED", completed_at=func.now()))
                db.commit()
                expired += 1
                continue
        db.rollback()
    return expired, interrupted


def _complete_debited(db: Session) -> int:
    """Tiền đã trừ nhưng Tuition chưa xác nhận: thử lại. Tuition confirm là idempotent theo reserved_by."""
    rows = db.execute(select(Transaction.id, Transaction.tuition_id, Transaction.student_code,
                             Transaction.student_name, Transaction.amount)
                      .where(Transaction.status == "DEBITED").order_by(Transaction.id).limit(BATCH)).all()
    db.rollback()  # không giữ transaction trong lúc gọi mạng
    completed = 0
    for tid, tuition_id, student_code, student_name, amount in rows:
        try:
            resp = clients.confirm_tuition_payment(tuition_id, tid)
        except Exception:  # noqa: BLE001 - Tuition chưa hồi phục: lần chạy sau thử lại
            log.warning("Giao dịch %s: chưa liên lạc được Tuition, giữ DEBITED", tid)
            continue
        if resp.status_code != 200:
            log.error("Giao dịch %s: Tuition trả %s khi xác nhận (%s) - CẦN XỬ LÝ THỦ CÔNG nếu lặp lại",
                      tid, resp.status_code, resp.text[:120])
            continue
        won = _upd(db, update(Transaction).where(Transaction.id == tid, Transaction.status == "DEBITED")
                   .values(status="SUCCESS", completed_at=func.now()).returning(Transaction.completed_at)).first()
        if won is None:  # request thật vừa hoàn tất trước job
            db.rollback()
            continue
        otp_mail = db.scalar(select(EmailLog).where(EmailLog.transaction_id == tid, EmailLog.email_type == "OTP")
                             .order_by(EmailLog.id.desc()).limit(1))
        email_log = None
        if otp_mail is not None:
            email_log = EmailLog(transaction_id=tid, email_type="CONFIRMATION", recipient=otp_mail.recipient,
                                 status="PENDING")
            db.add(email_log)
            db.flush()  # lấy email_log.id
        db.commit()
        completed += 1
        log.info("Giao dịch %s: đã hoàn tất (DEBITED -> SUCCESS) bởi job đối soát", tid)
        if email_log is not None:  # gửi ngay; nếu lỗi, _retry_emails sẽ thử lại sau
            send_confirmation_email(email_log.id, email_log.recipient, tid, student_code, student_name, amount,
                                    won[0])
    return completed


def _release_stale(db: Session) -> int:
    since = _now() - timedelta(seconds=settings.reconcile_release_window_seconds)
    rows = db.execute(select(Transaction.id, Transaction.tuition_id)
                      .where(Transaction.status.in_(("FAILED", "EXPIRED")),
                             Transaction.fail_reason.in_(RELEASE_REASONS), Transaction.completed_at > since)
                      .order_by(Transaction.id).limit(BATCH)).all()
    db.rollback()
    released = 0
    for tid, tuition_id in rows:
        try:
            info = clients.get_tuition(tuition_id)
            if info.status_code == 200 and info.json().get("status") == "RESERVED" \
                    and info.json().get("reserved_by") == tid:
                if clients.release_tuition(tuition_id, tid).status_code == 204:
                    released += 1
                    log.info("Đã nhả giữ chỗ treo của giao dịch %s (học phí %s)", tid, tuition_id)
        except Exception:  # noqa: BLE001
            log.warning("Chưa kiểm tra/nhả được giữ chỗ của giao dịch %s", tid)
    return released


def _retry_emails(db: Session) -> int:
    """Chỉ thử lại email XÁC NHẬN. OTP không thử lại được (mã gốc không được lưu) - người dùng dùng Gửi lại OTP."""
    older = _now() - timedelta(seconds=60)
    rows = db.execute(select(EmailLog.id, EmailLog.recipient, Transaction.id, Transaction.student_code,
                             Transaction.student_name, Transaction.amount, Transaction.completed_at)
                      .join(Transaction, Transaction.id == EmailLog.transaction_id)
                      .where(EmailLog.email_type == "CONFIRMATION", EmailLog.status.in_(("FAILED", "PENDING")),
                             EmailLog.attempts < 3, Transaction.status == "SUCCESS",
                             Transaction.completed_at < older)
                      .order_by(EmailLog.id).limit(BATCH)).all()
    db.rollback()
    for log_id, to, tid, code, name, amount, completed_at in rows:
        send_confirmation_email(log_id, to, tid, code, name, amount, completed_at)
    return len(rows)


def _safe(step, db: Session):
    try:
        return step(db)
    except Exception:  # noqa: BLE001 - một bước lỗi không được chặn các bước còn lại
        log.exception("Bước đối soát %s lỗi", getattr(step, "__name__", step))
        db.rollback()
        return None


def run_reconcile() -> ReconcileResult:
    if not _lock.acquire(blocking=False):  # đang có một lần chạy khác
        return ReconcileResult()
    try:
        res = ReconcileResult()
        with SessionLocal() as db:
            res.expired_otps = _safe(_expire_otps, db) or 0
            res.expired_transactions, res.interrupted_transactions = _safe(_sweep_pending, db) or (0, 0)
            res.retried_confirms = _safe(_complete_debited, db) or 0
            res.released_reservations = _safe(_release_stale, db) or 0
            res.retried_emails = _safe(_retry_emails, db) or 0
        return res
    finally:
        _lock.release()


async def reconcile_loop(interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(run_reconcile)
        except Exception:  # không để job chết vì một lần lỗi
            log.exception("Job đối soát lỗi")
