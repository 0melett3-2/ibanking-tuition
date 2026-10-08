"""Kiểm tra POST /transactions khi Tuition TẮT (kết quả đúng: 503 DEPENDENCY_UNAVAILABLE, không để lại dòng nào).
Cách dùng:
  1) docker compose stop tuition
  2) python tests/check_dependency_down.py
  3) docker compose start tuition
Gọi Payment trực tiếp với tuition_id bất kỳ vì Payment gọi Tuition TRƯỚC khi ghi DB nên lỗi xảy ra sớm."""
import json
import urllib.error
import urllib.request

USER, PAYMENT = "http://127.0.0.1:8001", "http://127.0.0.1:8003"


def call(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


s, b = call(USER + "/auth/login", {"username": "nguyenvana", "password": "123456"})
token = {"Authorization": f"Bearer {b['access_token']}"}
s, b = call(PAYMENT + "/transactions", {"tuition_id": 7}, token)
code = b.get("error", {}).get("code")
print(f"HTTP {s}  {json.dumps(b, ensure_ascii=False)}")
print("[OK ] đúng kỳ vọng: 503 DEPENDENCY_UNAVAILABLE" if s == 503 and code == "DEPENDENCY_UNAVAILABLE"
      else "[FAIL] kỳ vọng 503 DEPENDENCY_UNAVAILABLE; Tuition đã tắt chưa (docker compose stop tuition)?")
