"""Nạp dữ liệu mẫu khi khởi động: thêm mọi MSSV trong SEED mà chưa có (không đụng dữ liệu đã có,
nên thêm MSSV mới không cần xóa database). Khớp mục "Dữ liệu mẫu" của hợp đồng API."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Student, Tuition

log = logging.getLogger("ibanking.seed")

# (MSSV, họ tên, số tiền hoặc None nếu chưa có khoản học phí, trạng thái)
SEED = [
    ("52100001", "Trần Thị B", "15000000.00", "UNPAID"),   # Seq 3: A và B cùng trả MSSV này
    ("52100002", "Nguyễn Văn D", "15000000.00", "PAID"),    # thử khóa nút (đã thanh toán)
    ("52100003", "Lê Văn E", "15000000.00", "UNPAID"),      # Seq 4: A trả cả 52100001 và 52100003
    ("52100005", "Phạm Thị F", None, None),                 # sinh viên chưa có học phí (TUITION_NOT_FOUND)
    # Hai sinh viên dành riêng cho tests/smoke_tuition.py, không dùng cho demo.
    ("52109999", "Kiểm Thử Luồng", "1000000.00", "UNPAID"),
    ("52109998", "Kiểm Thử Đồng Thời", "1000000.00", "UNPAID"),
    # Tám sinh viên dự phòng cho tests/smoke_confirm.py: mỗi lần chạy thanh toán xong (PAID) một MSSV.
    *[(f"5210800{i}", f"Kiểm Thử Dự Phòng {i}", "1000000.00", "UNPAID") for i in range(1, 9)],
    # Kho MSSV cho tests/concurrency_seq3.py (mỗi vòng dùng 1) và concurrency_seq4.py (mỗi vòng dùng 2).
    *[(f"5210700{i}", f"Kiểm Thử Seq3 {i}", "1000000.00", "UNPAID") for i in range(1, 9)],
    *[(f"52106{i:03d}", f"Kiểm Thử Seq4 {i}", "1000000.00", "UNPAID") for i in range(1, 17)],
    # Kho MSSV cho tests/smoke_resend.py (mỗi lần chạy dùng 1).
    *[(f"5210500{i}", f"Kiểm Thử Gửi Lại {i}", "1000000.00", "UNPAID") for i in range(1, 9)],
    # Kho MSSV cho tests/smoke_reconcile.py (mỗi lần chạy dùng 3).
    *[(f"52104{i:03d}", f"Kiểm Thử Đối Soát {i}", "1000000.00", "UNPAID") for i in range(1, 13)],
]


def seed_missing(db: Session) -> None:
    now = datetime.now(timezone.utc)
    existing = set(db.scalars(select(Student.student_code)))
    added = 0
    for code, name, amount, status in SEED:
        if code in existing:
            continue
        student = Student(student_code=code, full_name=name)
        db.add(student)
        db.flush()  # lấy student.id
        if amount is not None:
            db.add(Tuition(student_id=student.id, amount=Decimal(amount), status=status,
                           paid_at=now if status == "PAID" else None))
        added += 1
    db.commit()
    if added:
        log.info("Đã nạp thêm %d sinh viên mẫu", added)
