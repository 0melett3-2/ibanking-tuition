import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ["DATABASE_URL"]


settings = Settings()
