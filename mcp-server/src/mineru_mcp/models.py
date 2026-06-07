"""Pydantic Models for API and MCP Responses

Aligned with markitdown-server response structure for consistency.
"""

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
    markdown: Optional[str] = Field(default=None, description="Markdown content")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class TaskImagesResponse(BaseModel):
    task_id: str = Field(..., description="Task identifier")
    status: TaskStatus = Field(..., description="Task status")
    images: dict[str, str] = Field(default_factory=dict, description="Images as Base64 data URLs")
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
