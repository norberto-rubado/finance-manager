"""Statements API — spec § 9.1 + § 5.1。

本 task(15):POST /import
Task 16:list / detail / review
"""
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUserDep, DbDep
from app.schemas import ImportResponse
from app.services.importer import DuplicateImportError, run_import_pipeline
from app.services.statement_parser import UnsupportedStatementError


router = APIRouter(prefix="/statements", tags=["statements"])


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/import", response_model=ImportResponse)
async def import_statement(
    user: CurrentUserDep, db: DbDep, file: UploadFile = File(...),
) -> ImportResponse:
    """multipart upload → 跑导入流水线。spec § 5.1。"""
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file > {_MAX_UPLOAD_BYTES // 1024 // 1024}MB")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    try:
        return run_import_pipeline(
            db, user_id=user.id, file_bytes=raw,
            filename=file.filename or "unknown",
        )
    except UnsupportedStatementError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            f"unsupported statement: {e}") from e
    except DuplicateImportError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        # 解析器内部错(如 GBK decode 失败 / 表头缺列)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
