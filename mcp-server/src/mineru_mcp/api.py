"""
REST API Layer

FastAPI routes that share the same MinerUClient backend as MCP tools.
Mounted under /api in the unified Starlette app.
"""

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from mineru_mcp.config import get_config
from mineru_mcp.mineru_client import get_client
from mineru_mcp.validation import (
    validate_file_path,
    validate_task_id,
    validate_backend,
    validate_language,
    validate_page_range,
    ValidationError,
)
from mineru_mcp.errors import from_exception
from mineru_mcp.utils import aggregate_markdown, extract_images, save_base64_file, cleanup_temp_file


def _save_upload_file(file: UploadFile) -> Path:
    """Save UploadFile to a temporary location.
    
    Args:
        file: FastAPI UploadFile object.
        
    Returns:
        Path to the saved temporary file.
    """
    temp_dir = Path(tempfile.gettempdir()) / "mineru_mcp_upload"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    unique_name = f"{uuid.uuid4()}{Path(file.filename).suffix if file.filename else '.pdf'}"
    temp_path = temp_dir / unique_name
    
    content = file.file.read()
    temp_path.write_bytes(content)
    
    return temp_path


def _get_start_time() -> float:
    """Get the shared start time from app module."""
    from mineru_mcp.app import _start_time
    return _start_time


def create_api_app() -> FastAPI:
    app = FastAPI(
        title="MinerU MCP Server API",
        description="REST API for MinerU PDF parsing (same backend as MCP tools)",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/health")
    async def health():
        config = get_config()
        client = get_client()
        try:
            is_healthy = await client.health_check()
        except Exception:
            is_healthy = False
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "uptime": time.time() - _get_start_time(),
        }

    @app.get("/backends")
    async def list_backends():
        client = get_client()
        backends = await client.list_backends()
        descriptions = {
            "pipeline": "Traditional pipeline (no VLM, multi-language support)",
            "vlm-auto-engine": "Local VLM engine (Chinese/English only)",
            "vlm-http-client": "Remote VLM via OpenAI-compatible API (Chinese/English only)",
            "hybrid-auto-engine": "Local OCR + local VLM (multi-language support)",
            "hybrid-http-client": "Local OCR + remote VLM (multi-language, recommended)",
        }
        return {
            "backends": [
                {"name": b, "description": descriptions.get(b, "")}
                for b in backends
            ],
        }

    @app.post("/parse")
    async def parse_pdf_sync(
        file: UploadFile = File(..., description="PDF file to parse"),
        backend: str = Form(default=None),
        lang: str = Form(default="ch"),
        formula_enable: bool = Form(default=True),
        table_enable: bool = Form(default=True),
        server_url: str = Form(default=None),
        start_page_id: int = Form(default=0),
        end_page_id: int = Form(default=99999),
    ):
        """Parse PDF file synchronously (multipart/form-data upload).
        
        Upload a PDF file for immediate parsing. Returns markdown content.
        
        Args:
            file: PDF file to upload and parse.
            backend: Parsing backend (optional, defaults to MINERU_DEFAULT_BACKEND).
            lang: Document language.
            formula_enable: Enable formula recognition.
            table_enable: Enable table recognition.
            server_url: VLM server URL (for http-client backends).
            start_page_id: Start page (0-indexed).
            end_page_id: End page (0-indexed).
            
        Returns:
            Parsing result with markdown content.
        """
        config = get_config()
        client = get_client()
        temp_file_path = None
        
        try:
            effective_backend = backend if backend is not None else config.default_backend
            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)
            
            logger.info(f"Received file upload: {file.filename}")
            
            temp_file_path = _save_upload_file(file)
            logger.info(f"Saved to temporary file: {temp_file_path.name}")
            
            effective_server_url = server_url or config.get_vlm_server_url()
            
            result = await client.parse_pdf_sync(
                file_path=str(temp_file_path),
                backend=validated_backend,
                lang=validated_lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                server_url=effective_server_url,
                return_md=True,
                return_images=False,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
            )
            
            cleanup_temp_file(temp_file_path)
            
            return result

        except HTTPException:
            raise
        except ValidationError as e:
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            raise HTTPException(status_code=400, detail=e.to_dict())
        except Exception as e:
            logger.error(f"Parse error: {e}")
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            err = from_exception(e)
            raise HTTPException(status_code=err.http_status, detail=err.to_dict())

    @app.post("/tasks")
    async def submit_task(
        file: UploadFile = File(..., description="PDF file to parse"),
        backend: str = Form(default=None),
        lang: str = Form(default="ch"),
        formula_enable: bool = Form(default=True),
        table_enable: bool = Form(default=True),
        server_url: str = Form(default=None),
        start_page_id: int = Form(default=0),
        end_page_id: int = Form(default=99999),
    ):
        """Submit PDF parsing task asynchronously (multipart/form-data upload).
        
        Upload a PDF file for asynchronous parsing. Returns task ID.
        
        Args:
            file: PDF file to upload and parse.
            backend: Parsing backend (optional, defaults to MINERU_DEFAULT_BACKEND).
            lang: Document language.
            formula_enable: Enable formula recognition.
            table_enable: Enable table recognition.
            server_url: VLM server URL (for http-client backends).
            start_page_id: Start page (0-indexed).
            end_page_id: End page (0-indexed).
            
        Returns:
            Task ID and status (pending).
        """
        config = get_config()
        client = get_client()
        temp_file_path = None
        
        try:
            effective_backend = backend if backend is not None else config.default_backend
            validated_backend = validate_backend(effective_backend)
            validated_lang = validate_language(lang)
            validate_page_range(start_page_id, end_page_id)
            
            logger.info(f"Received file upload: {file.filename}")
            
            temp_file_path = _save_upload_file(file)
            logger.info(f"Saved to temporary file: {temp_file_path.name}")
            
            effective_server_url = server_url or config.get_vlm_server_url()
            
            task_id = await client.submit_task(
                file_path=str(temp_file_path),
                backend=validated_backend,
                lang=validated_lang,
                formula_enable=formula_enable,
                table_enable=table_enable,
                server_url=effective_server_url,
                return_md=True,
                return_images=True,
                start_page_id=start_page_id,
                end_page_id=end_page_id,
            )
            
            cleanup_temp_file(temp_file_path)
            
            return JSONResponse(
                status_code=202,
                content={
                    "task_id": task_id,
                    "status": "pending",
                    "message": "Task submitted. Use GET /api/tasks/{task_id} to check progress.",
                },
            )

        except HTTPException:
            raise
        except ValidationError as e:
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            raise HTTPException(status_code=400, detail=e.to_dict())
        except Exception as e:
            logger.error(f"Task submission error: {e}")
            if temp_file_path:
                cleanup_temp_file(temp_file_path)
            err = from_exception(e)
            raise HTTPException(status_code=err.http_status, detail=err.to_dict())

    @app.get("/tasks/{task_id}")
    async def get_task(
        task_id: str,
        return_md: bool = Query(default=True),
    ):
        client = get_client()

        try:
            validated_task_id = validate_task_id(task_id)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=e.to_dict())

        try:
            status_info = await client.get_task_status(validated_task_id)
            task_status = status_info.get("status", "unknown")

            if task_status in ("pending", "processing"):
                return JSONResponse(
                    status_code=200,
                    content={
                        "task_id": validated_task_id,
                        "status": task_status,
                        "message": status_info.get("message", f"Task is {task_status}"),
                    },
                )

            if task_status == "failed":
                return JSONResponse(
                    status_code=200,
                    content={
                        "task_id": validated_task_id,
                        "status": "failed",
                        "error": status_info.get("error", "Unknown error"),
                    },
                )

            if task_status == "completed":
                if not return_md:
                    return {
                        "task_id": validated_task_id,
                        "status": "completed",
                        "message": "Task completed. Use return_md=true or GET /api/tasks/{task_id}/images to retrieve content.",
                    }

                result = await client.get_task_result(
                    task_id=validated_task_id,
                    return_md=True,
                    return_images=False,
                )

                return {
                    "task_id": validated_task_id,
                    "status": "completed",
                    "markdown": aggregate_markdown(result),
                }

            return {
                "task_id": validated_task_id,
                "status": task_status,
            }

        except ValueError:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        except Exception as e:
            logger.error(f"Get task error: {e}")
            err = from_exception(e)
            raise HTTPException(status_code=err.http_status, detail=err.to_dict())

    @app.get("/tasks/{task_id}/images")
    async def get_task_images(task_id: str):
        client = get_client()

        try:
            validated_task_id = validate_task_id(task_id)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=e.to_dict())

        try:
            result = await client.get_task_result(
                task_id=validated_task_id,
                return_md=False,
                return_images=True,
            )

            if result.get("status") == "processing":
                return JSONResponse(
                    status_code=202,
                    content={"task_id": validated_task_id, "status": "processing", "message": "Task result not ready yet"},
                )

            images = extract_images(result)
            return {
                "task_id": validated_task_id,
                "status": result.get("status", "unknown"),
                "images": images,
                "count": len(images),
            }

        except ValueError:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        except Exception as e:
            logger.error(f"Get images error: {e}")
            err = from_exception(e)
            raise HTTPException(status_code=err.http_status, detail=err.to_dict())

    return app
