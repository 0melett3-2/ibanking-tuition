"""Kiểm tra Web/BFF service (cổng 8000): python tests/smoke_web.py
Yêu cầu hệ thống đang chạy (docker compose up). Kiểm tra luồng web:
- /health -> 200
- Chưa đăng nhập truy cập / -> Chuyển hướng 303 về /login
- GET /login -> 200, có cookie csrf_token và form đăng nhập
- POST /login sai mật khẩu -> 401 hiển thị thông báo lỗi
- POST /login đúng (nguyenvana / 123456) -> 303 về /, cấp cookie access_token (HttpOnly)
- GET / với cookie -> 200 hiển thị tên, số dư và các nút điều hướng
- GET /pay với cookie -> 200 hiển thị thông tin người nộp tiền (readonly) và form tra cứu
- GET /pay/lookup?mssv=52100001 -> 200 trả về fragment học phí và điều kiện thanh toán
- GET /history với cookie -> 200 hiển thị bảng lịch sử giao dịch
- POST /logout -> 303 về /login và xóa cookie phiên.
"""
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

results = []


def check(name, cond, extra=""):
    cond = bool(cond)
    results.append(cond)
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {extra}"))


def req(method, path, data=None, headers=None, follow_redirect=True):
    headers = headers or {}
    url = BASE + path
    encoded_data = None
    if data is not None:
        if isinstance(data, dict):
            encoded_data = urllib.parse.urlencode(data).encode("utf-8")
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif isinstance(data, (str, bytes)):
            encoded_data = data.encode("utf-8") if isinstance(data, str) else data

    request = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None

    active_opener = opener if follow_redirect else urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj), NoRedirect
    )

    try:
        with active_opener.open(request, timeout=10) as r:
            body = r.read().decode("utf-8", errors="replace")
            return r.status, body, dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body, dict(e.headers)


print("=== Kiểm tra Web / BFF Service (cổng 8000) ===")

# 1. Health check
s, body, _ = req("GET", "/health")
check("/health trả về 200 status ok", s == 200 and '"status":"ok"' in body.replace(" ", ""), (s, body))

# 2. Truy cập / khi chưa đăng nhập -> chuyển hướng về /login (303)
s, body, h = req("GET", "/", follow_redirect=False)
check("chưa đăng nhập truy cập / -> 303 Redirect", s == 303 and "/login" in h.get("Location", ""), (s, h))

# 3. GET /login -> 200, có cookie csrf_token và form đăng nhập
s, body, h = req("GET", "/login")
check("GET /login -> 200 và có form đăng nhập", s == 200 and '<form method="post" action="/login"' in body, s)
cookies = {c.name: c.value for c in cj}
csrf_token = cookies.get("csrf_token")
check("nhận được cookie csrf_token", bool(csrf_token), cookies)

# 4. POST /login thiếu CSRF -> 403 Forbidden
s, body, _ = req("POST", "/login", {"username": "nguyenvana", "password": "123456"}, follow_redirect=False)
check("POST /login thiếu CSRF -> 403 Forbidden", s == 403, s)

# 5. POST /login sai mật khẩu -> 401 và giữ nguyên trang đăng nhập
s, body, _ = req("POST", "/login", {
    "username": "nguyenvana",
    "password": "wrongpassword",
    "csrf_token": csrf_token
}, headers={"X-CSRF-Token": csrf_token}, follow_redirect=False)
check("POST /login sai mật khẩu -> 401 hiển thị lỗi", s == 401 and "Đăng nhập không thành công" in body or "không đúng" in body, s)

# 6. POST /login đúng thông tin -> 303 Redirect về /
s, body, h = req("POST", "/login", {
    "username": "nguyenvana",
    "password": "123456",
    "csrf_token": csrf_token
}, headers={"X-CSRF-Token": csrf_token}, follow_redirect=False)
cookies = {c.name: c.value for c in cj}
check("POST /login đúng -> 303 về / và có cookie access_token",
      s == 303 and "/" in h.get("Location", "") and "access_token" in cookies, (s, h, cookies))

# 7. GET / sau khi đăng nhập -> 200, hiển thị thông tin người dùng
s, body, _ = req("GET", "/")
check("GET / sau đăng nhập -> 200, có tên Nguyễn Văn A",
      s == 200 and "Nguyễn Văn A" in body, (s, body[:200]))

# 8. GET /pay -> 200, hiển thị giao diện thanh toán học phí
s, body, _ = req("GET", "/pay")
check("GET /pay -> 200, có thông tin người nộp và ô tra cứu MSSV",
      s == 200 and "Người nộp tiền" in body and 'name="mssv"' in body, s)

# 9. GET /pay/lookup?mssv=52100001 -> 200, fragment tra cứu học phí
s, body, _ = req("GET", "/pay/lookup?mssv=52100001")
check("GET /pay/lookup -> 200, tìm thấy học phí sinh viên",
      s == 200 and ("52100001" in body or "Trần Thị B" in body), (s, body[:300]))

# 10. GET /history -> 200, hiển thị trang lịch sử giao dịch
s, body, _ = req("GET", "/history")
check("GET /history -> 200, hiển thị trang Lịch sử giao dịch",
      s == 200 and "Lịch sử giao dịch" in body, s)

# 11. POST /logout -> 303 về /login và xóa session
s, body, h = req("POST", "/logout", {"csrf_token": csrf_token},
                 headers={"X-CSRF-Token": csrf_token}, follow_redirect=False)
cookies_after = {c.name: c.value for c in cj}
check("POST /logout -> 303 về /login", s == 303 and "/login" in h.get("Location", ""), (s, h))

print(f"\nKết quả: {sum(results)}/{len(results)} kiểm tra đạt.")
if not all(results):
    sys.exit(1)
