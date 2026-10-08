from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# Mức cô lập mặc định của PostgreSQL là READ COMMITTED - các sơ đồ Seq 3, 4 dựa vào mức này.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tạo bảng từ model khi khởi động. Nếu dùng file SQL riêng thì bỏ create_all và chạy SQL."""
    from . import models  # noqa: F401  (để model đăng ký vào Base)
    Base.metadata.create_all(bind=engine)
