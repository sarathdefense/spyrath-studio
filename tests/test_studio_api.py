from __future__ import annotations

from pathlib import Path

import pytest

from spyrath.project import ProjectChapter, ProjectSpec, ProjectStage, ProjectStateStore, StageStatus
from spyrath.studio import ProjectRepository, StudioService, create_app


class FakeOrchestrator:
    def __init__(self, spec: ProjectSpec, root: Path, *, fail: bool = False):
        self.spec = spec
        self.root = root
        self.fail = fail

    def run(self):
        store = ProjectStateStore(self.root / "project.json")
        state = store.load(self.spec)
        for stage in ProjectStage:
            item = state.stage(stage)
            if self.fail and stage == ProjectStage.PRESENTER:
                item.status = StageStatus.FAILED
                item.error = "GPU unavailable"
                state.last_error = "GPU unavailable"
                store.save(state)
                raise RuntimeError("GPU unavailable")
            item.status = StageStatus.COMPLETED
            artifact = self.root / "artifacts" / f"{stage.value}.bin"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"ok")
            item.artifacts = [str(artifact)]
            item.error = None
            store.save(state)

        final = self.root / "final" / "project_presenter.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"fake mp4")
        state.stage(ProjectStage.EXPORT).artifacts = [str(final)]
        state.last_error = None
        store.save(state)
        return object()

    def resume(self):
        return self.run()


def make_spec(project_id: str = "book") -> ProjectSpec:
    return ProjectSpec(
        project_id=project_id,
        title="Machine Learning for Beginners",
        chapters=(ProjectChapter.from_texts("chapter_01", ["Hello world"]),),
        presenter_image=Path("presenter.png"),
        voice_reference=Path("voice.wav"),
    )


def make_service(tmp_path: Path, *, fail: bool = False) -> StudioService:
    repository = ProjectRepository(tmp_path / "projects")
    return StudioService(
        repository=repository,
        orchestrator_factory=lambda spec, root: FakeOrchestrator(spec, root, fail=fail),
    )


def test_repository_persists_and_lists_project_specs(tmp_path):
    repo = ProjectRepository(tmp_path / "projects")
    spec = make_spec()
    repo.create(spec)

    loaded = repo.load("book")
    assert loaded.project_id == "book"
    assert loaded.title == spec.title
    assert loaded.chapters[0].texts == ("Hello world",)
    assert [item.project_id for item in repo.list()] == ["book"]


def test_studio_service_runs_in_background_and_exposes_final_download(tmp_path):
    service = make_service(tmp_path)
    created = service.create_project(make_spec())
    assert created.status == "pending"
    assert created.progress_percent == 0

    started = service.run_project("book")
    assert started.project_id == "book"
    completed = service.wait("book", timeout=2)
    assert completed.status == "completed"
    assert completed.progress_percent == 100
    assert Path(completed.final_path).is_file()
    assert service.final_download("book") == Path(completed.final_path)


def test_studio_service_surfaces_persisted_failure(tmp_path):
    service = make_service(tmp_path, fail=True)
    service.create_project(make_spec())
    service.run_project("book")
    with pytest.raises(RuntimeError, match="GPU unavailable"):
        service.wait("book", timeout=2)

    summary = service.get_project("book")
    assert summary.status == "failed"
    assert summary.last_error == "GPU unavailable"
    assert summary.stages[ProjectStage.PRESENTER.value]["status"] == "failed"


def test_duplicate_project_is_rejected(tmp_path):
    service = make_service(tmp_path)
    service.create_project(make_spec())
    with pytest.raises(ValueError, match="already exists"):
        service.create_project(make_spec())


def test_project_id_is_path_safe(tmp_path):
    repo = ProjectRepository(tmp_path / "projects")
    with pytest.raises(ValueError):
        repo.project_root("../escape")


def test_fastapi_dashboard_and_project_endpoints(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    pytest.importorskip("starlette")
    from fastapi.testclient import TestClient

    service = make_service(tmp_path)
    app = create_app(service)
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Spyrath Studio" in dashboard.text

    payload = {
        "project_id": "book",
        "title": "Machine Learning for Beginners",
        "presenter_image": "presenter.png",
        "voice_reference": "voice.wav",
        "chapters": [{"chapter_id": "chapter_01", "texts": ["Hello world"]}],
    }
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 201
    assert response.json()["progress_percent"] == 0

    listed = client.get("/api/projects").json()["projects"]
    assert [item["project_id"] for item in listed] == ["book"]

    start = client.post("/api/projects/book/run")
    assert start.status_code == 202
    service.wait("book", timeout=2)
    detail = client.get("/api/projects/book").json()
    assert detail["status"] == "completed"
    assert detail["progress_percent"] == 100

    download = client.get("/api/projects/book/download")
    assert download.status_code == 200
    assert download.content == b"fake mp4"
