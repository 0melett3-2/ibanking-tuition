import logging
from math import ceil
from pathlib import Path
from decimal import Decimal
from datetime import datetime

from fastapi import FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import api, csrf
from .config import settings

log = logging.getLogger("ibanking.web")
BASE = Path(__file__).parent
app = FastAPI(title="Web / BFF - iBanking")
templates = Jinja2Templates(directory=BASE / "templates")


# ----------------------------------------------------------------------------------------------
# Jinja2 Filters
# ----------------------------------------------------------------------------------------------
def format_currency(val) -> str:
    try:
        n = int(float(val))
        return f"{n:,}".replace(",", ".") + " đ"
    except (ValueError, TypeError):
        return str(val) if val is not None else ""


def format_datetime(val) -> str:
    if not val:
        return ""
    try:
        if isinstance(val, str):
            val = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(val)
        else:
            dt = val
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(val)


templates.env.filters["currency"] = format_currency
templates.env.filters["datetime"] = format_datetime


# ----------------------------------------------------------------------------------------------
# Helpers: CSRF & Authentication
# ----------------------------------------------------------------------------------------------
def get_csrf(request: Request) -> tuple[str, bool]:
    """Lấy hoặc sinh mới CSRF token: (token, needs_set_cookie)."""
    token = request.cookies.get(settings.csrf_cookie)
    if token:
        try:
            csrf._ser.loads(token, max_age=86400)
            return token, False
        except Exception:
            pass
    return csrf.issue(), True


def check_csrf(request: Request, submitted_token: str | None = None) -> None:
    cookie_token = request.cookies.get(settings.csrf_cookie)
    submitted = request.headers.get("X-CSRF-Token") or submitted_token
    if not csrf.verify(cookie_token, submitted, max_age=86400):
        raise HTTPException(status_code=403, detail="Yêu cầu bị từ chối: CSRF token không hợp lệ hoặc đã hết hạn")


def render_page(request: Request, name: str, context: dict, status_code: int = 200) -> Response:
    csrf_token, needs_set = get_csrf(request)
    context["csrf_token"] = csrf_token
    resp = templates.TemplateResponse(request, name, context, status_code=status_code)
    if needs_set:
        resp.set_cookie(settings.csrf_cookie, csrf_token, httponly=False, samesite="lax",
                        secure=settings.cookie_secure)
    return resp


async def get_session(request: Request) -> tuple[dict | None, dict | None, str | None]:
    """(user, account, token) hoặc (None, None, None) nếu chưa đăng nhập / phiên hết hạn."""
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return None, None, None

    try:
        u_resp = await api.call("GET", settings.user_url, "/users/me", token=token)
        if u_resp.status_code != 200:
            return None, None, None
        user = u_resp.json()
    except Exception as e:
        log.warning("Không thể gọi user service: %s", e)
        return None, None, None

    try:
        a_resp = await api.call("GET", settings.payment_url, "/accounts/me", token=token)
        account = a_resp.json() if a_resp.status_code == 200 else None
    except Exception as e:
        log.warning("Không thể gọi payment service lấy tài khoản: %s", e)
        account = None

    return user, account, token


# ----------------------------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user, account, token = await get_session(request)
    if not user or not token:
        resp = RedirectResponse("/login", status_code=303)
        if request.cookies.get(settings.cookie_name):
            resp.delete_cookie(settings.cookie_name)
        return resp

    # Lấy 5 giao dịch gần nhất
    try:
        t_resp = await api.call("GET", settings.payment_url, "/transactions", token=token,
                                params={"page": 1, "page_size": 5})
        recent = t_resp.json().get("items", []) if t_resp.status_code == 200 else []
    except Exception as e:
        log.warning("Không thể lấy giao dịch gần đây: %s", e)
        recent = []

    return render_page(request, "index.html", {
        "user": user,
        "account": account,
        "recent_transactions": recent,
        "active_nav": "home",
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user, _, _ = await get_session(request)
    if user:
        return RedirectResponse("/", status_code=303)
    return render_page(request, "login.html", {})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(""), password: str = Form(""),
                       csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)

    try:
        r = await api.call("POST", settings.user_url, "/auth/login",
                           json={"username": username, "password": password})
    except Exception as e:
        log.exception("Lỗi kết nối User service: %s", e)
        return render_page(request, "login.html",
                           {"error": "Hệ thống đang bảo trì, vui lòng thử lại sau.", "username": username},
                           status_code=503)

    if r.status_code == 200:
        data = r.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)

        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(settings.cookie_name, token, max_age=expires_in,
                        httponly=True, samesite="lax", secure=settings.cookie_secure)
        return resp

    err = r.json().get("error", {}).get("message", "Đăng nhập không thành công")
    return render_page(request, "login.html", {"error": err, "username": username}, status_code=401)


@app.post("/logout")
async def logout(request: Request, csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(settings.cookie_name)
    return resp


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request, page: int = Query(1, ge=1)):
    user, account, token = await get_session(request)
    if not user or not token:
        return RedirectResponse("/login", status_code=303)

    page_size = 10
    try:
        r = await api.call("GET", settings.payment_url, "/transactions", token=token,
                           params={"page": page, "page_size": page_size})
        data = r.json() if r.status_code == 200 else {"items": [], "page": 1, "page_size": page_size, "total": 0}
    except Exception as e:
        log.warning("Không thể lấy lịch sử giao dịch: %s", e)
        data = {"items": [], "page": 1, "page_size": page_size, "total": 0}

    items = data.get("items", [])
    total = data.get("total", 0)
    current_page = data.get("page", page)
    total_pages = max(1, ceil(total / page_size))

    return render_page(request, "history.html", {
        "user": user,
        "account": account,
        "items": items,
        "page": current_page,
        "total": total,
        "total_pages": total_pages,
        "active_nav": "history",
    })


@app.get("/pay", response_class=HTMLResponse)
async def pay(request: Request):
    user, account, _ = await get_session(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return render_page(request, "pay.html", {
        "user": user,
        "account": account,
        "active_nav": "pay",
    })


@app.get("/pay/lookup", response_class=HTMLResponse)
async def pay_lookup(request: Request, mssv: str = Query("")):
    user, account, token = await get_session(request)
    if not user or not token:
        return HTMLResponse("<div class='p-4 text-red-600'>Phiên đăng nhập đã hết hạn. Vui lòng tải lại trang.</div>", status_code=401)

    code_val = mssv.strip()
    if not code_val:
        return render_page(request, "partials/tuition_lookup.html", {"error": "Vui lòng nhập MSSV để tra cứu"})

    r = await api.call("GET", settings.tuition_url, f"/students/{code_val}/tuition", token=token)
    if r.status_code == 404:
        code_err = r.json().get("error", {}).get("code")
        if code_err == "STUDENT_NOT_FOUND":
            return render_page(request, "partials/tuition_lookup.html", {"error": f"Không tìm thấy sinh viên có MSSV: {code_val}"})
        return render_page(request, "partials/tuition_lookup.html", {"error": f"Sinh viên {code_val} hiện không có khoản học phí nào cần thanh toán."})

    if r.status_code != 200:
        err_msg = r.json().get("error", {}).get("message", "Hệ thống tra cứu học phí đang bận")
        return render_page(request, "partials/tuition_lookup.html", {"error": err_msg})

    tuition = r.json()
    acc_balance = Decimal(str(account["balance"])) if account else Decimal(0)
    t_amount = Decimal(str(tuition["amount"]))
    can_balance = acc_balance >= t_amount

    return render_page(request, "partials/tuition_lookup.html", {
        "tuition": tuition,
        "account": account,
        "can_balance": can_balance,
    })


@app.post("/pay/transactions", response_class=HTMLResponse)
async def pay_create(request: Request, tuition_id: int = Form(...), csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    user, _, token = await get_session(request)
    if not user or not token:
        return HTMLResponse("<div class='p-4 text-red-600'>Phiên đăng nhập đã hết hạn. Vui lòng tải lại trang.</div>", status_code=401)

    r = await api.call("POST", settings.payment_url, "/transactions", token=token,
                       json={"tuition_id": tuition_id})
    if r.status_code in (200, 201):
        txn = r.json()
        return render_page(request, "partials/otp_modal.html", {
            "txn": txn,
            "user_email": user["email"],
        })

    err_body = r.json().get("error", {})
    err_msg = err_body.get("message", "Không thể khởi tạo giao dịch")
    return render_page(request, "partials/payment_result.html", {
        "status": "FAILED",
        "error": err_msg,
    })


@app.post("/pay/transactions/{tid}/confirm", response_class=HTMLResponse)
async def pay_confirm(tid: int, request: Request, otp: str = Form(""), csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    user, _, token = await get_session(request)
    if not user or not token:
        return HTMLResponse("<div class='p-4 text-red-600'>Phiên đăng nhập đã hết hạn. Vui lòng tải lại trang.</div>", status_code=401)

    r = await api.call("POST", settings.payment_url, f"/transactions/{tid}/confirm", token=token,
                       json={"otp": otp.strip()})
    if r.status_code == 200:
        return render_page(request, "partials/payment_result.html", {
            "status": "SUCCESS",
            "txn": r.json(),
        })

    if r.status_code == 202:
        return render_page(request, "partials/payment_result.html", {
            "status": "DEBITED",
            "txn": r.json(),
        })

    err_body = r.json().get("error", {})
    err_code = err_body.get("code")
    err_msg = err_body.get("message", "Xác thực không thành công")

    # Nếu OTP sai và giao dịch chưa FAILED -> Giữ màn hình OTP để người dùng nhập lại
    if err_code == "OTP_INVALID":
        attempts_left = err_body.get("details", {}).get("attempts_left")
        if attempts_left is not None and attempts_left > 0:
            err_msg += f" (Bạn còn {attempts_left} lần thử)"
            # Lấy lại thông tin transaction để render lại form OTP
            txn_resp = await api.call("GET", settings.payment_url, f"/transactions/{tid}", token=token)
            txn_data = txn_resp.json() if txn_resp.status_code == 200 else {"transaction_id": tid}
            return render_page(request, "partials/otp_modal.html", {
                "txn": txn_data,
                "user_email": user["email"],
                "error": err_msg,
            })

    # Các lỗi khác (409 TUITION_NOT_AVAILABLE, 422 INSUFFICIENT_BALANCE, hoặc OTP_ATTEMPTS_EXCEEDED)
    return render_page(request, "partials/payment_result.html", {
        "status": "FAILED",
        "error": err_msg,
    })


@app.post("/pay/transactions/{tid}/resend", response_class=HTMLResponse)
async def pay_resend(tid: int, request: Request, csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    user, _, token = await get_session(request)
    if not user or not token:
        return HTMLResponse("<div class='p-4 text-red-600'>Phiên đăng nhập đã hết hạn. Vui lòng tải lại trang.</div>", status_code=401)

    r = await api.call("POST", settings.payment_url, f"/transactions/{tid}/otps", token=token)
    txn_resp = await api.call("GET", settings.payment_url, f"/transactions/{tid}", token=token)
    txn_data = txn_resp.json() if txn_resp.status_code == 200 else {"transaction_id": tid}

    if r.status_code == 201:
        resend_data = r.json()
        txn_data["otp_expires_at"] = resend_data.get("otp_expires_at")
        left = resend_data.get("resends_left", 0)
        return render_page(request, "partials/otp_modal.html", {
            "txn": txn_data,
            "user_email": user["email"],
            "resend_message": f"Mã OTP mới đã được gửi! (Còn lại {left} lượt gửi lại)",
        })

    err_msg = r.json().get("error", {}).get("message", "Không thể gửi lại OTP lúc này")
    return render_page(request, "partials/otp_modal.html", {
        "txn": txn_data,
        "user_email": user["email"],
        "error": err_msg,
    })


@app.get("/pay/transactions/{tid}/status", response_class=HTMLResponse)
async def pay_status(tid: int, request: Request):
    user, _, token = await get_session(request)
    if not user or not token:
        return HTMLResponse("<div class='p-4 text-red-600'>Phiên đăng nhập đã hết hạn.</div>", status_code=401)

    r = await api.call("GET", settings.payment_url, f"/transactions/{tid}", token=token)
    if r.status_code != 200:
        return render_page(request, "partials/payment_result.html", {
            "status": "FAILED",
            "error": "Không tìm thấy thông tin giao dịch",
        })

    txn = r.json()
    st = txn.get("status")
    if st == "SUCCESS":
        return render_page(request, "partials/payment_result.html", {"status": "SUCCESS", "txn": txn})
    if st == "DEBITED":
        return render_page(request, "partials/payment_result.html", {"status": "DEBITED", "txn": txn})

    return render_page(request, "partials/payment_result.html", {
        "status": "FAILED",
        "txn": txn,
        "error": txn.get("fail_reason", "Giao dịch không thành công"),
    })
