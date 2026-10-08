"""Gửi email nền (OTP, xác nhận) và ghi kết quả vào EMAIL_LOGS. Hàm chạy sau khi đã trả response
(BackgroundTasks) nên tự mở session riêng. Mã OTP gốc chỉ nằm trong bộ nhớ và email;
nếu gửi lỗi thì người dùng dùng chức năng Gửi lại OTP (UC08)."""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .config import settings
from .database import SessionLocal
from .mail import send_email
from .models import EmailLog

log = logging.getLogger("ibanking.email")
VN = timezone(timedelta(hours=7))


def _ttl_text() -> str:
    secs = settings.otp_ttl_seconds
    return f"{secs // 60} phút" if secs % 60 == 0 else f"{secs} giây"


def _vnd(amount: Decimal) -> str:
    return f"{amount:,.0f}".replace(",", ".") + " VND"


def _ttl_text() -> str:
    ttl = settings.otp_ttl_seconds
    return f"{ttl // 60} phút" if ttl >= 60 else f"{ttl} giây"


def _deliver(email_log_id: int, to: str, subject: str, body: str) -> None:
    status = "SENT"
    try:
        send_email(to, subject, body)
    except Exception:  # noqa: BLE001 - lỗi SMTP không được làm hỏng giao dịch
        log.exception("Gửi email lỗi (email_log %s)", email_log_id)
        status = "FAILED"
    with SessionLocal() as db:
        row = db.get(EmailLog, email_log_id)
        if row is not None:
            row.attempts += 1
            row.status = status
            row.sent_at = datetime.now(timezone.utc) if status == "SENT" else None
            db.commit()


def send_otp_email(email_log_id: int, to: str, student_code: str, student_name: str,
                   amount: Decimal, code: str) -> None:
    body = (
        f"Mã OTP của bạn: {code}\n\n"
        f"Giao dịch: đóng học phí cho sinh viên {student_name} (MSSV {student_code}), số tiền {_vnd(amount)}.\n"
        f"Mã có hiệu lực trong {_ttl_text()} và chỉ dùng được một lần.\n"
        "Không chia sẻ mã này cho bất kỳ ai."
    )
    _deliver(email_log_id, to, "Mã OTP xác nhận thanh toán học phí", body)


def send_confirmation_email(email_log_id: int, to: str, transaction_id: int, student_code: str,
                            student_name: str, amount: Decimal, completed_at: datetime | None) -> None:
    when = (completed_at or datetime.now(timezone.utc)).astimezone(VN).strftime("%H:%M %d/%m/%Y")
    body = (
        "Thanh toán học phí thành công.\n\n"
        f"Mã giao dịch: {transaction_id}\n"
        f"Sinh viên: {student_name} (MSSV {student_code})\n"
        f"Số tiền: {_vnd(amount)}\n"
        f"Thời gian: {when}\n"
    )
    _deliver(email_log_id, to, "Thanh toán học phí thành công", body)
