from pathlib import Path

from mineru_mcp.task_queue import FileManager


def test_output_contract_requires_md_and_middle_json(tmp_path):
    file_manager = FileManager(output_root=str(tmp_path))
    task_dir = tmp_path / "2026" / "06" / "07" / "task-output"
    task_dir.mkdir(parents=True, exist_ok=True)

    output_files = file_manager.get_output_files(task_dir, "document.pdf", "vlm-http-client")
    output_files["md"].parent.mkdir(parents=True, exist_ok=True)
    output_files["md"].write_text("# ok\n", encoding="utf-8")

    validation = file_manager.validate_task_outputs(task_dir, "document.pdf", "vlm-http-client")

    assert validation["required_missing"] == ["middle_json"]
    assert "content_list" in validation["recommended_missing"]
    assert "content_list_v2" in validation["recommended_missing"]
    assert "model_json" in validation["optional_missing"]


def test_output_contract_passes_when_required_outputs_exist(tmp_path):
    file_manager = FileManager(output_root=str(tmp_path))
    task_dir = tmp_path / "2026" / "06" / "07" / "task-output"
    task_dir.mkdir(parents=True, exist_ok=True)

    output_files = file_manager.get_output_files(task_dir, "document.pdf", "vlm-http-client")
    output_files["md"].parent.mkdir(parents=True, exist_ok=True)
    output_files["md"].write_text("# ok\n", encoding="utf-8")
    output_files["middle_json"].write_text("{}\n", encoding="utf-8")

    validation = file_manager.validate_task_outputs(task_dir, "document.pdf", "vlm-http-client")

    assert validation["required_missing"] == []
