"""Nạp dữ liệu mẫu khi khởi động: thêm mọi username trong SEED_USERS mà chưa có (không đụng dữ liệu đã có).
Id được cấp tuần tự 1, 2, 3 nên các service khác (Payment: accounts.user_id) có thể tham chiếu cố định.
Mật khẩu mẫu chỉ dùng để phát triển và demo."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User
from .passwords import hash_password

log = logging.getLogger("ibanking.seed")

SEED_PASSWORD = "123456"
SEED_USERS = [
    # (username, họ tên, số điện thoại, email)
    ("nguyenvana", "Nguyễn Văn A", "0901234567", "a@example.com"),
    ("lethib", "Lê Thị B", "0902345678", "b@example.com"),
    ("phamvanc", "Phạm Văn C", "0903456789", "c@example.com"),
    # Tám tài khoản dành riêng cho tests/concurrency_seq4.py (id 4..11, mỗi lần chạy dùng một tài khoản mới).
    *[(f"tester{i}", f"Kiểm Thử {i}", f"09100000{i:02d}", f"t{i}@example.com") for i in range(1, 9)],
]


def seed_missing(db: Session) -> None:
    existing = set(db.scalars(select(User.username)))
    todo = [u for u in SEED_USERS if u[0] not in existing]
    if not todo:
        return
    password_hash = hash_password(SEED_PASSWORD)  # dùng chung một hash
    for username, full_name, phone, email in todo:  # thêm theo thứ tự nên id tuần tự
        db.add(User(username=username, password_hash=password_hash,
                    full_name=full_name, phone=phone, email=email))
    db.commit()
    log.info("Đã nạp thêm %d người dùng mẫu (mật khẩu: %s)", len(todo), SEED_PASSWORD)
