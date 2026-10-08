"""Kiểm tra Payment bước 1-3 (chế độ DEV): python tests/smoke_payment.py
Cần User :8001, Tuition :8002, Payment :8003 và Mailpit :8025. Dùng sinh viên kiểm thử 52109998.
Giao dịch PENDING tạo ra tồn tại tới khi hết hạn (chưa có job đối soát): chạy lại ngay sẽ nhận 200 (giao dịch cũ)
và bỏ qua phần kiểm tra email; muốn làm mới hoàn toàn: docker compose down -v rồi up --build."""
import json
import re
import sys
import time
import urllib.error
import urllib.request

USER, TUITION, PAYMENT, MAILPIT = ("http://127.0.0.1:8001", "http://127.0.0.1:8002",
                                   "http://127.0.0.1:8003", "http://127.0.0.1:8025")


def call(base, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else {})


results = []


def check(name, cond, extra=""):
    cond = bool(cond)  # điều kiện có thể trả về chuỗi/dict khi dùng 'and' nối nhiều vế
    results.append(cond)
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {extra}"))


def code(b):
    return b.get("error", {}).get("code")


def login(username):
    s, b = call(USER, "POST", "/auth/login", {"username": username, "password": "123456"})
    if s != 200:
        raise SystemExit(f"Không đăng nhập được {username} ({s}): chạy tests/smoke_user.py trước")
    return {"Authorization": f"Bearer {b['access_token']}"}


def mailbox_for(address):
    s, b = call(MAILPIT, "GET", "/api/v1/messages")
    if s != 200:
        return []
    return [m for m in b.get("messages", []) if any(t.get("Address") == address for t in m.get("To", []))]


A, B, C = login("nguyenvana"), login("lethib"), login("phamvanc")
tid = call(TUITION, "GET", "/students/52109998/tuition", headers=A)[1]["tuition_id"]
paid_tid = call(TUITION, "GET", "/students/52100002/tuition", headers=A)[1]["tuition_id"]
big_tid = call(TUITION, "GET", "/students/52100001/tuition", headers=A)[1]["tuition_id"]

print("== Tài khoản ==")
s, b = call(PAYMENT, "GET", "/accounts/me")
check("không token -> 401", s == 401, (s, b))
s, b = call(PAYMENT, "GET", "/accounts/me", headers=A)
check("A: 200, user_id=1, balance là chuỗi '20000000.00'",
      s == 200 and b.get("user_id") == 1 and b.get("balance") == "20000000.00", (s, b))
s, b = call(PAYMENT, "GET", "/accounts/me", headers=C)
check("C: balance '1000000.00'", s == 200 and b.get("balance") == "1000000.00", (s, b))

print("== Các trường hợp bị từ chối khi tạo giao dịch ==")
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid})
check("không token -> 401", s == 401, (s, b))
s, b = call(PAYMENT, "POST", "/transactions", {}, A)
check("thiếu tuition_id -> 422 VALIDATION_ERROR", s == 422 and code(b) == "VALIDATION_ERROR", (s, b))
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": 999999}, A)
check("học phí không tồn tại -> 404 TUITION_NOT_FOUND", s == 404 and code(b) == "TUITION_NOT_FOUND", (s, b))
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": paid_tid}, A)
check("học phí đã PAID -> 409 TUITION_NOT_AVAILABLE", s == 409 and code(b) == "TUITION_NOT_AVAILABLE", (s, b))
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": big_tid}, C)
check("C thiếu số dư (1tr < 15tr) -> 422 INSUFFICIENT_BALANCE", s == 422 and code(b) == "INSUFFICIENT_BALANCE", (s, b))

print("== Tạo giao dịch và OTP ==")
try:
    call(MAILPIT, "DELETE", "/api/v1/messages")  # xóa hộp thư để dễ đối chiếu
except Exception:
    pass
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid}, A)
fresh = s == 201
check("A tạo giao dịch -> 201 hoặc 200 (giao dịch cũ), trạng thái PENDING, amount '1000000.00'",
      s in (200, 201) and b.get("status") == "PENDING" and b.get("amount") == "1000000.00"
      and isinstance(b.get("transaction_id"), int) and b.get("otp_expires_at"), (s, b))
txn_id = b.get("transaction_id")

if fresh:
    msgs = []
    for _ in range(10):  # email gửi nền, chờ tối đa ~5 giây
        msgs = mailbox_for("a@example.com")
        if msgs:
            break
        time.sleep(0.5)
    check("email OTP tới a@example.com xuất hiện trong Mailpit", len(msgs) == 1, f"{len(msgs)} thư")
    if msgs:
        s, m = call(MAILPIT, "GET", f"/api/v1/message/{msgs[0]['ID']}")
        text = m.get("Text", "")
        check("nội dung thư có mã OTP 6 chữ số và MSSV 52109998",
              re.search(r"\b\d{6}\b", text) is not None and "52109998" in text, text[:200])
else:
    print("[SKIP] giao dịch PENDING từ lần chạy trước còn đó nên không có email mới (docker compose down -v để làm mới)")

before = len(mailbox_for("a@example.com"))
s, b2 = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid}, A)
time.sleep(1.5)
check("A bấm đúp -> 200 cùng transaction_id, không sinh OTP/email mới",
      s == 200 and b2.get("transaction_id") == txn_id and len(mailbox_for("a@example.com")) == before, (s, b2))
s, b3 = call(PAYMENT, "POST", "/transactions", {"tuition_id": tid}, B)
check("B cùng học phí vẫn tạo được giao dịch riêng (khác transaction_id)",
      s in (200, 201) and b3.get("transaction_id") not in (None, txn_id), (s, b3))

print(f"\n{sum(results)}/{len(results)} kiểm tra đạt")
sys.exit(0 if all(results) else 1)
