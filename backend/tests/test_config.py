"""Settings 加载与默认值测试。"""
from app.core.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/test")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummy")

    s = Settings()

    assert str(s.database_url).startswith("postgresql+psycopg://")
    assert s.secret_key == "x" * 32
    assert s.backend_cors_origins == ["http://localhost:3000"]


def test_settings_cors_can_be_csv(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/test")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummy")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://a.com,http://b.com")

    s = Settings()

    assert s.backend_cors_origins == ["http://a.com", "http://b.com"]
