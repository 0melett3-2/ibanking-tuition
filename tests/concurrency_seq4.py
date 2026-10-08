"""Seq 4: MỘT tài khoản thanh toán HAI học phí đồng thời, số dư chỉ đủ cho một.
Tài khoản tester (1.500.000) trả hai học phí 1.000.000. Kết quả đúng: đúng một giao dịch SUCCESS, giao dịch kia nhận
422 INSUFFICIENT_BALANCE (học phí của nó được nhả chỗ), số dư cuối đúng 500.000 và KHÔNG BAO GIỜ âm.
Chạy: python tests/concurrency_seq4.py [--rounds N]   (mỗi vòng dùng 1 tài khoản tester và 2 MSSV 52106xxx; có 8 tester)
Làm mới: docker compose down -v rồi up --build."""
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from common import (PAYMENT, TUITION, balance, call, check, clear_mailbox, code, finish, login, otp_mails, otp_of)

A = login("nguyenvana")  # chỉ để tra cứu học phí


def pick_tester():
    for i in range(1, 9):
        h = login(f"tester{i}")
        if balance(h) == Decimal("1500000.00"):
            return i, h
    raise SystemExit("Hết tài khoản tester1..tester8 còn nguyên số dư: docker compose down -v rồi up --build")


def pick_two_tuitions():
    found = []
    for i in range(1, 17):
        s, b = call(TUITION, "GET", f"/students/52106{i:03d}/tuition", headers=A)
        if s == 200 and b["status"] == "UNPAID":
            found.append(b)
            if len(found) == 2:
                return found
    raise SystemExit("Hết MSSV 52106001..52106016: docker compose down -v rồi up --build")


def one_round(n):
    i, h = pick_tester()
    t1, t2 = pick_two_tuitions()
    print(f"\n=== Vòng {n}: tester{i} (số dư 1.500.000) trả đồng thời {t1['student_code']} và {t2['student_code']} ===")
    clear_mailbox()
    txns = {}
    for t in (t1, t2):
        s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": t["tuition_id"]}, h)
        check(f"tạo giao dịch cho {t['student_code']} -> 201", s == 201, (s, b))
        txns[t["student_code"]] = b.get("transaction_id")
    texts = otp_mails(f"t{i}@example.com", 2)
    codes = {m: otp_of(tx) for tx in texts for m in txns if m in tx}
    check("nhận đủ 2 email OTP, đối chiếu đúng MSSV", len(codes) == 2 and all(codes.values()), texts)
    if len(codes) != 2:
        return
    before = balance(h)

    barrier = threading.Barrier(2)

    def go(mssv):
        barrier.wait()  # hai request xuất phát cùng lúc, cùng một tài khoản
        return mssv, call(PAYMENT, "POST", f"/transactions/{txns[mssv]}/confirm", {"otp": codes[mssv]}, h)

    with ThreadPoolExecutor(max_workers=2) as pool:
        out = [f.result() for f in [pool.submit(go, t["student_code"]) for t in (t1, t2)]]
    for mssv, (s, b) in out:
        print(f"  {mssv} -> HTTP {s} {b.get('status') or code(b)}")

    wins = [m for m, (s, b) in out if s == 200 and b.get("status") == "SUCCESS"]
    fails = [m for m, (s, b) in out if s == 422 and code(b) == "INSUFFICIENT_BALANCE"]
    check("đúng 1 giao dịch thành công và 1 giao dịch nhận 422 INSUFFICIENT_BALANCE",
          len(wins) == 1 and len(fails) == 1, f"thắng={wins}, thua={fails}")
    final = balance(h)
    check("số dư cuối đúng 500.000 (trừ đúng một lần), không âm", final == Decimal("500000.00") and final >= 0,
          f"{before} -> {final}")
    if len(wins) != 1 or len(fails) != 1:
        return
    s, b = call(PAYMENT, "GET", f"/transactions/{txns[fails[0]]}", headers=h)
    check("giao dịch thua: FAILED, fail_reason INSUFFICIENT_BALANCE",
          b.get("status") == "FAILED" and b.get("fail_reason") == "INSUFFICIENT_BALANCE", (s, b))
    s, b = call(TUITION, "GET", f"/students/{wins[0]}/tuition", headers=A)
    check("học phí của giao dịch thắng: PAID", b.get("status") == "PAID", (s, b))
    s, b = call(TUITION, "GET", f"/students/{fails[0]}/tuition", headers=A)
    check("học phí của giao dịch thua được NHẢ CHỖ: UNPAID", b.get("status") == "UNPAID", (s, b))


ap = argparse.ArgumentParser()
ap.add_argument("--rounds", type=int, default=1)
for n in range(1, ap.parse_args().rounds + 1):
    one_round(n)
finish()
