"""File Manager Module.

Manages file storage with date-based directory structure.
"""

import base64
import hashlib
import json
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

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

    _MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)")
    _IMAGE_MIME_TYPES = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
        
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
            "content_list_v2": output_dir / f"{pdf_name}_content_list_v2.json",
            "images_dir": output_dir / "images",
        }

    def validate_task_outputs(self, task_dir: Path, input_filename: str, backend: str = "vlm-auto-engine") -> dict[str, list[str]]:
        """Validate output contract for a completed task.

        Required outputs define task success. Recommended outputs are logged when
        missing but do not fail the task.
        """
        output_files = self.get_output_files(task_dir, input_filename, backend)
        required = {
            "md": output_files["md"],
            "middle_json": output_files["middle_json"],
        }
        recommended = {
            "content_list": output_files["content_list"],
            "content_list_v2": output_files["content_list_v2"],
        }
        optional = {
            "model_json": output_files["model_json"],
        }

        result = {
            "required_missing": [name for name, path in required.items() if not path.exists()],
            "recommended_missing": [name for name, path in recommended.items() if not path.exists()],
            "optional_missing": [name for name, path in optional.items() if not path.exists()],
        }
        return result

    def list_task_artifacts(self, task_dir: Path, input_filename: str, backend: str = "vlm-auto-engine") -> list[dict[str, Any]]:
        """List logical artifacts for a task with availability metadata."""
        output_files = self.get_output_files(task_dir, input_filename, backend)
        markdown_content = self.get_markdown_content(output_files["md"])
        image_items = self.list_images(output_files["images_dir"], markdown_content)
        artifact_specs = [
            ("markdown", output_files["md"], "text/markdown", "primary", True, "markdown"),
            ("middle_json", output_files["middle_json"], "application/json", "required", False, "middle_json"),
            ("model_json", output_files["model_json"], "application/json", "optional", False, "model_json"),
            ("content_list", output_files["content_list"], "application/json", "recommended", False, "content_list"),
            ("content_list_v2", output_files["content_list_v2"], "application/json", "experimental", False, "content_list_v2"),
        ]

        artifacts = []
        for name, path, media_type, role, is_default, artifact_type in artifact_specs:
            artifacts.append({
                "name": name,
                "kind": "file",
                "filename": path.name,
                "media_type": media_type,
                "role": role,
                "available": path.exists(),
                "downloadable": path.exists(),
                "download_key": self.to_download_key(task_dir, path) if path.exists() else None,
                "is_default": is_default,
                "artifact_type": artifact_type,
            })

        artifacts.append({
            "name": "images",
            "kind": "group",
            "filename": "images/",
            "media_type": "inode/directory",
            "role": "supplementary",
            "available": bool(image_items),
            "downloadable": False,
            "download_key": None,
            "is_default": False,
            "artifact_type": "image_group",
            "children": [
                {
                    "name": f"images/{item['filename']}",
                    "kind": "file",
                    "filename": item["filename"],
                    "media_type": item["media_type"],
                    "role": "supplementary",
                    "available": True,
                    "downloadable": True,
                    "download_key": self.to_download_key(task_dir, output_files["images_dir"] / item["filename"]),
                    "is_default": False,
                    "artifact_type": "image_file",
                }
                for item in image_items
            ],
        })
        return artifacts

    def read_task_result_format(self, task_dir: Path, input_filename: str, backend: str, result_format: str) -> tuple[str, str | dict | list | None, str | None]:
        """Read a logical task result format.

        Returns a tuple of (format, payload, filename).
        """
        output_files = self.get_output_files(task_dir, input_filename, backend)
        normalized_format = result_format or "markdown"

        format_map: dict[str, tuple[Path, str]] = {
            "markdown": (output_files["md"], "text"),
            "middle_json": (output_files["middle_json"], "json"),
            "model_json": (output_files["model_json"], "json"),
            "content_list": (output_files["content_list"], "json"),
            "content_list_v2": (output_files["content_list_v2"], "json"),
        }

        if normalized_format not in format_map:
            raise ValueError(f"Unsupported result format: {normalized_format}")

        target_path, read_mode = format_map[normalized_format]
        if not target_path.exists():
            raise FileNotFoundError(f"Result format '{normalized_format}' is not available")

        if read_mode == "text":
            return normalized_format, target_path.read_text(encoding="utf-8"), target_path.name

        return normalized_format, json.loads(target_path.read_text(encoding="utf-8")), target_path.name

    def to_download_key(self, task_dir: Path, artifact_path: Path) -> str:
        """Return a controlled relative path for unified artifact download."""
        task_root = task_dir.resolve(strict=False)
        target = artifact_path.resolve(strict=False)
        return target.relative_to(task_root).as_posix()

    def get_allowed_download_keys(self, task_dir: Path, input_filename: str, backend: str = "vlm-auto-engine") -> set[str]:
        """Return the set of download keys exposed by the public deliverables contract."""
        artifacts = self.list_task_artifacts(task_dir, input_filename, backend)
        allowed: set[str] = set()

        def collect(items: list[dict[str, Any]]) -> None:
            for item in items:
                download_key = item.get("download_key")
                if item.get("downloadable") and isinstance(download_key, str) and download_key:
                    allowed.add(download_key)
                children = item.get("children")
                if isinstance(children, list):
                    collect(children)

        collect(artifacts)
        return allowed

    def resolve_download_key(self, task_dir: Path, download_key: str) -> Path:
        """Resolve a controlled relative path safely within the task directory."""
        if not download_key or Path(download_key).is_absolute():
            raise ValueError("Invalid download key")

        candidate = (task_dir / download_key).resolve(strict=False)
        task_root = task_dir.resolve(strict=False)

        try:
            candidate.relative_to(task_root)
        except ValueError as exc:
            raise ValueError("Invalid download key") from exc

        return candidate

    def read_artifact_by_download_key(self, task_dir: Path, download_key: str) -> tuple[Path, str | dict | list]:
        """Read an artifact by unified download key."""
        artifact_path = self.resolve_download_key(task_dir, download_key)
        if not artifact_path.exists() or not artifact_path.is_file():
            raise FileNotFoundError(f"Artifact '{download_key}' is not available")

        suffix = artifact_path.suffix.lower()
        if suffix == ".md":
            return artifact_path, artifact_path.read_text(encoding="utf-8")
        if suffix == ".json":
            return artifact_path, json.loads(artifact_path.read_text(encoding="utf-8"))

        return artifact_path, base64.b64encode(artifact_path.read_bytes()).decode("utf-8")
        
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
                mime_type = self.get_image_mime_type(image_path)
                
                data_url = f"data:{mime_type};base64,{image_base64}"
                all_images[image_path.name] = data_url
        
        return all_images

    def get_image_mime_type(self, image_path: Path) -> str:
        """Get image media type from file extension."""
        return self._IMAGE_MIME_TYPES.get(image_path.suffix.lower(), "application/octet-stream")

    def get_media_type_for_path(self, artifact_path: Path) -> str:
        """Get a media type for an arbitrary artifact path."""
        if artifact_path.suffix.lower() in self._IMAGE_MIME_TYPES:
            return self.get_image_mime_type(artifact_path)
        guessed, _ = mimetypes.guess_type(artifact_path.name)
        return guessed or "application/octet-stream"

    def get_markdown_image_references(self, markdown_content: str) -> Dict[str, list[dict[str, Any]]]:
        """Parse markdown image tokens into filename-keyed references.

        Positions are based on the markdown output, not on original PDF coordinates.
        """
        references: Dict[str, list[dict[str, Any]]] = {}

        if not markdown_content:
            return references

        offset = 0
        for line_number, line in enumerate(markdown_content.splitlines(keepends=True), start=1):
            for match in self._MARKDOWN_IMAGE_PATTERN.finditer(line):
                markdown_path = match.group("path").strip()
                filename = Path(markdown_path).name
                references.setdefault(filename, []).append({
                    "markdown_path": markdown_path,
                    "line_number": line_number,
                    "start_offset": offset + match.start(),
                    "end_offset": offset + match.end(),
                    "alt_text": match.group("alt"),
                })
            offset += len(line)

        return references

    def list_images(self, images_dir: Path, markdown_content: str = "") -> list[dict[str, Any]]:
        """List extracted images with markdown-level reference metadata."""
        references_by_name = self.get_markdown_image_references(markdown_content)
        items: list[dict[str, Any]] = []

        if not images_dir.exists():
            return items

        for image_path in sorted(images_dir.iterdir(), key=lambda item: item.name):
            if not image_path.is_file():
                continue

            relative_path = f"images/{image_path.name}"
            references = references_by_name.get(image_path.name, [])
            items.append({
                "filename": image_path.name,
                "relative_path": relative_path,
                "url": None,
                "media_type": self.get_image_mime_type(image_path),
                "referenced_in_markdown": bool(references),
                "references": references,
            })

        return items

    def resolve_task_image_path(self, images_dir: Path, image_name: str) -> Path:
        """Resolve a task image path safely within the images directory."""
        candidate = (images_dir / image_name).resolve(strict=False)
        images_root = images_dir.resolve(strict=False)

        if candidate.parent != images_root:
            raise ValueError("Invalid image path")

        return candidate
    
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
