"""Kiểm tra Tuition service (chế độ DEV: User :8001, Tuition :8002): python tests/smoke_tuition.py
Dùng hai sinh viên kiểm thử 52109999 (luồng đầy đủ) và 52109998 (đồng thời), KHÔNG đụng dữ liệu demo.
Bước thanh toán xong (PAID) là không đảo ngược: chạy lại lần sau sẽ bỏ qua bước đó;
muốn làm mới: docker compose down -v rồi docker compose up --build."""
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

USER, TUITION = "http://127.0.0.1:8001", "http://127.0.0.1:8002"


def env_value(name):
    for line in (pathlib.Path(__file__).resolve().parent.parent / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"Không thấy {name} trong .env")


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


KEY = {"X-Internal-Key": env_value("INTERNAL_API_KEY")}
s, b = call(USER, "POST", "/auth/login", {"username": "nguyenvana", "password": "123456"})
if s != 200:
    raise SystemExit(f"Không đăng nhập được User service ({s}): hãy chạy tests/smoke_user.py trước")
JWT = {"Authorization": f"Bearer {b['access_token']}"}


def lookup(mssv):
    return call(TUITION, "GET", f"/students/{mssv}/tuition", headers=JWT)


def reserve(tid, txn):
    return call(TUITION, "POST", f"/tuitions/{tid}/reservation", {"transaction_id": txn}, KEY)


def release(tid, txn):
    return call(TUITION, "DELETE", f"/tuitions/{tid}/reservation?transaction_id={txn}", headers=KEY)


def pay(tid, txn):
    return call(TUITION, "POST", f"/tuitions/{tid}/payment", {"transaction_id": txn}, KEY)


print("== Tra cứu ==")
s, b = call(TUITION, "GET", "/students/52100001/tuition")
check("tra cứu không token -> 401", s == 401, (s, b))
s, b = lookup("52100001")
check("52100001 -> 200, UNPAID, amount là chuỗi '15000000.00'",
      s == 200 and b.get("status") == "UNPAID" and b.get("amount") == "15000000.00", (s, b))
s, b = lookup("52100002")
check("52100002 đã trả -> vẫn 200 với status PAID (không phải 409)", s == 200 and b.get("status") == "PAID", (s, b))
s, b = lookup("00000000")
check("MSSV không tồn tại -> 404 STUDENT_NOT_FOUND", s == 404 and code(b) == "STUDENT_NOT_FOUND", (s, b))
s, b = lookup("52100005")
check("sinh viên chưa có học phí -> 404 TUITION_NOT_FOUND", s == 404 and code(b) == "TUITION_NOT_FOUND", (s, b))
s, b = lookup("52109999")
tid = b["tuition_id"]
s, b = call(TUITION, "GET", f"/tuitions/{tid}")
check("GET /tuitions/{id} không có khóa nội bộ -> 401", s == 401, (s, b))
s, b = call(TUITION, "GET", f"/tuitions/{tid}", headers=KEY)
check("GET /tuitions/{id} có khóa nội bộ -> 200, có reserved_by", s == 200 and "reserved_by" in b, (s, b))
s, b = call(TUITION, "GET", "/tuitions/999999", headers=KEY)
check("học phí không tồn tại -> 404 TUITION_NOT_FOUND", s == 404 and code(b) == "TUITION_NOT_FOUND", (s, b))

print("== Luồng giữ chỗ -> thanh toán (sinh viên 52109999) ==")
already_paid = lookup("52109999")[1]["status"] == "PAID"
if already_paid:
    print("[SKIP] 52109999 đã PAID từ lần chạy trước (docker compose down -v để làm mới)")
else:
    for t in (9001, 9002, 9003):
        release(tid, t)  # dọn dẹp nếu lần chạy trước bị dừng giữa chừng
    s, b = reserve(tid, 9001)
    check("giữ chỗ lần đầu -> 200 RESERVED, reserved_by=9001",
          s == 200 and b.get("status") == "RESERVED" and b.get("reserved_by") == 9001, (s, b))
    s, b = reserve(tid, 9001)
    check("giữ chỗ lại cùng giao dịch -> 200 (idempotent)", s == 200, (s, b))
    s, b = reserve(tid, 9002)
    check("giao dịch khác giữ chỗ -> 409 TUITION_NOT_AVAILABLE", s == 409 and code(b) == "TUITION_NOT_AVAILABLE", (s, b))
    check("tra cứu thấy RESERVED", lookup("52109999")[1].get("status") == "RESERVED")
    s, b = release(tid, 9002)
    check("giao dịch khác nhả chỗ -> 204 nhưng KHÔNG nhả được",
          s == 204 and lookup("52109999")[1].get("status") == "RESERVED", (s, b))
    s, b = pay(tid, 9002)
    check("xác nhận bởi giao dịch không giữ chỗ -> 409 RESERVATION_MISMATCH",
          s == 409 and code(b) == "RESERVATION_MISMATCH", (s, b))
    s, b = release(tid, 9001)
    check("chủ giữ chỗ nhả -> 204 và học phí về UNPAID",
          s == 204 and lookup("52109999")[1].get("status") == "UNPAID", (s, b))
    s, b = reserve(tid, 9003)
    s2, b2 = pay(tid, 9003)
    check("giữ chỗ rồi xác nhận -> 200 PAID", s == 200 and s2 == 200 and b2.get("status") == "PAID", (s, b, s2, b2))
    s, b = pay(tid, 9003)
    check("xác nhận lại -> 200 (idempotent)", s == 200 and b.get("status") == "PAID", (s, b))
    s, b = release(tid, 9003)
    check("nhả chỗ khi đã PAID -> 409 TUITION_ALREADY_PAID", s == 409 and code(b) == "TUITION_ALREADY_PAID", (s, b))
    s, b = reserve(tid, 9004)
    check("giữ chỗ khi đã PAID -> 409 TUITION_NOT_AVAILABLE", s == 409 and code(b) == "TUITION_NOT_AVAILABLE", (s, b))

print("== Đồng thời: 10 giao dịch cùng giữ chỗ một học phí (sinh viên 52109998) ==")
tid2 = lookup("52109998")[1]["tuition_id"]
for t in range(9101, 9111):
    release(tid2, t)
barrier = threading.Barrier(10)


def attempt(txn):
    barrier.wait()  # cả 10 luồng cùng xuất phát
    return txn, reserve(tid2, txn)


with ThreadPoolExecutor(max_workers=10) as pool:
    outcomes = list(pool.map(attempt, range(9101, 9111)))
winners = [t for t, (s, _) in outcomes if s == 200]
losers = [t for t, (s, b) in outcomes if s == 409 and code(b) == "TUITION_NOT_AVAILABLE"]
check("đúng 1 giao dịch thắng và 9 giao dịch còn lại nhận 409", len(winners) == 1 and len(losers) == 9,
      f"thắng={winners}, thua={losers}")
state = call(TUITION, "GET", f"/tuitions/{tid2}", headers=KEY)[1]
check("reserved_by trùng với người thắng", len(winners) == 1 and state.get("reserved_by") == winners[0], state)
for t in winners:
    release(tid2, t)
check("nhả chỗ xong học phí về UNPAID (chạy lại được)", lookup("52109998")[1].get("status") == "UNPAID")

print(f"\n{sum(results)}/{len(results)} kiểm tra đạt")
sys.exit(0 if all(results) else 1)
