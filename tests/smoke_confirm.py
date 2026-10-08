"""Kiểm tra bước 4-5 của Payment: thanh toán trọn vẹn (mốc 3) và lịch sử giao dịch.
Chạy: python tests/smoke_confirm.py   (cần chế độ DEV: User :8001, Tuition :8002, Payment :8003, Mailpit :8025)

MỖI LẦN CHẠY thanh toán xong (PAID) một MSSV dự phòng 52108001..52108008 và trừ 1.000.000 của người dùng A.
Hết MSSV dự phòng hoặc muốn trả lại số dư 20.000.000 cho demo: docker compose down -v rồi up --build."""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal

USER, TUITION, PAYMENT, MAILPIT = ("http://127.0.0.1:8001", "http://127.0.0.1:8002",
                                   "http://127.0.0.1:8003", "http://127.0.0.1:8025")


def call(base, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else {})


results = []


def check(name, cond, extra=""):
    cond = bool(cond)
    results.append(cond)
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {extra}"))


def code(b):
    return b.get("error", {}).get("code")


def login(username):
    s, b = call(USER, "POST", "/auth/login", {"username": username, "password": "123456"})
    if s != 200:
        raise SystemExit(f"Không đăng nhập được {username}: chạy tests/smoke_user.py trước")
    return {"Authorization": f"Bearer {b['access_token']}"}


def mails(address):
    s, b = call(MAILPIT, "GET", "/api/v1/messages")
    return [m for m in b.get("messages", []) if any(t.get("Address") == address for t in m.get("To", []))] if s == 200 else []


def wait_mail(address, subject_part, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        for m in mails(address):
            if subject_part in m.get("Subject", ""):
                return call(MAILPIT, "GET", f"/api/v1/message/{m['ID']}")[1].get("Text", "")
        time.sleep(0.5)
    return None


def balance(h):
    return Decimal(call(PAYMENT, "GET", "/accounts/me", headers=h)[1]["balance"])


A, B = login("nguyenvana"), login("lethib")

# chọn một MSSV dự phòng còn UNPAID
mssv = tid = None
for i in range(1, 9):
    s, b = call(TUITION, "GET", f"/students/5210800{i}/tuition", headers=A)
    if s == 200 and b["status"] == "UNPAID":
        mssv, tid = b["student_code"], b["tuition_id"]
        break
if mssv is None:
    raise SystemExit("Hết MSSV dự phòng 52108001..52108008: docker compose down -v rồi up --build")
print(f"Dùng MSSV dự phòng {mssv} (tuition_id={tid})")

try:
    call(MAILPIT, "DELETE", "/api/v1/messages")
except Exception:
    pass
before = balance(A)

print("== Tạo giao dịch ==")
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid}, A)
txn = b.get("transaction_id")
check("A tạo giao dịch -> 201 PENDING", s == 201 and b.get("status") == "PENDING", (s, b))
text = wait_mail("a@example.com", "OTP")
m = re.search(r"\b(\d{6})\b", text or "")
check("nhận được email OTP", m is not None, text)
otp_code = m.group(1) if m else "000000"

print("== Trước khi xác nhận ==")
s, b = call(PAYMENT, "GET", f"/transactions/{txn}", headers=A)
check("A xem giao dịch -> 200 PENDING, có tuition_id", s == 200 and b.get("status") == "PENDING" and b.get("tuition_id") == tid, (s, b))
s, b = call(PAYMENT, "GET", f"/transactions/{txn}", headers=B)
check("B xem giao dịch của A -> 404 TRANSACTION_NOT_FOUND", s == 404 and code(b) == "TRANSACTION_NOT_FOUND", (s, b))
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": otp_code}, B)
check("B xác nhận giao dịch của A -> 404", s == 404 and code(b) == "TRANSACTION_NOT_FOUND", (s, b))
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": "12ab"}, A)
check("OTP sai định dạng -> 422 VALIDATION_ERROR", s == 422 and code(b) == "VALIDATION_ERROR", (s, b))
wrong = "000000" if otp_code != "000000" else "000001"
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": wrong}, A)
check("OTP sai -> 400 OTP_INVALID, còn 2 lần thử",
      s == 400 and code(b) == "OTP_INVALID" and b["error"]["details"].get("attempts_left") == 2, (s, b))
check("OTP sai không làm đổi số dư", balance(A) == before)

print("== Thanh toán trọn vẹn (mốc 3) ==")
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": otp_code}, A)
check("OTP đúng -> 200 SUCCESS, amount '1000000.00', có completed_at",
      s == 200 and b.get("status") == "SUCCESS" and b.get("amount") == "1000000.00" and b.get("completed_at"), (s, b))
after = balance(A)
check("số dư A giảm đúng 1.000.000", before - after == Decimal("1000000.00"), f"{before} -> {after}")
s, b = call(TUITION, "GET", f"/students/{mssv}/tuition", headers=A)
check("học phí chuyển PAID", s == 200 and b.get("status") == "PAID", (s, b))
s, b = call(PAYMENT, "GET", f"/transactions/{txn}", headers=A)
check("giao dịch SUCCESS và có completed_at", s == 200 and b.get("status") == "SUCCESS" and b.get("completed_at"), (s, b))
s, b = call(PAYMENT, "POST", f"/transactions/{txn}/confirm", {"otp": otp_code}, A)
check("xác nhận lại -> 200 SUCCESS (idempotent)", s == 200 and b.get("status") == "SUCCESS", (s, b))
check("xác nhận lại KHÔNG trừ tiền lần hai", balance(A) == after, f"{after} -> {balance(A)}")
confirm_text = wait_mail("a@example.com", "thành công")
check("email xác nhận thành công có mã giao dịch và MSSV",
      confirm_text is not None and str(txn) in confirm_text and mssv in confirm_text, confirm_text)
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid}, A)
check("tạo giao dịch cho học phí đã PAID -> 409 TUITION_NOT_AVAILABLE", s == 409 and code(b) == "TUITION_NOT_AVAILABLE", (s, b))

print("== Lịch sử giao dịch ==")
s, b = call(PAYMENT, "GET", "/transactions", headers=A)
items = b.get("items", [])
check("danh sách -> 200, giao dịch mới nhất đứng đầu",
      s == 200 and items and items[0]["transaction_id"] == txn and b["total"] >= 1, (s, b))
check("mục danh sách có đủ trường theo hợp đồng và không có tuition_id",
      items and {"transaction_id", "student_code", "student_name", "amount", "status", "fail_reason",
                 "created_at", "completed_at"} <= set(items[0]) and "tuition_id" not in items[0], items[:1])
s, b = call(PAYMENT, "GET", "/transactions?page=1&page_size=1", headers=A)
check("page_size=1 -> đúng 1 mục, total giữ nguyên", s == 200 and len(b["items"]) == 1 and b["page_size"] == 1, (s, b))
s, b = call(PAYMENT, "GET", "/transactions?status=SUCCESS", headers=A)
check("lọc status=SUCCESS -> chỉ còn SUCCESS", s == 200 and b["items"] and all(i["status"] == "SUCCESS" for i in b["items"]), (s, b))
s, b = call(PAYMENT, "GET", "/transactions?status=BOGUS", headers=A)
check("status không hợp lệ -> 422 VALIDATION_ERROR", s == 422 and code(b) == "VALIDATION_ERROR", (s, b))
s, b = call(PAYMENT, "GET", "/transactions", headers=B)
check("B không thấy giao dịch của A", s == 200 and all(i["transaction_id"] != txn for i in b["items"]), (s, b))
s, b = call(PAYMENT, "GET", "/transactions")
check("không token -> 401", s == 401, (s, b))

print(f"\n{sum(results)}/{len(results)} kiểm tra đạt")
sys.exit(0 if all(results) else 1)
