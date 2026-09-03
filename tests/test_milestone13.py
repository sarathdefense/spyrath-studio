from pathlib import Path
import pytest

from spyrath.studio.accounts import AccountStore
from spyrath.studio.commercial import BETA_PLAN, UsageStore
from spyrath.studio.security import AccessController, SecurityConfig
from spyrath.studio import ProjectRepository, StudioService, create_app


def make_service(tmp_path):
    return StudioService(repository=ProjectRepository(tmp_path / "projects"), orchestrator_factory=lambda spec, root: None)


def test_beta_usage_is_durable_and_monthly(tmp_path):
    usage = UsageStore(tmp_path / "usage.db")
    usage.set_beta("alice")
    usage.record("alice", "production_start", "p1")
    usage.record("alice", "production_start", "p2")
    summary = UsageStore(tmp_path / "usage.db").summary("alice", 2)
    assert summary["plan"]["plan_id"] == "beta"
    assert summary["projects"] == {"used": 2, "limit": BETA_PLAN.max_projects}
    assert summary["production_starts"]["used"] == 2


def test_beta_project_limit_is_enforced(tmp_path):
    usage = UsageStore(tmp_path / "usage.db")
    usage.require_project_capacity("alice", BETA_PLAN.max_projects - 1)
    with pytest.raises(PermissionError, match="Project limit reached"):
        usage.require_project_capacity("alice", BETA_PLAN.max_projects)


def test_commercial_api_exposes_identity_plan_and_usage(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    service = make_service(tmp_path)
    accounts = AccountStore(tmp_path / "meta.db")
    accounts.ensure_user("alice", "Alice", "secret")
    access = AccessController(accounts, SecurityConfig(enabled=True))
    usage = UsageStore(tmp_path / "usage.db")
    client = TestClient(create_app(service, access=access, usage=usage))
    headers = {"X-Spyrath-Key": "secret"}
    assert client.get("/api/me", headers=headers).json()["user"]["user_id"] == "alice"
    assert client.get("/api/plans").json()["plans"][0]["plan_id"] == "beta"
    data = client.get("/api/usage", headers=headers).json()["usage"]
    assert data["projects"]["used"] == 0
    assert data["production_starts"]["used"] == 0


def test_project_media_routes_are_tenant_protected(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    service = make_service(tmp_path)
    accounts = AccountStore(tmp_path / "meta.db")
    accounts.ensure_user("alice", "Alice", "a")
    accounts.ensure_user("bob", "Bob", "b")
    access = AccessController(accounts, SecurityConfig(enabled=True))
    client = TestClient(create_app(service, access=access, usage=UsageStore(tmp_path / "usage.db")))
    payload = {"project_id":"book","title":"Book","presenter_image":"p.png","voice_reference":"v.wav","chapters":[{"chapter_id":"c","texts":["hello"]}]}
    assert client.post("/api/projects", json=payload, headers={"X-Spyrath-Key":"a"}).status_code == 201
    assert client.get("/api/projects/book/video", headers={"X-Spyrath-Key":"b"}).status_code == 404
    assert client.get("/api/projects/book/download", headers={"X-Spyrath-Key":"b"}).status_code == 404
    assert client.post("/api/projects/book/run", headers={"X-Spyrath-Key":"b"}).status_code == 404

def test_readiness_reports_failed_runtime_preflight(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    service = StudioService(
        repository=ProjectRepository(tmp_path / "projects"),
        orchestrator_factory=lambda spec, root: None,
        runtime_preflight=lambda: (_ for _ in ()).throw(RuntimeError("GPU unavailable")),
    )
    body = TestClient(create_app(service)).get("/api/ready").json()
    assert body["status"] == "not_ready"
    assert "GPU unavailable" in body["runtime"]["detail"]
