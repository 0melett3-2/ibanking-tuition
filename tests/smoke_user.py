"""Kiểm tra User service đang chạy ở chế độ DEV (cổng 8001): python tests/smoke_user.py
Đọc INTERNAL_API_KEY từ file .env ở gốc repo. Dữ liệu mẫu: nguyenvana / lethib / phamvanc, mật khẩu 123456."""
import json
import pathlib
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"


def env_value(name: str) -> str:
    for line in (pathlib.Path(__file__).resolve().parent.parent / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"Không thấy {name} trong .env")


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


results = []


def check(name, cond, extra=""):
    cond = bool(cond)  # điều kiện có thể trả về chuỗi/dict khi dùng 'and' nối nhiều vế
    results.append(cond)
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {extra}"))


key = {"X-Internal-Key": env_value("INTERNAL_API_KEY")}
s, b = call("POST", "/auth/login", {"username": "nguyenvana", "password": "123456"})
check("đăng nhập đúng -> 200 và có access_token", s == 200 and "access_token" in b, (s, b))
token = {"Authorization": f"Bearer {b.get('access_token', '')}"}

s, b2 = call("POST", "/auth/login", {"username": "nguyenvana", "password": "sai"})
check("sai mật khẩu -> 401 INVALID_CREDENTIALS", s == 401 and b2["error"]["code"] == "INVALID_CREDENTIALS", (s, b2))
s, b3 = call("POST", "/auth/login", {"username": "khongton", "password": "123456"})
check("username không tồn tại -> cùng 401 và cùng thông báo",
      s == 401 and b3["error"]["message"] == b2["error"]["message"], (s, b3))
s, b4 = call("POST", "/auth/login", {})
check("thiếu dữ liệu -> 422 VALIDATION_ERROR", s == 422 and b4["error"]["code"] == "VALIDATION_ERROR", (s, b4))

s, me = call("GET", "/users/me", headers=token)
check("/users/me với token -> 200, đúng người dùng", s == 200 and me.get("username") == "nguyenvana", (s, me))
s, e = call("GET", "/users/me")
check("/users/me không token -> 401 UNAUTHORIZED", s == 401 and e["error"]["code"] == "UNAUTHORIZED", (s, e))

s, e = call("GET", "/users/1")
check("/users/1 không có khóa nội bộ -> 401", s == 401, (s, e))
s, u = call("GET", "/users/1", headers=key)
check("/users/1 có khóa nội bộ -> 200, có email", s == 200 and u.get("email") == "a@example.com", (s, u))
s, e = call("GET", "/users/999", headers=key)
check("/users/999 -> 404 USER_NOT_FOUND", s == 404 and e["error"]["code"] == "USER_NOT_FOUND", (s, e))

print(f"\n{sum(results)}/{len(results)} kiểm tra đạt")
sys.exit(0 if all(results) else 1)
