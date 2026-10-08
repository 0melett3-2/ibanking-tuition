"""Hàm dùng chung cho các script đồng thời (concurrency_seq3.py, concurrency_seq4.py)."""
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal

USER, TUITION, PAYMENT, MAILPIT = ("http://127.0.0.1:8001", "http://127.0.0.1:8002",
                                   "http://127.0.0.1:8003", "http://127.0.0.1:8025")
results = []


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
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else {})


def check(name, cond, extra=""):
    cond = bool(cond)
    results.append(cond)
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {extra}"))


def code(b):
    return b.get("error", {}).get("code")


def login(username, password="123456"):
    s, b = call(USER, "POST", "/auth/login", {"username": username, "password": password})
    if s != 200:
        raise SystemExit(f"Không đăng nhập được {username} ({s}): kiểm tra User service và dữ liệu mẫu")
    return {"Authorization": f"Bearer {b['access_token']}"}


def balance(h):
    return Decimal(call(PAYMENT, "GET", "/accounts/me", headers=h)[1]["balance"])


def clear_mailbox():
    try:
        call(MAILPIT, "DELETE", "/api/v1/messages")
    except Exception:
        pass


def otp_mails(address, count, timeout=10):
    """Chờ đủ `count` email OTP gửi tới `address`; trả về danh sách nội dung (Text)."""
    end = time.time() + timeout
    texts = []
    while time.time() < end:
        s, b = call(MAILPIT, "GET", "/api/v1/messages")
        msgs = [m for m in b.get("messages", []) if s == 200 and "OTP" in m.get("Subject", "")
                and any(t.get("Address") == address for t in m.get("To", []))]
        if len(msgs) >= count:
            texts = [call(MAILPIT, "GET", f"/api/v1/message/{m['ID']}")[1].get("Text", "") for m in msgs]
            return texts
        time.sleep(0.5)
    return texts


def otp_of(text):
    m = re.search(r"Mã OTP của bạn: (\d{6})", text or "")
    return m.group(1) if m else None


def finish():
    print(f"\n{sum(results)}/{len(results)} kiểm tra đạt")
    sys.exit(0 if all(results) else 1)
