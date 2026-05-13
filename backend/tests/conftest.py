"""pytest fixtures。

策略(slice B I-3 修复后):
- session 起始一次性 create_all(基于 SQLAlchemy metadata,与 alembic 解耦,测试不依赖 alembic head)
- 每个 db 测试开新 connection + 起外层 transaction,session 用 join_transaction_mode="create_savepoint"
- 测试中调 session.commit() 实际只 release/create savepoint,数据可见但未真正落盘
- 测试结束 rollback 外层 transaction,所有数据消失,无 truncate 开销
- 不需要 db 的测试(parser、normalize 等)直接不引用 db fixture,零开销
- 可选 TEST_DATABASE_URL 指向独立 db,进一步保护开发数据
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


_settings = get_settings()
# `or` 让空字符串 "" 与 None 都回落到 database_url(.env.example 占位 TEST_DATABASE_URL= 即空串)
_db_url = _settings.test_database_url or _settings.database_url
_engine = create_engine(_db_url, future=True)
_TestSession = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """整个测试 session 一次性 create_all。session 结束不 drop,便于事后查表。"""
    Base.metadata.create_all(_engine)
    yield


@pytest.fixture
def db() -> Session:
    """每个 db 测试一个 connection + 外层 transaction + nested savepoint session。

    session.commit() 只 release/create savepoint;teardown rollback 外层 transaction。
    嵌套 try/finally 保证即使中间一步抛错,connection.close() 也一定执行
    (避免 pytest-xdist / 网络抖动场景下连接泄漏)。

    测试间隔离:外层 transaction rollback 后,本次测试期间的所有 INSERT / UPDATE /
    DELETE(包括看似 commit 过的)都消失,无需手动 truncate。

    注意:savepoint rollback 不能撤销在 fixture 之外、外层 transaction 启动之前就已
    落盘的数据 —— 例如 `python -m app.db.seed` 在 dev db 留下的 admin user 及其
    categories / merchant_rules。若测试依赖"空表"前提,请创建临时 user_id(uuid 后缀)
    绕开残留,参见 tests/test_seed_categories.py::fresh_user。
    """
    connection = _engine.connect()
    outer_tx = connection.begin()
    session = _TestSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        try:
            session.close()
        finally:
            try:
                outer_tx.rollback()
            finally:
                connection.close()
