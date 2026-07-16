"""Pydantic Models for API and MCP Responses

Aligned with markitdown-server response structure for consistency.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UploadStatus(str, Enum):
    UPLOADED = "uploaded"
    CONSUMED = "consumed"


class QueueStatsResponse(BaseModel):
    pending: int = Field(default=0, description="Pending tasks count")
    processing: int = Field(default=0, description="Processing tasks count")
    completed: int = Field(default=0, description="Completed tasks count")
    failed: int = Field(default=0, description="Failed tasks count")
    cancelled: int = Field(default=0, description="Cancelled tasks count")


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Server health status")
    version: str = Field(..., description="Server version")
    uptime: float = Field(..., description="Server uptime in seconds")
    scheduler_running: bool = Field(default=False, description="Whether the task scheduler is running")
    auth_required: bool = Field(default=False, description="Whether authentication is enabled")
    queue_stats: Optional[QueueStatsResponse] = Field(default=None, description="Task queue statistics")


class SubmitTaskResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    message: str = Field(default="Task submitted successfully", description="Status message")
    created_at: datetime = Field(..., description="Task creation timestamp")


class UploadResponse(BaseModel):
    upload_id: str = Field(..., description="Unique upload identifier")
    status: UploadStatus = Field(..., description="Current upload status")
    file_name: str = Field(..., description="Original file name")
    mime_type: str = Field(..., description="Uploaded file MIME type")
    size_bytes: int = Field(..., description="Uploaded file size in bytes")
    sha256: str = Field(..., description="SHA256 hash of uploaded content")
    created_at: datetime = Field(..., description="Upload creation timestamp")


class SubmitUploadedTaskRequest(BaseModel):
    upload_id: str = Field(..., description="Uploaded file identifier")
    backend: Optional[str] = Field(default=None, description="Parsing backend")
    lang: str = Field(default="ch", description="Document language")
    formula_enable: bool = Field(default=True, description="Enable formula recognition")
    table_enable: bool = Field(default=True, description="Enable table recognition")
    image_analysis: bool = Field(default=True, description="Enable VLM image analysis")
    server_url: Optional[str] = Field(default=None, description="VLM server URL")
    start_page_id: int = Field(default=0, description="Start page (0-indexed)")
    end_page_id: int = Field(default=99999, description="End page (0-indexed)")


class TaskStatusResponse(BaseModel):
    task_id: str = Field(..., description="Task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    progress: int = Field(..., ge=-1, le=100, description="Progress percentage (0-100, -1 for failed/cancelled)")
    message: str = Field(..., description="Human-readable status message")
    created_at: datetime = Field(..., description="Task creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class TaskDetailResponse(BaseModel):
    task_id: str = Field(..., description="Task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    progress: int = Field(..., ge=-1, le=100, description="Progress percentage (0-100, -1 for failed/cancelled)")
    message: str = Field(..., description="Human-readable status message")
    created_at: datetime = Field(..., description="Task creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    started_at: Optional[datetime] = Field(default=None, description="Task start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Task completion timestamp")
    markdown: Optional[str] = Field(default=None, description="Markdown content when completed")
    error: Optional[str] = Field(default=None, description="Error message when failed or cancelled")


class TaskResultResponse(BaseModel):
    task_id: str = Field(..., description="Task identifier")
    status: TaskStatus = Field(..., description="Task status")
    format: str = Field(default="markdown", description="Requested logical result format")
    markdown: Optional[str] = Field(default=None, description="Markdown content")
    content: Optional[dict | list | str] = Field(default=None, description="Requested result payload")
    filename: Optional[str] = Field(default=None, description="Underlying output filename when applicable")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class TaskArtifactItem(BaseModel):
    name: str = Field(..., description="Logical artifact name")
    kind: str = Field(..., description="Artifact kind: file/group")
    filename: str = Field(..., description="Artifact filename")
    media_type: str = Field(..., description="Artifact media type")
    role: str = Field(..., description="Artifact role: primary/required/recommended/optional/experimental")
    available: bool = Field(..., description="Whether the artifact currently exists")
    downloadable: bool = Field(..., description="Whether the artifact can be downloaded directly")
    download_key: Optional[str] = Field(default=None, description="Controlled relative path used for unified download")
    is_default: bool = Field(default=False, description="Whether this artifact is the default primary result")
    artifact_type: Optional[str] = Field(
        default=None,
        description="Artifact type classification: markdown/middle_json/model_json/content_list/content_list_v2/image_group/image_file"
    )
    children: Optional[list[TaskArtifactItem]] = Field(default=None, description="Child artifacts for group/collection entries")


class TaskArtifactsResponse(BaseModel):
    task_id: str = Field(..., description="Task identifier")
    status: TaskStatus = Field(..., description="Task status")
    artifacts: list[TaskArtifactItem] = Field(default_factory=list, description="Available task artifacts")


class TaskImageReference(BaseModel):
    markdown_path: str = Field(..., description="Image path as referenced in markdown")
    line_number: int = Field(..., ge=1, description="1-based markdown line number where the image is referenced")
    start_offset: int = Field(..., ge=0, description="0-based character offset of the markdown image token start")
    end_offset: int = Field(..., ge=0, description="0-based character offset immediately after the markdown image token")
    alt_text: str = Field(default="", description="Alt text from the markdown image token")


class TaskImageItem(BaseModel):
    filename: str = Field(..., description="Image filename")
    relative_path: str = Field(..., description="Relative image path within the task output")
    url: Optional[str] = Field(default=None, description="Static file URL for remote access")
    media_type: str = Field(..., description="Detected image media type")
    referenced_in_markdown: bool = Field(default=False, description="Whether the image is referenced by markdown output")
    references: list[TaskImageReference] = Field(default_factory=list, description="Markdown-level reference positions for this image")


class TaskImagesResponse(BaseModel):
    task_id: str = Field(..., description="Task identifier")
    status: TaskStatus = Field(..., description="Task status")
    images: dict[str, str] = Field(default_factory=dict, description="Images as Base64 data URLs")
    items: list[TaskImageItem] = Field(default_factory=list, description="Structured image metadata and remote URLs")
    count: int = Field(default=0, description="Number of images")


class TaskListItem(BaseModel):
    task_id: str
    filename: str
    status: TaskStatus
    progress: int
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    tasks: list[TaskListItem] = Field(default_factory=list, description="List of tasks")
    total: int = Field(..., description="Total number of tasks matching filter")


class CancelTaskResponse(BaseModel):
    task_id: str = Field(..., description="Task identifier")
    cancelled: bool = Field(..., description="Whether task was cancelled")
    message: str = Field(..., description="Status message")


class BackendInfo(BaseModel):
    name: str = Field(..., description="Backend name")
    description: str = Field(..., description="Backend description")


class BackendsResponse(BaseModel):
    backends: list[BackendInfo] = Field(default_factory=list, description="List of backends")


class ErrorResponse(BaseModel):
    status: str = Field(default="error", description="Error status")
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: Optional[dict] = Field(default=None, description="Detailed error information")


class QueueStatsWrapper(BaseModel):
    queue_stats: QueueStatsResponse = Field(..., description="Queue statistics")
    total: int = Field(..., description="Total tasks count")
