"""File Manager Module

Manages file storage with date-based directory structure.
"""

import base64
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict

from loguru import logger
from fastapi import UploadFile


class FileManager:
    """File manager for task queue.
    
    Directory structure:
        output/2026/05/10/{uuid}/
            ├── input.pdf          # Uploaded file
            └── {pdf_name}/vlm/    # MinerU output (managed by MinerU)
    """
    
    def __init__(self, output_root: str = "output"):
        """Initialize file manager.
        
        Args:
            output_root: Root directory for all outputs.
        """
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileManager initialized at {self.output_root}")
        
    def create_task_dir(self) -> Tuple[str, Path]:
        """Create task directory with date-based structure.
        
        Returns:
            Tuple of (task_id, task_dir).
        """
        task_id = str(uuid.uuid4())
        today = datetime.now()
        
        task_dir = self.output_root / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"Created task directory: {task_dir}")
        return task_id, task_dir

    def create_upload_dir(self) -> Tuple[str, Path]:
        """Create upload directory with date-based structure."""
        upload_id = str(uuid.uuid4())
        today = datetime.now()

        upload_dir = self.output_root / "uploads" / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}" / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Created upload directory: {upload_dir}")
        return upload_id, upload_dir

    def save_uploaded_content(
        self,
        safe_filename: str,
        content: bytes,
        mime_type: str,
    ) -> dict:
        """Persist uploaded content and return metadata."""
        upload_id, upload_dir = self.create_upload_dir()
        stored_path = upload_dir / safe_filename
        stored_path.write_bytes(content)

        sha256 = hashlib.sha256(content).hexdigest()

        return {
            "upload_id": upload_id,
            "upload_dir": upload_dir,
            "file_path": stored_path,
            "file_name": safe_filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "sha256": sha256,
        }
        
    def save_upload_file(
        self,
        file: UploadFile,
        task_dir: Optional[Path] = None
    ) -> Tuple[str, Path, str]:
        """Save uploaded file to task directory.
        
        Args:
            file: FastAPI UploadFile object.
            task_dir: Task directory path (optional, will create if None).
            
        Returns:
            Tuple of (task_id, task_dir, input_filename).
        """
        if task_dir is None:
            task_id, task_dir = self.create_task_dir()
        else:
            task_id = task_dir.name
            
        input_filename = f"input{Path(file.filename).suffix if file.filename else '.pdf'}"
        input_path = task_dir / input_filename
        
        content = file.file.read()
        input_path.write_bytes(content)
        
        logger.info(f"Saved upload file: {input_path} ({len(content)} bytes)")
        return task_id, task_dir, input_filename
        
    def save_file_from_path(
        self,
        file_path: str,
        task_dir: Optional[Path] = None
    ) -> Tuple[str, Path, str]:
        """Save file from local path to task directory.
        
        Args:
            file_path: Local file path.
            task_dir: Task directory path (optional, will create if None).
            
        Returns:
            Tuple of (task_id, task_dir, input_filename).
        """
        source_path = Path(file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        if task_dir is None:
            task_id, task_dir = self.create_task_dir()
        else:
            task_id = task_dir.name
            
        input_filename = f"input{source_path.suffix}"
        input_path = task_dir / input_filename
        
        content = source_path.read_bytes()
        input_path.write_bytes(content)
        
        logger.info(f"Saved file from path: {input_path}")
        return task_id, task_dir, input_filename
        
    def get_output_dir(self, task_dir: Path, input_filename: str, backend: str = "vlm-auto-engine") -> Path:
        """Get MinerU output directory path.
        
        Args:
            task_dir: Task directory path.
            input_filename: Input file name.
            backend: MinerU backend type.
            
        Returns:
            Output directory path (MinerU will create this).
            
        Note:
            MinerU output structure: {task_dir}/{pdf_name}/{parse_method}/
            - pdf_name: extracted from input_filename (without extension)
            - parse_method: "vlm", "auto", "hybrid_auto", "office" (based on backend type)
        """
        pdf_name = Path(input_filename).stem
        
        backend_map = {
            "vlm-auto-engine": "vlm",
            "vlm-transformers": "vlm",
            "vlm-vllm-engine": "vlm",
            "vlm-vllm-async-engine": "vlm",
            "vlm-lmdeploy-engine": "vlm",
            "vlm-http-client": "vlm",
            "pipeline": "auto",
            "hybrid-auto-engine": "hybrid_auto",
            "hybrid-http-client": "hybrid_auto",
            "office": "office",
        }
        
        backend_type = backend_map.get(backend, "auto")
        output_dir = task_dir / pdf_name / backend_type
        
        return output_dir
        
    def get_output_files(self, task_dir: Path, input_filename: str, backend: str = "vlm-auto-engine") -> dict:
        """Get output file paths (after processing).
        
        Args:
            task_dir: Task directory path.
            input_filename: Input file name.
            backend: MinerU backend type.
            
        Returns:
            Dict with file paths (md, middle_json, images_dir, etc).
        """
        output_dir = self.get_output_dir(task_dir, input_filename, backend)
        pdf_name = Path(input_filename).stem
        
        return {
            "output_dir": output_dir,
            "md": output_dir / f"{pdf_name}.md",
            "middle_json": output_dir / f"{pdf_name}_middle.json",
            "model_json": output_dir / f"{pdf_name}_model.json",
            "content_list": output_dir / f"{pdf_name}_content_list.json",
            "images_dir": output_dir / "images",
        }
        
    def cleanup_task_dir(self, task_dir: Path) -> None:
        """Clean up task directory.
        
        Args:
            task_dir: Task directory path.
        """
        import shutil
        
        if task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)
            logger.info(f"Cleaned up task directory: {task_dir}")
    
    def get_images_as_base64(self, images_dir: Path) -> Dict[str, str]:
        """Get all images from directory as Base64 data URLs.
        
        Shared method used by both REST API and MCP Tool.
        
        Args:
            images_dir: Path to images directory.
            
        Returns:
            Dict mapping image filename to Base64 data URL.
        """
        all_images: Dict[str, str] = {}
        
        if not images_dir.exists():
            return all_images
        
        for image_path in images_dir.iterdir():
            if image_path.is_file():
                image_bytes = image_path.read_bytes()
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                ext = image_path.suffix.lower()
                mime_type = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                }.get(ext, 'image/jpeg')
                
                data_url = f"data:{mime_type};base64,{image_base64}"
                all_images[image_path.name] = data_url
        
        return all_images
    
    def get_markdown_content(self, md_path: Path) -> str:
        """Get markdown content from file.
        
        Shared method used by both REST API and MCP Tool.
        
        Args:
            md_path: Path to markdown file.
            
        Returns:
            Markdown content string, or empty string if file not found.
        """
        if md_path.exists():
            return md_path.read_text(encoding='utf-8')
        return ""
