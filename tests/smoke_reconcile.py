"""Kiểm tra job đối soát (bước 9): python tests/smoke_reconcile.py
BẮT BUỘC đặt các dòng sau trong .env rồi chạy `docker compose up -d` (xong nhớ khôi phục mặc định):
    OTP_TTL_SECONDS=3
    TRANSACTION_EXPIRE_GRACE_SECONDS=6
    RECONCILE_STUCK_SECONDS=2
    RECONCILE_INTERVAL_SECONDS=3600     (tắt vòng lặp nền để script tự điều khiển thời điểm chạy job)
    OTP_RESEND_COOLDOWN_SECONDS=2
Ba kịch bản (khoảng 45 giây; kịch bản 2 và 3 cần lệnh `docker` để chỉnh DB và tắt/bật Tuition):
  1) OTP hết hạn -> giao dịch EXPIRED sau grace; vẫn gửi lại OTP được trong thời gian grace; được tạo giao dịch mới.
  2) Tiền đã trừ (DEBITED) nhưng Tuition chết -> job giữ DEBITED, Tuition sống lại -> job hoàn tất SUCCESS, đúng 1 email.
  3) Sập giữa chừng sau khi dùng OTP và giữ chỗ -> job đánh dấu FAILED và NHẢ giữ chỗ treo.
Mỗi lần chạy dùng 3 MSSV 52104001..52104012 và (kịch bản 2) trừ 1.000.000 của A."""
import pathlib
import shutil
import subprocess
import time
import urllib.request
from decimal import Decimal

from common import (MAILPIT, PAYMENT, TUITION, balance, call, check, clear_mailbox, code, env_value, finish, login,
                    otp_mails)

ROOT = pathlib.Path(__file__).resolve().parent.parent


def env_int(name, default):
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return int(line.split("=", 1)[1].strip())
    return default


TTL, GRACE = env_int("OTP_TTL_SECONDS", 300), env_int("TRANSACTION_EXPIRE_GRACE_SECONDS", 600)
STUCK, COOLDOWN = env_int("RECONCILE_STUCK_SECONDS", 60), env_int("OTP_RESEND_COOLDOWN_SECONDS", 60)
if not (TTL <= 10 and GRACE <= 20 and STUCK <= 10 and COOLDOWN <= 5):
    raise SystemExit(__doc__.split("Ba kịch bản")[0])

KEY = {"X-Internal-Key": env_value("INTERNAL_API_KEY")}
PGUSER = env_value("POSTGRES_USER")
HAS_DOCKER = shutil.which("docker") is not None
A = login("nguyenvana")


def reconcile():
    s, b = call(PAYMENT, "POST", "/internal/jobs/reconcile", None, KEY)
    assert s == 200, (s, b)
    return b


def txn_of(tid, h=A):
    return call(PAYMENT, "GET", f"/transactions/{tid}", headers=h)[1]


def psql(sql):
    r = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", PGUSER, "-d", "payment_db",
                        "-c", sql], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr


def fresh_txn():
    """Tạo giao dịch PENDING cho MSSV dự phòng đầu tiên còn tạo được (201)."""
    for i in range(1, 13):
        mssv = f"52104{i:03d}"
        s, t = call(TUITION, "GET", f"/students/{mssv}/tuition", headers=A)
        if s == 200 and t["status"] == "UNPAID":
            s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": t["tuition_id"]}, A)
            if s == 201:
                return t, b["transaction_id"]
    raise SystemExit("Hết MSSV 52104001..52104012 còn tạo được giao dịch: chờ giao dịch cũ hết hạn hoặc docker compose down -v")


def lookup(mssv):
    return call(TUITION, "GET", f"/students/{mssv}/tuition", headers=A)[1]


def wait_tuition_up(timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(TUITION + "/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def mails_with(subject_part, address="a@example.com"):
    s, b = call(MAILPIT, "GET", "/api/v1/messages")
    return [m for m in b.get("messages", []) if subject_part in m.get("Subject", "")
            and any(t.get("Address") == address for t in m.get("To", []))] if s == 200 else []


clear_mailbox()

print(f"== Kịch bản 1: hết hạn OTP (TTL={TTL}s, grace={GRACE}s) ==")
t1, tid1 = fresh_txn()
time.sleep(TTL + 1)
r = reconcile()
check("job đánh dấu OTP hết hạn (expired_otps >= 1)", r["expired_otps"] >= 1, r)
check("trong thời gian grace giao dịch VẪN PENDING (còn gửi lại OTP được)", txn_of(tid1).get("status") == "PENDING", txn_of(tid1))
s, b = call(PAYMENT, "POST", f"/transactions/{tid1}/otps", None, A)
check("OTP hết hạn nhưng trong grace: gửi lại OTP -> 201 (UC08)", s == 201, (s, b))
time.sleep(TTL + GRACE + 1)
r = reconcile()
tx = txn_of(tid1)
check("quá grace: giao dịch -> EXPIRED, fail_reason OTP_EXPIRED",
      tx.get("status") == "EXPIRED" and tx.get("fail_reason") == "OTP_EXPIRED", tx)
s, b = call(PAYMENT, "POST", f"/transactions/{tid1}/confirm", {"otp": "123456"}, A)
check("xác nhận giao dịch EXPIRED -> 409 TRANSACTION_NOT_PENDING (status EXPIRED)",
      s == 409 and code(b) == "TRANSACTION_NOT_PENDING" and b["error"]["details"].get("status") == "EXPIRED", (s, b))
s, b = call(PAYMENT, "POST", f"/transactions/{tid1}/otps", None, A)
check("gửi lại OTP cho giao dịch EXPIRED -> 409", s == 409 and code(b) == "TRANSACTION_NOT_PENDING", (s, b))
s, b = call(PAYMENT, "POST", "/transactions", {"tuition_id": t1["tuition_id"]}, A)
check("giao dịch cũ hết hạn không còn chặn: tạo giao dịch mới cho cùng học phí -> 201", s == 201, (s, b))

if not HAS_DOCKER:
    print("\n[SKIP] không có lệnh `docker` trong PATH nên bỏ qua kịch bản 2 và 3.")
    finish()

print("== Kịch bản 2: đã trừ tiền (DEBITED) nhưng Tuition chết ==")
t2, tid2 = fresh_txn()
amount = Decimal(txn_of(tid2)["amount"])
s, b = call(TUITION, "POST", f"/tuitions/{t2['tuition_id']}/reservation", {"transaction_id": tid2}, KEY)
check("dựng tình huống: học phí đã giữ chỗ cho giao dịch", s == 200, (s, b))
ok, out = psql(f"UPDATE otps SET status='USED' WHERE transaction_id={tid2} AND status='ACTIVE'; "
               f"UPDATE accounts SET balance = balance - {amount} WHERE user_id = 1; "
               f"UPDATE transactions SET status='DEBITED' WHERE id = {tid2};")
check("dựng tình huống: tiền đã trừ, giao dịch DEBITED (mô phỏng sập ngay sau khi commit)", ok, out)
bal = balance(A)
subprocess.run(["docker", "compose", "stop", "tuition"], cwd=ROOT, capture_output=True)
try:
    reconcile()
    check("Tuition đang tắt: giao dịch GIỮ DEBITED, không mất dữ liệu", txn_of(tid2).get("status") == "DEBITED", txn_of(tid2))
    check("Tuition đang tắt: số dư không đổi", balance(A) == bal)
finally:
    subprocess.run(["docker", "compose", "start", "tuition"], cwd=ROOT, capture_output=True)
check("Tuition khởi động lại và khỏe", wait_tuition_up())
reconcile()
tx = txn_of(tid2)
check("Tuition hồi phục: job hoàn tất giao dịch -> SUCCESS", tx.get("status") == "SUCCESS" and tx.get("completed_at"), tx)
check("học phí chuyển PAID", lookup(t2["student_code"]).get("status") == "PAID")
check("số dư không bị trừ lần hai", balance(A) == bal, balance(A))
reconcile()
reconcile()
time.sleep(2)
texts = [call(MAILPIT, "GET", f"/api/v1/message/{m['ID']}")[1].get("Text", "") for m in mails_with("thành công")]
check("đúng MỘT email xác nhận cho giao dịch (chạy job nhiều lần không gửi trùng)",
      sum(1 for t in texts if f"Mã giao dịch: {tid2}" in t) == 1, [t[:60] for t in texts])

print("== Kịch bản 3: sập giữa chừng sau khi dùng OTP và giữ chỗ ==")
t3, tid3 = fresh_txn()
s, b = call(TUITION, "POST", f"/tuitions/{t3['tuition_id']}/reservation", {"transaction_id": tid3}, KEY)
ok, out = psql(f"UPDATE otps SET status='USED' WHERE transaction_id={tid3} AND status='ACTIVE';")
check("dựng tình huống: OTP đã dùng, học phí đang bị giữ chỗ", s == 200 and ok, (s, b, out))
check("trước khi chạy job: học phí đang RESERVED", lookup(t3["student_code"]).get("status") == "RESERVED")
bal3 = balance(A)
time.sleep(TTL + STUCK + 1)
r = reconcile()
tx = txn_of(tid3)
check("giao dịch treo -> FAILED, fail_reason PROCESSING_INTERRUPTED",
      tx.get("status") == "FAILED" and tx.get("fail_reason") == "PROCESSING_INTERRUPTED", tx)
check("giữ chỗ treo được NHẢ: học phí về UNPAID", lookup(t3["student_code"]).get("status") == "UNPAID",
      lookup(t3["student_code"]))
check("số dư không đổi", balance(A) == bal3)
finish()
