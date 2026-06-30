from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "مكتب سعيد الشبيبي للمحاماة"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./saeed_law.db"
    upload_dir: str = "app/static/uploads"
    session_max_age: int = 60 * 60 * 8

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            db_path = url.removeprefix("sqlite:///")
            if db_path != ":memory:" and not Path(db_path).is_absolute():
                return f"sqlite:///{(PROJECT_ROOT / db_path).resolve().as_posix()}"
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
