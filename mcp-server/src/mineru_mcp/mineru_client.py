"""
MinerU API Client

HTTP client for calling MinerU FastAPI endpoints.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger

from mineru_mcp.config import get_config, DEFAULT_BACKEND


# Task status constants
TASK_PENDING = "pending"
TASK_PROCESSING = "processing"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"


class MinerUClient:
    """Client for MinerU FastAPI."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        default_backend: Optional[str] = None,
        default_server_url: Optional[str] = None,
    ):
        """Initialize the client.
        
        Args:
            base_url: MinerU FastAPI base URL. Defaults to config value.
            default_backend: Default parsing backend. Defaults to config value.
            default_server_url: Default VLM server URL for http-client backends.
        """
        config = get_config()
        self.base_url = base_url or config.mineru_api_base
        self.default_backend = default_backend or config.default_backend
        # VLM server URL: use provided value, or config value, or None
        self.default_server_url = default_server_url or config.get_vlm_server_url()
        self.timeout = httpx.Timeout(300.0, connect=30.0)  # 5 min timeout for large files
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def health_check(self) -> bool:
        """Check if MinerU API is healthy.
        
        Returns:
            True if healthy, False otherwise.
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200 and response.json().get("status") == "healthy"
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    async def parse_pdf_sync(
        self,
        file_path: str,
        backend: str = None,  # Will use self.default_backend if None
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        server_url: Optional[str] = None,  # Will use self.default_server_url if None
        return_md: bool = True,
        return_images: bool = False,
        start_page_id: int = 0,
        end_page_id: int = 99999,
    ) -> dict[str, Any]:
        """Parse PDF synchronously (wait for completion).
        
        Args:
            file_path: Path to the PDF file.
            backend: Parsing backend (defaults to client's default_backend).
            lang: Document language.
            formula_enable: Enable formula recognition.
            table_enable: Enable table recognition.
            server_url: VLM server URL (defaults to client's default_server_url).
            return_md: Return markdown content.
            return_images: Return extracted images.
            start_page_id: Start page (0-indexed).
            end_page_id: End page (0-indexed).
            
        Returns:
            Parsing result with markdown content and images.
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Use default backend if not specified
        effective_backend = backend if backend is not None else self.default_backend
        
        # Use default server_url if not specified and backend is http-client
        effective_server_url = server_url if server_url is not None else self.default_server_url
        
        # Prepare form data
        # Use 99999 as default for end_page_id (means parse all pages)
        effective_end_page_id = end_page_id if end_page_id is not None else 99999
        form_data = {
            "backend": effective_backend,
            "lang_list": lang,
            "formula_enable": str(formula_enable).lower(),
            "table_enable": str(table_enable).lower(),
            "return_md": str(return_md).lower(),
            "return_images": str(return_images).lower(),
            "start_page_id": str(start_page_id),
            "end_page_id": str(effective_end_page_id),
        }
        
        # Add server_url if available (for http-client backends)
        if effective_server_url:
            form_data["server_url"] = effective_server_url
        
        # Upload file
        client = await self._get_client()
        with open(file_path, "rb") as f:
            files = {"files": (file_path_obj.name, f, "application/pdf")}
            logger.info(f"Uploading file: {file_path_obj.name}")
            response = await client.post(
                f"{self.base_url}/file_parse",
                data=form_data,
                files=files,
            )
        
        if response.status_code != 200:
            error_detail = response.json().get("detail", response.text)
            raise RuntimeError(f"Parse failed: {error_detail}")
        
        return response.json()
    
    async def submit_task(
        self,
        file_path: str,
        backend: str = None,  # Will use self.default_backend if None
        lang: str = "ch",
        formula_enable: bool = True,
        table_enable: bool = True,
        server_url: Optional[str] = None,  # Will use self.default_server_url if None
        return_md: bool = True,
        return_images: bool = False,
        start_page_id: int = 0,
        end_page_id: int = 99999,
    ) -> str:
        """Submit an async parsing task.
        
        Args:
            file_path: Path to the PDF file.
            backend: Parsing backend (defaults to client's default_backend).
            lang: Document language.
            formula_enable: Enable formula recognition.
            table_enable: Enable table recognition.
            server_url: VLM server URL (defaults to client's default_server_url).
            return_md: Return markdown content.
            return_images: Return extracted images.
            start_page_id: Start page (0-indexed).
            end_page_id: End page (0-indexed).
            
        Returns:
            Task ID for tracking.
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Use default backend if not specified
        effective_backend = backend if backend is not None else self.default_backend
        
        # Use default server_url if not specified and backend is http-client
        effective_server_url = server_url if server_url is not None else self.default_server_url
        
        # Prepare form data
        # Use 99999 as default for end_page_id (means parse all pages)
        effective_end_page_id = end_page_id if end_page_id is not None else 99999
        form_data = {
            "backend": effective_backend,
            "lang_list": lang,
            "formula_enable": str(formula_enable).lower(),
            "table_enable": str(table_enable).lower(),
            "return_md": str(return_md).lower(),
            "return_images": str(return_images).lower(),
            "start_page_id": str(start_page_id),
            "end_page_id": str(effective_end_page_id),
        }
        
        # Add server_url if available (for http-client backends)
        if effective_server_url:
            form_data["server_url"] = effective_server_url
        
        # Upload file
        client = await self._get_client()
        with open(file_path, "rb") as f:
            files = {"files": (file_path_obj.name, f, "application/pdf")}
            logger.info(f"Submitting task for file: {file_path_obj.name}")
            response = await client.post(
                f"{self.base_url}/tasks",
                data=form_data,
                files=files,
            )
        
        if response.status_code != 202:
            error_detail = response.json().get("detail", response.text)
            raise RuntimeError(f"Task submission failed: {error_detail}")
        
        result = response.json()
        return result["task_id"]
    
    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get task status.
        
        Args:
            task_id: Task ID.
            
        Returns:
            Task status information.
        """
        client = await self._get_client()
        response = await client.get(f"{self.base_url}/tasks/{task_id}")
        
        if response.status_code == 404:
            raise ValueError(f"Task not found: {task_id}")
        
        if response.status_code != 200:
            raise RuntimeError(f"Status check failed: {response.text}")
        
        return response.json()
    
    async def get_task_result(
        self,
        task_id: str,
        return_md: bool = True,
        return_images: bool = False,
    ) -> dict[str, Any]:
        """Get task result.
        
        Args:
            task_id: Task ID.
            return_md: Return markdown content.
            return_images: Return extracted images.
            
        Returns:
            Parsing result.
        """
        params = {
            "return_md": str(return_md).lower(),
            "return_images": str(return_images).lower(),
        }
        
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/tasks/{task_id}/result",
            params=params,
        )
        
        if response.status_code == 404:
            raise ValueError(f"Task not found: {task_id}")
        
        if response.status_code == 202:
            # Task still processing
            return {"status": "processing", "message": "Task result not ready yet"}
        
        if response.status_code != 200:
            raise RuntimeError(f"Result fetch failed: {response.text}")
        
        return response.json()
    
    async def wait_for_task(
        self,
        task_id: str,
        timeout: float = 600.0,
        poll_interval: float = 5.0,
    ) -> dict[str, Any]:
        """Wait for task completion.
        
        Args:
            task_id: Task ID.
            timeout: Maximum wait time in seconds.
            poll_interval: Polling interval in seconds.
            
        Returns:
            Final task result.
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = await self.get_task_status(task_id)
            task_status = status.get("status")
            
            if task_status == TASK_COMPLETED:
                logger.info(f"Task {task_id} completed")
                return await self.get_task_result(task_id)
            
            if task_status == TASK_FAILED:
                error = status.get("error", "Unknown error")
                raise RuntimeError(f"Task failed: {error}")
            
            logger.debug(f"Task {task_id} status: {task_status}, waiting...")
            await asyncio.sleep(poll_interval)  # Use async sleep
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")
    
    async def list_backends(self) -> list[str]:
        """List supported parsing backends.
        
        Returns:
            List of backend names.
        """
        # These are the backends supported by MinerU
        return [
            "pipeline",
            "vlm-auto-engine",
            "vlm-http-client",
            "hybrid-auto-engine",
            "hybrid-http-client",
        ]


# Global client instance
_client: Optional[MinerUClient] = None


def get_client() -> MinerUClient:
    """Get the global MinerU client instance."""
    global _client
    if _client is None:
        _client = MinerUClient()
    return _client


def reset_client() -> None:
    """Reset the global client (for testing)."""
    global _client
    _client = None
