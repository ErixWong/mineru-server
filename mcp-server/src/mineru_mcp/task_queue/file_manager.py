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

from mineru_mcp.postprocess import build_postprocess_output_path


def clean_display_name(raw_name: str) -> str:
    """Strip path components and control characters from a display filename.

    This is light cleaning only: no charset replacement (Chinese, spaces, etc. are
    preserved).  Path separators are normalised (backslashes become forward slashes
    on all platforms) so that ``Path(...).name`` reliably strips path components
    regardless of the OS.  Control characters (U+0000 through U+001F, plus DEL) are
    removed to prevent download-header injection.
    """
    if not raw_name:
        return "input.pdf"
    # Normalise Windows-style separators to forward slashes so that
    # Path(...).name strips path components on POSIX as well.
    name = str(Path(raw_name.replace('\\', '/')).name)
    name = re.sub(r'[\x00-\x1f\x7f]', '', name)
    return name or "input.pdf"


def stored_filename(task_id: str, display_name: str) -> str:
    """Derive the on-disk filename from task_id and the display name.

    The storage name is ``{task_id[:8]}{suffix}`` where the suffix is taken from the
    display name (e.g. ``.pdf``).  If the display name has no extension, ``.pdf`` is
    used as a safe default.
    """
    suffix = Path(display_name).suffix or '.pdf'
    return f"{task_id[:8]}{suffix}"


def resolve_stored_filename(task_id: str, display_name: str, task_dir: Path) -> str:
    """Resolve the actual on-disk filename for a task.

    New tasks always write the derived name (``stored_filename``), so that branch
    is checked first.  For legacy tasks whose disk file may still be the old
    ``input_filename`` (either the original name from admin-created tasks or the
    hard-coded ``input.pdf`` from MCP/REST tasks), fall back to the display name
    when the derived file does not exist on disk.
    """
    candidate = stored_filename(task_id, display_name)
    if (task_dir / candidate).exists():
        return candidate
    if (task_dir / display_name).exists():
        return display_name
    return candidate


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

    @staticmethod
    def _normalize_postprocess_filenames(value: "str | list[str] | tuple | set | None") -> list[str]:
        """兼容单个文件名与文件名集合两种入参，去重并保持顺序。"""
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        seen: list[str] = []
        for item in value:
            if item and item not in seen:
                seen.append(item)
        return seen

    def list_task_artifacts(
        self,
        task_dir: Path,
        input_filename: str,
        backend: str = "vlm-auto-engine",
        postprocess_output_filenames: "str | list[str] | None" = None,
        display_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List logical artifacts for a task with availability metadata.

        ``postprocess_output_filenames`` 为该任务全部后处理 run 步骤的产物
        文件名集合（兼容旧的单文件名字符串入参）；同名覆盖策略下天然去重。

        When *display_name* is provided, the primary markdown artifact's
        ``filename`` is mapped from the on-disk derived name back to
        ``{display_stem}.md`` for user-facing display.  The disk file is
        never renamed.
        """
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
        # 后处理产物按 run 步骤快照聚合；没有任何 run 的任务不产生噪音行。
        insert_at = 1
        for filename in self._normalize_postprocess_filenames(postprocess_output_filenames):
            try:
                postprocessed_md_path = build_postprocess_output_path(output_files["md"], filename)
            except ValueError:
                logger.warning("Invalid postprocess output filename %r for task %s, skipping artifact", filename, task_dir.name)
                continue
            artifact_specs.insert(
                insert_at,
                ("postprocessed_markdown", postprocessed_md_path, "text/markdown", "postprocess", False, "postprocessed_markdown"),
            )
            insert_at += 1

        display_md_filename = None
        if display_name:
            display_md_filename = f"{Path(display_name).stem}.md"

        artifacts = []
        for name, path, media_type, role, is_default, artifact_type in artifact_specs:
            filename = display_md_filename if (display_md_filename and artifact_type == "markdown") else path.name
            artifacts.append({
                "name": name,
                "kind": "file",
                "filename": filename,
                "media_type": media_type,
                "role": role,
                "available": path.exists(),
                "downloadable": path.exists(),
                "download_key": self.to_download_key(task_dir, path) if path.exists() else None,
                "is_default": is_default,
                "artifact_type": artifact_type,
            })

        for item in image_items:
            img_path = output_files["images_dir"] / item["filename"]
            artifacts.append({
                "name": f"images/{item['filename']}",
                "kind": "file",
                "filename": item["filename"],
                "media_type": item["media_type"],
                "role": "supplementary",
                "available": True,
                "downloadable": True,
                "download_key": self.to_download_key(task_dir, img_path),
                "is_default": False,
                "artifact_type": "image_file",
            })

        return artifacts

    def read_task_result_format(
        self,
        task_dir: Path,
        input_filename: str,
        backend: str,
        result_format: str,
        postprocess_output_filename: str | None = None,
    ) -> tuple[str, str | dict | list | None, str | None]:
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
        # The postprocessed artifact only exists for tasks with postprocess enabled
        # (filename frozen at creation).  Tasks without it must not register the key
        # to avoid the deterministic-nonexistent-default fallback.
        if postprocess_output_filename:
            format_map["postprocessed_markdown"] = (
                build_postprocess_output_path(output_files["md"], postprocess_output_filename),
                "text",
            )

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

    def get_allowed_download_keys(
        self,
        task_dir: Path,
        input_filename: str,
        backend: str = "vlm-auto-engine",
        postprocess_output_filenames: "str | list[str] | None" = None,
    ) -> set[str]:
        """Return the set of download keys exposed by the public deliverables contract."""
        artifacts = self.list_task_artifacts(task_dir, input_filename, backend, postprocess_output_filenames)
        allowed: set[str] = set()
        for item in artifacts:
            dk = item.get("download_key")
            if item.get("downloadable") and isinstance(dk, str) and dk:
                allowed.add(dk)
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
