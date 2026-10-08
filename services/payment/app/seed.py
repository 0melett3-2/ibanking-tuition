"""Nạp số dư mẫu khi khởi động: thêm mọi user_id còn thiếu (không đụng số dư đã có).
user_id khớp dữ liệu mẫu của User service (1 = nguyenvana, 2 = lethib, 3 = phamvanc)."""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Account

log = logging.getLogger("ibanking.seed")

SEED_ACCOUNTS = [
    (1, "20000000.00"),  # A: đủ trả 15.000.000 một lần; hai lần thì thiếu (Seq 4)
    (2, "20000000.00"),  # B
    (3, "1000000.00"),   # C: thiếu số dư (thử INSUFFICIENT_BALANCE)
    # Tám tài khoản tester (user_id 4..11) cho tests/concurrency_seq4.py: 1,5 triệu = đủ trả MỘT trong hai học phí 1 triệu.
    *[(3 + i, "1500000.00") for i in range(1, 9)],
]


def seed_missing(db: Session) -> None:
    existing = set(db.scalars(select(Account.user_id)))
    todo = [(uid, bal) for uid, bal in SEED_ACCOUNTS if uid not in existing]
    for user_id, balance in todo:
        db.add(Account(user_id=user_id, balance=Decimal(balance)))
    db.commit()
    if todo:
        log.info("Đã nạp thêm %d tài khoản mẫu", len(todo))
