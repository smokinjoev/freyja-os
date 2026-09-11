from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from freyja import cloyd_coder


def test_create_job_requires_allowlisted_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLOYD_CODER_STATE_DIR", str(tmp_path))
    client = TestClient(cloyd_coder.app)

    response = client.post("/jobs", json={"project": "nope", "prompt": "status"})

    assert response.status_code == 400
    assert "family-dashboard" in response.text


def test_job_lifecycle_persists_real_opencode_result(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("CLOYD_CODER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setitem(cloyd_coder.PROJECTS, "family-dashboard", str(repo))

    def fake_git_files(cwd: str) -> set[str]:
        assert cwd == str(repo)
        marker = repo / "changed.txt"
        return {"changed.txt"} if marker.exists() else set()

    def fake_send(job: cloyd_coder.Job) -> dict[str, object]:
        (repo / "changed.txt").write_text("changed\n", encoding="utf-8")
        return {
            "ok": True,
            "session": "ses_test",
            "state": "completed",
            "result": "actual OpenCode output",
        }

    monkeypatch.setattr(cloyd_coder, "git_files", fake_git_files)
    monkeypatch.setattr(cloyd_coder, "_run_opencode_send", fake_send)
    client = TestClient(cloyd_coder.app)

    created = client.post("/jobs", json={"project": "family-dashboard", "prompt": "inspect only"})

    assert created.status_code == 200
    job_id = created.json()["id"]
    for _ in range(50):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] == "completed":
            break
        time.sleep(0.05)

    assert status["cwd"] == str(repo)
    assert status["opencode_session"] == "ses_test"
    assert status["changed_files"] == ["changed.txt"]
    log = client.get(f"/jobs/{job_id}/log").json()["log"]
    assert "actual OpenCode output" in log


def test_openwebui_cloyd_coder_tool_source_defines_expected_methods() -> None:
    import ast

    source = Path("ops/openwebui/create_iris_tools.py").read_text(encoding="utf-8")
    module_ast = ast.parse(source)
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module_ast.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "CLOYD_CODER"
    }
    namespace: dict[str, object] = {}
    exec(constants["CLOYD_CODER"], namespace)
    tools = namespace.get("Tools")
    assert isinstance(tools, type)
    for method in ("coder_start", "coder_status", "coder_log", "coder_cancel"):
        assert callable(getattr(tools(), method))
