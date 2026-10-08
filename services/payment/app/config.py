import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ["DATABASE_URL"]
    user_service_url: str = os.environ["USER_SERVICE_URL"]
    tuition_service_url: str = os.environ["TUITION_SERVICE_URL"]
    internal_api_key: str = os.environ["INTERNAL_API_KEY"]
    smtp_host: str = os.getenv("SMTP_HOST", "mailpit")
    smtp_port: int = int(os.getenv("SMTP_PORT", "1025"))
    mail_from: str = os.getenv("MAIL_FROM", "no-reply@ibanking.local")
    otp_hmac_secret: str = os.environ["OTP_HMAC_SECRET"]
    # OTP_TTL_SECONDS (nếu có) ưu tiên hơn OTP_TTL_MINUTES; dùng để rút ngắn thời gian khi kiểm thử.
    otp_ttl_seconds: int = int(os.getenv("OTP_TTL_SECONDS") or int(os.getenv("OTP_TTL_MINUTES", "5")) * 60)
    # Giao dịch PENDING chỉ chuyển EXPIRED khi OTP mới nhất đã hết hạn quá khoảng này (trong lúc đó vẫn gửi lại OTP được).
    transaction_grace_seconds: int = int(os.getenv("TRANSACTION_EXPIRY_GRACE_SECONDS", "600"))
    otp_max_attempts: int = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))
    otp_max_resends: int = int(os.getenv("OTP_MAX_RESENDS", "3"))
    otp_resend_cooldown_seconds: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))
    reconcile_interval_seconds: int = int(os.getenv("RECONCILE_INTERVAL_SECONDS") or 30)
    # Giao dịch PENDING chỉ chuyển EXPIRED sau khi OTP MỚI NHẤT hết hạn thêm chừng này giây, để người dùng
    # vẫn kịp bấm "Gửi lại OTP" (UC08) khi OTP hết hạn.
    transaction_expire_grace_seconds: int = int(os.getenv("TRANSACTION_EXPIRE_GRACE_SECONDS") or 600)
    # Giao dịch PENDING có OTP đã USED mà quá hạn chừng này giây vẫn chưa xong => xử lý bị gián đoạn (sập giữa chừng).
    reconcile_stuck_seconds: int = int(os.getenv("RECONCILE_STUCK_SECONDS") or 60)
    # Chỉ thử nhả giữ chỗ cho giao dịch FAILED/EXPIRED vừa kết thúc trong khoảng này.
    reconcile_release_window_seconds: int = int(os.getenv("RECONCILE_RELEASE_WINDOW_SECONDS") or 600)
    http_timeout_seconds: float = 3.0


settings = Settings()
