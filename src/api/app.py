# -*- coding: utf-8 -*-
"""FastAPI application for the agent task pipeline."""

from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .services import AgentTaskService

app = FastAPI(
    title="员工-客户金额往来审查 Agent API",
    version="1.0.0",
)
service = AgentTaskService()


class ReviewSourceModel(BaseModel):
    type: str = Field(..., description="task_standardized_excel 或 uploaded_excel")
    file_id: str = Field(default="", description="当 type=uploaded_excel 时必填")


class ReviewRequestModel(BaseModel):
    review_source: ReviewSourceModel
    name_list_text: str = Field(..., description="用户名单原始输入文本，支持逗号、顿号、分号和换行切分")


def ok(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": data,
    }


def fail(status_code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": status_code,
            "message": message,
            "data": None,
        },
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(_: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and {"code", "message", "data"}.issubset(detail.keys()):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": str(detail),
            "data": None,
        },
    )


@app.get("/api/v1/health")
def health() -> Dict[str, Any]:
    return ok({"status": "ok"})


@app.post("/api/v1/tasks")
async def create_task(request: Request) -> Dict[str, Any]:
    try:
        content_type = str(request.headers.get("content-type", "") or "").lower()
        task_title = ""
        documents: List[Dict[str, Any]] = []

        if "application/json" in content_type:
            payload = await request.json()
            task_title = str(payload.get("task_title", "") or "").strip()
            document_urls = payload.get("document_urls", []) or []
            if not isinstance(document_urls, list) or not document_urls:
                raise fail(400, "JSON 请求必须提供非空 document_urls 数组")
            task = service.create_task(task_title)
            for url in document_urls:
                documents.append(service.save_document_from_url(task["task_id"], str(url)))
        else:
            form = await request.form()
            task_title = str(form.get("task_title", "") or "").strip()
            files = [item for item in form.getlist("files") if hasattr(item, "filename")]
            if not files:
                raise fail(400, "表单请求必须通过 files 传入至少一个文档")
            task = service.create_task(task_title)
            for upload in files:
                documents.append(
                    service.save_uploaded_document(
                        task["task_id"],
                        upload.filename or "document.bin",
                        await upload.read(),
                    )
                )

        detail = service.get_task_detail(task["task_id"])
        detail["document_count"] = len(documents)
        return ok(detail)
    except ValueError as exc:
        raise fail(400, str(exc))


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str) -> Dict[str, Any]:
    try:
        return ok(service.get_task_detail(task_id))
    except FileNotFoundError as exc:
        raise fail(404, str(exc))


@app.post("/api/v1/tasks/{task_id}/standardize")
def start_standardize(task_id: str) -> Dict[str, Any]:
    try:
        return ok(service.create_standardize_job(task_id))
    except FileNotFoundError as exc:
        raise fail(404, str(exc))
    except ValueError as exc:
        raise fail(400, str(exc))


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    try:
        return ok(service.get_job(job_id))
    except FileNotFoundError as exc:
        raise fail(404, str(exc))


@app.post("/api/v1/tasks/{task_id}/review-source/upload")
async def upload_review_source(task_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        result = service.upload_review_source(
            task_id,
            file.filename or "review_source.xlsx",
            await file.read(),
        )
        return ok(result)
    except FileNotFoundError as exc:
        raise fail(404, str(exc))
    except ValueError as exc:
        raise fail(400, str(exc))


@app.post("/api/v1/tasks/{task_id}/review")
def start_review(task_id: str, payload: ReviewRequestModel) -> Dict[str, Any]:
    try:
        result = service.create_review_job(
            task_id,
            review_source_type=payload.review_source.type,
            uploaded_file_id=payload.review_source.file_id,
            name_list_text=payload.name_list_text,
        )
        return ok(result)
    except FileNotFoundError as exc:
        raise fail(404, str(exc))
    except ValueError as exc:
        raise fail(400, str(exc))


@app.post("/api/v1/tasks/{task_id}/export-skills")
def export_skills(task_id: str) -> Dict[str, Any]:
    try:
        return ok(service.export_skills(task_id))
    except FileNotFoundError as exc:
        raise fail(404, str(exc))
    except ValueError as exc:
        raise fail(400, str(exc))


@app.get("/api/v1/files/{file_id}/download")
def download_file(file_id: str):
    try:
        file_meta = service.get_file(file_id)
    except FileNotFoundError as exc:
        raise fail(404, str(exc))

    path = Path(str(file_meta.get("path", "") or ""))
    if not path.exists():
        raise fail(404, f"文件不存在: {file_id}")

    return FileResponse(
        path=str(path),
        filename=str(file_meta.get("file_name", "") or path.name),
        media_type=str(file_meta.get("content_type", "") or "application/octet-stream"),
    )
