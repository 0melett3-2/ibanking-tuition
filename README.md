# iBanking – Phân hệ đóng học phí (CS504070, HK1/2026-2027)

Kiến trúc Microservices: **Web/BFF** (Jinja2 + HTMX + Tailwind) gọi **User**, **Tuition**, **Payment** (FastAPI + SQLAlchemy)
trên một PostgreSQL (3 database riêng) và Mailpit (SMTP giả để xem OTP, email). Chi tiết: `docs/diagrams/arch-v3.png`.

## Chạy nhanh

Yêu cầu: Docker Desktop (có `docker compose`).

```bash
cp .env.example .env              # Windows PowerShell: Copy-Item .env.example .env   rồi đổi các giá trị change-me
docker compose up --build         # chế độ DEV: tự reload khi sửa code, mở cổng Swagger
python tests/smoke_health.py --dev
```

| Thành phần | Địa chỉ | Ghi chú |
|---|---|---|
| Web | http://localhost:8000 | Cổng duy nhất của ứng dụng mở ra ngoài |
| Mailpit (xem email OTP) | http://localhost:8025 | SMTP `:1025` chỉ trong mạng nội bộ |
| Swagger User / Tuition / Payment | http://localhost:8001/docs, :8002/docs, :8003/docs | Chỉ ở chế độ DEV |
| PostgreSQL | localhost:5432 (user/password trong `.env`) | Chỉ ở chế độ DEV |

**Chế độ DEMO** (đúng như sơ đồ kiến trúc: chỉ Web và Mailpit mở cổng, không reload):

```bash
docker compose -f docker-compose.yml up --build
```

Các lệnh hay dùng: `docker compose logs -f payment` (xem log) · `docker compose down` (dừng) ·
`docker compose down -v` (dừng và **xóa sạch dữ liệu**, cần khi sửa `db/init/*.sql`).

Hiện tại mọi endpoint nghiệp vụ trả `501 NOT_IMPLEMENTED` (khung theo hợp đồng API); chỉ `/health` chạy thật.
Mở Swagger là thấy đủ endpoint, request và response.

## Tài khoản mẫu

User service tự nạp 3 người dùng khi khởi động nếu bảng `users` còn trống (id 1, 2, 3). Mật khẩu chung: `123456`.

| id | username | Họ tên | Email |
|---|---|---|---|
| 1 | nguyenvana | Nguyễn Văn A | a@example.com |
| 2 | lethib | Lê Thị B | b@example.com |
| 3 | phamvanc | Phạm Văn C | c@example.com |
| 4 ... 11 | tester1 ... tester8 | Kiểm Thử 1 ... 8 | t1@example.com ... t8@example.com |

`tester1..8` (cùng mật khẩu) chỉ dùng cho `tests/concurrency_seq4.py`, không dùng demo.

Kiểm tra nhanh User service (cần chế độ DEV): `python tests/smoke_user.py`.
Muốn nạp lại từ đầu: `docker compose down -v` rồi `docker compose up --build`.

## Dữ liệu học phí mẫu

Tuition service tự nạp khi khởi động nếu bảng `students` còn trống. Số tiền 15.000.000 cho các MSSV demo.

| MSSV | Họ tên | Học phí | Dùng để |
|---|---|---|---|
| 52100001 | Trần Thị B | UNPAID | Demo; Seq 3 (hai người cùng trả) |
| 52100002 | Nguyễn Văn D | PAID | Thử khóa nút Xác nhận |
| 52100003 | Lê Văn E | UNPAID | Demo; Seq 4 cùng 52100001 (thiếu số dư ở giao dịch thứ hai) |
| 52100005 | Phạm Thị F | (không có) | Thử `TUITION_NOT_FOUND` |
| 52109999, 52109998 | Kiểm Thử ... | UNPAID (1.000.000) | Chỉ cho `tests/smoke_tuition.py` và `smoke_payment.py`, không dùng demo |
| 52107001 ... 52107008 | Kiểm Thử Seq3 | UNPAID (1.000.000) | `tests/concurrency_seq3.py`: mỗi vòng dùng một MSSV |
| 52106001 ... 52106016 | Kiểm Thử Seq4 | UNPAID (1.000.000) | `tests/concurrency_seq4.py`: mỗi vòng dùng hai MSSV |
| 52104001 ... 52104012 | Kiểm Thử Đối Soát | UNPAID (1.000.000) | `tests/smoke_reconcile.py`: mỗi lần chạy dùng 3 MSSV |
| 52105001 ... 52105008 | Kiểm Thử Gửi Lại | UNPAID (1.000.000) | `tests/smoke_resend.py`: mỗi lần chạy dùng một MSSV |
| 52108001 ... 52108008 | Kiểm Thử Dự Phòng | UNPAID (1.000.000) | `tests/smoke_confirm.py`: mỗi lần chạy thanh toán xong một MSSV và trừ 1.000.000 của A |

Kiểm tra Tuition service (cần chế độ DEV): `python tests/smoke_tuition.py`.

## Tài khoản thanh toán mẫu

Payment service tự nạp số dư khi khởi động nếu bảng `accounts` còn trống (`user_id` khớp User service).

| user_id | Người dùng | Số dư | Dùng để |
|---|---|---|---|
| 1 | nguyenvana (A) | 20.000.000 | Đủ trả một học phí 15.000.000; hai học phí thì thiếu (Seq 4) |
| 2 | lethib (B) | 20.000.000 | Seq 3: cùng A trả một học phí |
| 3 | phamvanc (C) | 1.000.000 | Thử `INSUFFICIENT_BALANCE` |
| 4 ... 11 | tester1 ... tester8 | 1.500.000 | `tests/concurrency_seq4.py`: đủ trả một trong hai học phí 1.000.000 |

Kiểm tra Payment (cần chế độ DEV): `python tests/smoke_payment.py` (tạo giao dịch, OTP) và `python tests/smoke_confirm.py`
(thanh toán trọn vẹn, lịch sử). `smoke_confirm.py` làm giảm số dư của A; trước khi demo hãy `docker compose down -v` để trả về dữ liệu gốc.
Email OTP xem tại Mailpit: http://localhost:8025.

## Kiểm thử đồng thời (yêu cầu 6 của đề)

Cần chế độ DEV (User, Tuition, Payment, Mailpit đều chạy). Mỗi script có tham số `--rounds N` để lặp nhiều vòng.

```bash
python tests/concurrency_seq3.py --rounds 3   # Seq 3: hai người cùng trả một học phí -> chỉ một người thành công
python tests/concurrency_seq4.py --rounds 3   # Seq 4: một tài khoản trả hai học phí, số dư chỉ đủ một -> không chi vượt số dư
```

Cả hai tiêu thụ dữ liệu mẫu (MSSV, số dư). Làm mới: `docker compose down -v` rồi `docker compose up --build`.
Trước khi demo hãy làm mới để số dư A, B trở về 20.000.000.

## Gửi lại OTP (UC08)

Mặc định hai lần gửi cách nhau 60 giây nên `python tests/smoke_resend.py` chỉ kiểm tra phần từ chối. Để kiểm tra đầy đủ
(khoảng 15 giây): đặt `OTP_RESEND_COOLDOWN_SECONDS=2` trong `.env`, chạy `docker compose up -d`, chạy script, rồi
**trả về 60 và `docker compose up -d` lại trước khi demo**.

## Job đối soát (tự lành sau sự cố)

Payment chạy nền mỗi `RECONCILE_INTERVAL_SECONDS` giây (mặc định 30) và có thể gọi tay khi demo:
`POST /internal/jobs/reconcile` (header `X-Internal-Key`). Job làm năm việc, đều an toàn khi chạy lặp:

1. OTP `ACTIVE` quá hạn -> `EXPIRED`.
2. Giao dịch `PENDING` quá hạn -> `EXPIRED` sau khi OTP mới nhất hết hạn thêm `TRANSACTION_EXPIRE_GRACE_SECONDS`
   (mặc định 600 giây, để người dùng kịp bấm Gửi lại OTP). `PENDING` có OTP đã dùng mà treo -> `FAILED`.
3. Giao dịch `DEBITED` (đã trừ tiền, Tuition chưa xác nhận) -> thử xác nhận lại; thành công -> `SUCCESS` và gửi email xác nhận.
4. Giao dịch `FAILED`/`EXPIRED` vừa kết thúc mà học phí còn bị giữ chỗ -> nhả giữ chỗ.
5. Email xác nhận gửi lỗi -> thử lại (tối đa 3 lần). Email OTP không thử lại được: dùng Gửi lại OTP.

Kiểm tra: `python tests/smoke_reconcile.py` (đọc hướng dẫn đặt `.env` ở đầu file script; **xong phải khôi phục mặc định**).

## Cấu trúc repo

```text
.
├── docker-compose.yml            # 6 container: web, user, tuition, payment, postgres, mailpit
├── docker-compose.override.yml   # chỉ cho DEV: reload, mở cổng 8001-8003 và 5432
├── .env.example                  # mẫu biến môi trường (copy thành .env, không commit)
├── db/init/01-create-databases.sql   # tạo user_db, tuition_db, payment_db (chạy lần đầu)
├── shared/ibanking_common/       # dùng chung cho 3 service backend
│   ├── errors.py                 #   AppError, định dạng lỗi {"error": {...}}, handler 422/404/500
│   └── security.py               #   JWT (get_current_user), X-Internal-Key (require_internal_key)
├── services/
│   ├── user/        app/{main,config,database,models,schemas}.py, routers/{auth,users}.py
│   ├── tuition/     app/..., routers/tuitions.py
│   ├── payment/     app/..., routers/{accounts,transactions,internal}.py,
│   │                clients.py (gọi User/Tuition), otp.py, mail.py, jobs.py (đối soát)
│   └── web/         app/{main,config,api,csrf}.py, templates/, static/
├── docs/            # sơ đồ (diagrams/), hợp đồng API, báo cáo
├── tests/           # smoke_health.py; thêm script đồng thời cho Seq 3, 4 vào đây
└── scripts/         # script hỗ trợ (dữ liệu mẫu, reset...)
```

## Quy ước làm việc

- **Mỗi thư mục `services/<tên>` có một người chịu trách nhiệm chính.** Sửa thư mục của người khác qua pull request.
  Mỗi người một nhánh (`feature/<tên>-<việc>`), không push thẳng lên `main`.
- **Hợp đồng API là nguồn sự thật** (`docs/api-contract.md`). Cần đổi thì báo cả nhóm trước, rồi sửa hợp đồng và code cùng một PR.
- **Lỗi** luôn dùng `AppError(status, "MA_LOI", "thông báo tiếng Việt")`; không tự `raise HTTPException`.
- **Xác thực**: endpoint người dùng dùng `Depends(get_current_user)`, endpoint nội bộ dùng `Depends(require_internal_key)`.
- **Tiền** là `Decimal` (JSON ra dạng chuỗi `"15000000.00"`), không dùng `float`.
- Thêm thư viện: sửa `requirements.txt` của đúng service rồi `docker compose up --build`.
- Mật khẩu Postgres trong `.env` chỉ nên gồm chữ và số (ký tự đặc biệt làm hỏng `DATABASE_URL`).

## Việc cần làm (gợi ý thứ tự)

1. **Nhi**: khai báo model (`services/*/app/models.py`) theo ERD v3, gồm CHECK và các unique index một phần; file SQL/seed dữ liệu mẫu
   (xem mục "Dữ liệu mẫu" trong hợp đồng API). Chưa có seed thì dùng `init_db()` tạo bảng từ model.
2. **Backend**: User (login, JWT) → Tuition (tra cứu, reservation, payment) → Payment (luồng thành công trước, rồi các nhánh lỗi)
   → concurrency (Seq 3, 4) → email và job đối soát.
3. **Tân**: các route trong `services/web/app/main.py` (bảng route trong hợp đồng API), CSRF (`csrf.py`), giao diện.
4. Thêm script đồng thời vào `tests/` để chứng minh Seq 3 và Seq 4 khi demo.
