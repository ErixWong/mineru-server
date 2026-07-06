"""
Services Package

Shared business logic layer for MinerU MCP Server.
Provides reusable service classes that can be used by both
REST API (api.py) and MCP Protocol (server.py).

Current services:
- TaskService: Task creation, status query, deliverable operations
"""

from mineru_mcp.services.task_service import (
    TaskService,
    get_task_service,
    reset_task_service,
)

__all__ = [
    "TaskService",
    "get_task_service",
    "reset_task_service",
]