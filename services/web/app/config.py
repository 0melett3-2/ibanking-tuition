import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    user_url: str = os.environ["USER_SERVICE_URL"]
    tuition_url: str = os.environ["TUITION_SERVICE_URL"]
    payment_url: str = os.environ["PAYMENT_SERVICE_URL"]
    secret_key: str = os.environ["WEB_SECRET_KEY"]
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    cookie_name: str = "access_token"       # cookie HttpOnly chứa JWT
    csrf_cookie: str = "csrf_token"


settings = Settings()
