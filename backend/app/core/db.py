"""SQLAlchemy engine/session 工厂。"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖:每个请求一个 session + 一个事务。

    端点内只需要 db.add()/db.flush()/对象赋值;请求成功结束时统一 commit。
    若端点抛错或 response_model 序列化阶段失败,统一 rollback,避免半写入。
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def db_session() -> Iterator[Session]:
    """普通脚本/seed 用的 context manager。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
