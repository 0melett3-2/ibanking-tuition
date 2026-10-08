"""Gửi email qua SMTP (Mailpit khi chạy local). Gọi từ BackgroundTasks, không gọi trong request."""
import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("ibanking.mail")


def send_email(to: str, subject: str, body: str) -> None:
    """Ném exception nếu gửi lỗi; nơi gọi chịu trách nhiệm ghi EMAIL_LOGS = FAILED và thử lại."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
        smtp.send_message(msg)
    log.info("Đã gửi email '%s' tới %s", subject, to)
