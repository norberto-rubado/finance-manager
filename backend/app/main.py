"""FastAPI app 实例 + minimum routes。"""
from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.core.db import engine

app = FastAPI(title="Finance Manager API", version="0.1.0")

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    """健康检查:进程在 + db 可达。"""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {type(e).__name__}"
    return {"status": "ok", "version": app.version, "db": db_status}


app.include_router(router)
