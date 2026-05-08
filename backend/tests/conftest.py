"""pytest fixtures。

策略:
- 用一个独立的"测试 schema"在主 db 里跑,每个测试函数前 truncate 全表
- 这比 SQLite in-memory 简单(不用处理 PG-only 类型如 JSONB),又比 testcontainers 快
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


_settings = get_settings()
_engine = create_engine(_settings.database_url, future=True)
_TestSession = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """整个测试 session 一次性建表。"""
    Base.metadata.create_all(_engine)
    yield
    # session 结束**不**drop,留着便于事后人工查


@pytest.fixture(autouse=True)
def _truncate_between_tests():
    """每个测试前 TRUNCATE 业务表(保留 alembic_version 不动)。

    WARNING: 此测试基础设施使用生产 postgres 数据库。
    _truncate_between_tests 在每个测试前清空用户数据。
    这对 slice A 可行(仅有可重新生成的种子数据),
    但在后续 slice 应考虑分离的测试 db。
    """
    with _engine.begin() as conn:
        # 用 RESTART IDENTITY 让自增 id 也重置;CASCADE 处理外键
        conn.execute(text(
            "TRUNCATE TABLE "
            "dedup_candidates, transactions, statement_imports, "
            "merchant_rules, categories, api_tokens, accounts, users "
            "RESTART IDENTITY CASCADE"
        ))
    yield


@pytest.fixture
def db() -> Session:
    """每个测试一个独立 session(autocommit 关闭,显式 commit)。"""
    session = _TestSession()
    try:
        yield session
        session.rollback()  # 默认每个测试 rollback,显式 commit 的代码可以提前 flush
    finally:
        session.close()
