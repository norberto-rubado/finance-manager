"""Pydantic Settings:读 .env 并把字段做类型校验。"""
from functools import lru_cache
from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Postgres
    database_url: str = Field(...)

    # Backend
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    backend_cors_origins: Union[str, List[str]] = ["http://localhost:3000"]

    # Auth
    secret_key: str = Field(..., min_length=32)
    admin_username: str = "admin"
    admin_password_hash: str = Field(...)

    # MCP
    mcp_api_token: str | None = None

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def split_cors(cls, v):
        if isinstance(v, str) and "," in v:
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, str):
            return [v]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
