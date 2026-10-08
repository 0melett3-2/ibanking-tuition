"""Kiểm tra gửi lại OTP (UC08, Seq 5): python tests/smoke_resend.py
Cần chế độ DEV (User, Tuition, Payment, Mailpit). Mặc định khoảng cách giữa hai lần gửi là 60 giây nên script chỉ kiểm tra
phần "từ chối"; để kiểm tra đầy đủ (mất ~15 giây) đặt trong .env  OTP_RESEND_COOLDOWN_SECONDS=2  rồi  docker compose up -d
(chạy xong nhớ trả về 60 và up -d lại trước khi demo).
Mỗi lần chạy đầy đủ thanh toán xong một MSSV 52105001..52105008 và trừ 1.000.000 của A; làm mới: docker compose down -v."""
import json
import pathlib
import time
import urllib.error
import urllib.request

from common import PAYMENT, TUITION, balance, call, check, clear_mailbox, code, finish, login, otp_mails, otp_of


def env_opt(name, default):
    path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return int(line.split("=", 1)[1].strip())
    return default


def post_with_headers(path, headers=None):
    req = urllib.request.Request(PAYMENT + path, data=b"", method="POST", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}"), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), {k.lower(): v for k, v in e.headers.items()}


COOLDOWN, MAX_RESENDS = env_opt("OTP_RESEND_COOLDOWN_SECONDS", 60), env_opt("OTP_MAX_RESENDS", 3)
A, B = login("nguyenvana"), login("lethib")
clear_mailbox()  # xóa TRƯỚC khi tạo giao dịch (email gửi nền sau response, xóa sau sẽ lệch mã)

txn = tid = None
for i in range(1, 9):
    s, t = call(TUITION, "GET", f"/students/5210500{i}/tuition", headers=A)
    if s == 200 and t["status"] == "UNPAID":
        s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": t["tuition_id"]}, A)
        if s == 201:  # 200 nghĩa là A đã có giao dịch PENDING cũ cho học phí này: bỏ qua, thử MSSV khác
            txn, tid, mssv = b["transaction_id"], t["tuition_id"], t["student_code"]
            break
if txn is None:
    raise SystemExit("Hết MSSV 52105001..52105008: docker compose down -v rồi up --build")
print(f"Dùng MSSV {mssv}, giao dịch {txn}; khoảng cách gửi lại={COOLDOWN}s, tối đa {MAX_RESENDS} lần")

first = otp_mails("a@example.com", 1)
history = [otp_of(first[0])] if first else []  # các mã đã thấy theo thứ tự: OTP gốc, lần gửi lại 1, 2, 3
check("nhận được email OTP gốc", len(history) == 1 and history[0], first)

print("== Từ chối ==")
s, b, h = post_with_headers(f"/transactions/{txn}/otps")
check("không token -> 401", s == 401, (s, b))
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/otps", None, B)
check("B gửi lại OTP của giao dịch người khác -> 404", s == 404 and code(b) == "TRANSACTION_NOT_FOUND", (s, b))
s, b = call(PAYMENT, "POST", "/transactions/999999/otps", None, A)
check("giao dịch không tồn tại -> 404", s == 404 and code(b) == "TRANSACTION_NOT_FOUND", (s, b))
s, b, h = post_with_headers(f"/transactions/{txn}/otps", A)
ra = b.get("error", {}).get("details", {}).get("retry_after")
check("gửi lại ngay sau OTP gốc -> 429 OTP_RESEND_COOLDOWN, có retry_after và header Retry-After",
      s == 429 and code(b) == "OTP_RESEND_COOLDOWN" and isinstance(ra, int) and 1 <= ra <= COOLDOWN
      and h.get("retry-after") == str(ra), (s, b, h))

if COOLDOWN > 10:
    print("\n[SKIP] OTP_RESEND_COOLDOWN_SECONDS > 10 nên bỏ qua phần gửi lại thật. Đặt OTP_RESEND_COOLDOWN_SECONDS=2 "
          "trong .env, chạy docker compose up -d rồi chạy lại (giao dịch này sẽ bị bỏ qua, script dùng MSSV khác).")
    finish()


def new_code(expected_mails):
    """Chờ đủ `expected_mails` email OTP; mã mới là mã chưa có trong lịch sử."""
    codes = [otp_of(t) for t in otp_mails("a@example.com", expected_mails)]
    fresh = [c for c in codes if c and c not in history]
    return fresh[0] if len(codes) == expected_mails and len(fresh) == 1 else None


def wrong_code():
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in history)


print("== Gửi lại ==")
for k in range(1, MAX_RESENDS + 1):
    time.sleep(COOLDOWN + 1)
    s, b = call(PAYMENT, "POST", f"/transactions/{txn}/otps", None, A)
    check(f"gửi lại lần {k} -> 201, resends_left = {MAX_RESENDS - k}, có otp_expires_at",
          s == 201 and b.get("resends_left") == MAX_RESENDS - k and b.get("otp_expires_at"), (s, b))
    fresh = new_code(k + 1)
    check(f"lần {k}: nhận đúng một email OTP mới, mã khác mọi mã trước", fresh is not None, history)
    if fresh:
        history.append(fresh)
    if k == 1:
        s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": wrong_code()}, A)
        check("nhập sai sau khi gửi lại -> 400 OTP_INVALID, còn 2 lần thử",
              s == 400 and b["error"]["details"].get("attempts_left") == 2, (s, b))
    if k == 2:
        s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": wrong_code()}, A)
        check("sau khi gửi lại, số lần nhập sai được TÍNH LẠI từ đầu (còn 2 lần thử)",
              s == 400 and b["error"]["details"].get("attempts_left") == 2, (s, b))

s, b = call(PAYMENT, "POST", f"/transactions/{txn}/otps", None, A)
check("vượt số lần gửi lại -> 429 OTP_RESEND_LIMIT", s == 429 and code(b) == "OTP_RESEND_LIMIT", (s, b))

print("== OTP gửi lại dùng được, OTP cũ bị thu hồi ==")
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": history[-2]}, A)
check("OTP của lần gửi lại trước (đã bị thu hồi) -> 400 OTP_INVALID", s == 400 and code(b) == "OTP_INVALID", (s, b))
before = balance(A)
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": history[-1]}, A)
check("xác nhận bằng OTP của lần gửi lại cuối -> 200 SUCCESS", s == 200 and b.get("status") == "SUCCESS", (s, b))
check("số dư A giảm đúng 1.000.000", before - balance(A) == 1000000, f"{before} -> {balance(A)}")
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/otps", None, A)
check("gửi lại khi giao dịch đã SUCCESS -> 409 TRANSACTION_NOT_PENDING",
      s == 409 and code(b) == "TRANSACTION_NOT_PENDING" and b["error"]["details"].get("status") == "SUCCESS", (s, b))
finish()
