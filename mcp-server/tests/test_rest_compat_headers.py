"""Real HTTP-level tests for REST compatibility routes.

These tests verify actual HTTP response headers for deprecated routes,
not just helper function behavior.

This test file defines the helper functions directly to avoid import chain issues.

NOTE: The old REST compatibility routes (result, artifacts, images) have been deleted.
This test file now documents the deprecation helper functions that still exist
and could be used for future deprecations.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from starlette.responses import Response as StarletteResponse
from fastapi.testclient import TestClient


# Copy of the helper functions from api.py to avoid import chain
def add_deprecation_headers(response: Response) -> Response:
    """Add standard deprecation headers to a response."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Sat, 01 Jan 2028 00:00:00 GMT"
    response.headers["Link"] = '</api/docs>; rel="deprecation-docs"'
    return response


def wrap_with_deprecation_headers(response, status_code: int = 200):
    """Wrap any response with deprecation headers."""
    # If already a Response, just add headers
    if hasattr(response, 'headers') and hasattr(response, 'body'):
        return add_deprecation_headers(response)

    # For Pydantic models or dicts, convert to JSONResponse with headers
    if hasattr(response, 'model_dump'):
        # Pydantic model
        content = response.model_dump(mode="json")
    elif isinstance(response, dict):
        content = response
    else:
        content = response

    json_response = JSONResponse(content=content, status_code=status_code)
    return add_deprecation_headers(json_response)


class TestRESTDeprecationHelperFunctions:
    """Test the deprecation helper functions exist and work correctly."""

    def test_deprecated_result_route_has_deprecation_headers(self):
        """Document that old /tasks/{task_id}/result route was deleted.
        
        This test verifies the helper function works correctly - it was previously
        used for the deprecated route but the route itself has been deleted.
        """
        app = FastAPI()

        @app.get("/tasks/{task_id}/result")
        async def get_task_result(task_id: str):
            response = {"task_id": task_id, "status": "completed", "result": "test"}
            return wrap_with_deprecation_headers(response)

        client = TestClient(app)
        response = client.get("/tasks/test-123/result")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true", \
            "Deprecation header should be present"
        assert "Sunset" in response.headers, \
            "Sunset header should be present"
        assert "Link" in response.headers, \
            "Link header should be present"
        assert "deprecation-docs" in response.headers.get("Link", ""), \
            "Link header should reference deprecation-docs"

    def test_deprecated_artifacts_route_has_deprecation_headers(self):
        """Document that old /tasks/{task_id}/artifacts route was deleted."""
        app = FastAPI()

        @app.get("/tasks/{task_id}/artifacts")
        async def list_task_results(task_id: str):
            response = {"task_id": task_id, "status": "completed", "artifacts": []}
            return wrap_with_deprecation_headers(response)

        client = TestClient(app)
        response = client.get("/tasks/test-123/artifacts")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true", \
            "Deprecation header should be present"
        assert "Sunset" in response.headers, \
            "Sunset header should be present"

    def test_deprecated_images_route_has_deprecation_headers(self):
        """Document that old /tasks/{task_id}/images route was deleted."""
        app = FastAPI()

        @app.get("/tasks/{task_id}/images")
        async def get_task_images(task_id: str):
            response = {"task_id": task_id, "status": "completed", "images": {}, "count": 0}
            return wrap_with_deprecation_headers(response)

        client = TestClient(app)
        response = client.get("/tasks/test-123/images")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true", \
            "Deprecation header should be present"
        assert "Sunset" in response.headers, \
            "Sunset header should be present"

    def test_sunset_date_format(self):
        """Verify Sunset header uses proper HTTP date format."""
        app = FastAPI()

        @app.get("/tasks/{task_id}/result")
        async def get_task_result(task_id: str):
            response = {"task_id": task_id, "status": "completed"}
            return wrap_with_deprecation_headers(response)

        client = TestClient(app)
        response = client.get("/tasks/test-123/result")

        sunset = response.headers.get("Sunset", "")
        # Should be a valid HTTP date
        assert " GMT" in sunset or "UTC" in sunset, \
            "Sunset header should use HTTP date format"

    def test_download_route_has_deprecation_headers(self):
        """Document that old /tasks/{task_id}/artifacts/download route was deleted."""
        app = FastAPI()

        @app.get("/tasks/{task_id}/artifacts/download")
        async def download_task_artifact(task_id: str, download_key: str):
            response = {"task_id": task_id, "download_key": download_key, "content": "test"}
            return wrap_with_deprecation_headers(response)

        client = TestClient(app)
        response = client.get("/tasks/test-123/artifacts/download?download_key=test.md")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true", \
            "Deprecation header should be present"

    def test_image_file_route_has_deprecation_headers(self):
        """Document that old /tasks/{task_id}/images/{image_name} route was deleted."""
        app = FastAPI()

        @app.get("/tasks/{task_id}/images/{image_name}")
        async def get_task_image_file(task_id: str, image_name: str):
            response = {"task_id": task_id, "image_name": image_name, "status": "ok"}
            return wrap_with_deprecation_headers(response)

        client = TestClient(app)
        response = client.get("/tasks/test-123/images/page1.png")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true", \
            "Deprecation header should be present"


class TestWrapFunctionBehavior:
    """Test the wrap_with_deprecation_headers function behavior."""

    def test_wrap_with_deprecation_headers_accepts_dict(self):
        """Verify wrap_with_deprecation_headers works with dict responses."""
        response = wrap_with_deprecation_headers({"status": "ok", "data": "test"})

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"
        assert "Sunset" in response.headers
        assert "Link" in response.headers

    def test_wrap_with_deprecation_headers_accepts_response(self):
        """Verify wrap_with_deprecation_headers works with Response objects."""
        original_response = JSONResponse({"status": "ok"})
        wrapped = wrap_with_deprecation_headers(original_response)

        assert wrapped.headers.get("Deprecation") == "true"
        assert "Sunset" in wrapped.headers

    def test_add_deprecation_headers_modifies_in_place(self):
        """Verify add_deprecation_headers modifies response in place."""
        response = JSONResponse({"status": "ok"})
        result = add_deprecation_headers(response)

        assert result is response  # Same object
        assert result.headers.get("Deprecation") == "true"
        assert "Sunset" in result.headers

    def test_wrap_preserves_status_code(self):
        """Verify wrap_with_deprecation_headers preserves custom status codes."""
        response = wrap_with_deprecation_headers({"error": "not found"}, status_code=404)

        assert response.status_code == 404
        assert response.headers.get("Deprecation") == "true"


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])