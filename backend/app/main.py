"""FastAPI app 实例 + minimum routes。"""
from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.api import auth as auth_api
from app.api import statements as statements_api
from app.core.db import engine

app = FastAPI(title="Finance Manager API", version="0.1.0")

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health() -> dict:
    """健康检查:进程在 + db 可达。"""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {type(e).__name__}"
    return {"status": "ok", "version": app.version, "db": db_status}


api_router.include_router(auth_api.router)
api_router.include_router(statements_api.router)
app.include_router(api_router)
