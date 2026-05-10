"""MCP server settings — 从 finance-manager/.env 读。"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根 .env(mcp_server 目录在 finance-manager/mcp_server,所以 parent.parent.parent)
_ENV_PATH = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mcp_backend_url: str = Field("http://127.0.0.1:8000")
    mcp_api_token: str = Field(...)            # 必填
    mcp_host: str = Field("0.0.0.0")
    mcp_port: int = Field(8765)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def reset_settings_for_tests() -> None:
    """tests fixture 用 — 强制重新 build settings(读最新 env)。"""
    global _settings
    _settings = None
