"""回归测试:生产 get_db 依赖必须在成功请求后提交事务。"""

from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.deps import current_user
from app.core import db as db_module
from app.main import app
from app.models import Account, Transaction, User


def test_real_get_db_commits_successful_write_request(db, monkeypatch):
    """不 override get_db,只把 SessionLocal 指到测试事务连接。

    过去 get_db 只 close 不 commit;POST 返回 201,但新 session 查不到写入。
    这个测试用同一条测试 connection + 外层事务隔离数据,同时真实执行 get_db 的
    yield/commit/rollback/finally 生命周期。
    """
    user = User(username="commit_regression_user", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    account = Account(
        user_id=user.id,
        name="测试现金账户",
        type="cash",
        institution="现金",
        last4=None,
        currency="CNY",
    )
    db.add(account)
    db.flush()

    test_session_local = sessionmaker(
        bind=db.connection(),
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(db_module, "SessionLocal", test_session_local)

    def _current_user_override() -> User:
        return user

    app.dependency_overrides[current_user] = _current_user_override
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/transactions/manual",
                json={
                    "account_id": account.id,
                    "tx_kind": "expense",
                    "tx_time": "2026-05-10T12:00:00",
                    "amount": "12.34",
                    "currency": "CNY",
                    "merchant": "commit-regression-merchant",
                    "description": "should persist after request",
                },
            )
        assert resp.status_code == 201, resp.text
        tx_id = resp.json()["id"]

        verify_db = test_session_local()
        try:
            persisted = verify_db.execute(
                select(Transaction).where(Transaction.id == tx_id)
            ).scalar_one_or_none()
            assert persisted is not None
            assert persisted.amount == Decimal("12.34")
            assert persisted.merchant_normalized == "commit-regression-merchant"
            assert persisted.tx_time.replace(tzinfo=None) == datetime(2026, 5, 10, 12, 0)
        finally:
            verify_db.close()
    finally:
        app.dependency_overrides.pop(current_user, None)
