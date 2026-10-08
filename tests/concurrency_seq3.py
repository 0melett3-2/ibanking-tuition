"""Seq 3: hai người dùng (A, B) cùng thanh toán MỘT học phí, xác nhận OTP đồng thời.
Kết quả đúng: đúng một giao dịch SUCCESS; người kia nhận 409 TUITION_NOT_AVAILABLE, giao dịch FAILED và KHÔNG bị trừ tiền.
Chạy: python tests/concurrency_seq3.py [--rounds N]   (mặc định 1 vòng; kho có 8 MSSV 52107001..52107008)
Mỗi vòng tiêu thụ một MSSV và trừ 1.000.000 của người thắng; làm mới: docker compose down -v rồi up --build."""
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from common import (PAYMENT, TUITION, balance, call, check, clear_mailbox, code, env_value, finish, login,
                    otp_mails, otp_of)

KEY = {"X-Internal-Key": env_value("INTERNAL_API_KEY")}
A, B = login("nguyenvana"), login("lethib")


def pick_tuition():
    for i in range(1, 9):
        s, b = call(TUITION, "GET", f"/students/5210700{i}/tuition", headers=A)
        if s == 200 and b["status"] == "UNPAID":
            return b
    raise SystemExit("Hết MSSV 52107001..52107008: docker compose down -v rồi up --build")


def one_round(n):
    t = pick_tuition()
    tid, mssv = t["tuition_id"], t["student_code"]
    print(f"\n=== Vòng {n}: A và B cùng trả MSSV {mssv} (tuition_id={tid}) ===")
    clear_mailbox()
    sa, ba = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid}, A)
    sb, bb = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid}, B)
    check("A và B đều tạo được giao dịch PENDING riêng", sa == 201 and sb == 201, (sa, ba, sb, bb))
    ta, tb = ba["transaction_id"], bb["transaction_id"]
    code_a = otp_of((otp_mails("a@example.com", 1) or [None])[0])
    code_b = otp_of((otp_mails("b@example.com", 1) or [None])[0])
    check("cả hai nhận được OTP qua email", code_a and code_b)
    bal_a, bal_b = balance(A), balance(B)

    barrier = threading.Barrier(2)

    def go(h, txn, otp_code):
        barrier.wait()  # hai request xuất phát cùng lúc
        return call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": otp_code}, h)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa, fb = pool.submit(go, A, ta, code_a), pool.submit(go, B, tb, code_b)
        (s1, r1), (s2, r2) = fa.result(), fb.result()
    print(f"  A -> HTTP {s1} {r1.get('status') or code(r1)}    B -> HTTP {s2} {r2.get('status') or code(r2)}")

    players = {"A": (A, ta, s1, r1, bal_a), "B": (B, tb, s2, r2, bal_b)}
    winners = [k for k, v in players.items() if v[2] == 200 and v[3].get("status") == "SUCCESS"]
    losers = [k for k, v in players.items() if v[2] == 409 and code(v[3]) == "TUITION_NOT_AVAILABLE"]
    check("đúng 1 người thành công (200 SUCCESS) và 1 người nhận 409 TUITION_NOT_AVAILABLE",
          len(winners) == 1 and len(losers) == 1, f"thắng={winners}, thua={losers}")
    if len(winners) != 1 or len(losers) != 1:
        return
    w, l = players[winners[0]], players[losers[0]]
    s, b = call(PAYMENT, "GET", f"/transactions/{w[1]}", headers=w[0])
    check("giao dịch người thắng: SUCCESS", s == 200 and b.get("status") == "SUCCESS", (s, b))
    s, b = call(PAYMENT, "GET", f"/transactions/{l[1]}", headers=l[0])
    check("giao dịch người thua: FAILED, fail_reason TUITION_NOT_AVAILABLE",
          s == 200 and b.get("status") == "FAILED" and b.get("fail_reason") == "TUITION_NOT_AVAILABLE", (s, b))
    check("người thắng bị trừ đúng 1.000.000", w[4] - balance(w[0]) == Decimal("1000000.00"))
    check("người thua KHÔNG bị trừ tiền", balance(l[0]) == l[4])
    s, b = call(TUITION, "GET", f"/students/{mssv}/tuition", headers=A)
    check("học phí được thanh toán đúng một lần (PAID)", s == 200 and b.get("status") == "PAID", (s, b))
    s, b = call(TUITION, "GET", f"/tuitions/{tid}", headers=KEY)
    check("reserved_by của học phí là giao dịch của người thắng", b.get("reserved_by") == w[1], b)
    s, b = call(PAYMENT, "POST", f"/transactions/{l[1]}/confirm", {"otp": code_a if winners[0] == "B" else code_b}, l[0])
    check("người thua xác nhận lại -> 409 TRANSACTION_NOT_PENDING", s == 409 and code(b) == "TRANSACTION_NOT_PENDING", (s, b))


ap = argparse.ArgumentParser()
ap.add_argument("--rounds", type=int, default=1)
for n in range(1, ap.parse_args().rounds + 1):
    one_round(n)
finish()
