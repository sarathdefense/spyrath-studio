from __future__ import annotations

from pathlib import Path

import pytest

from spyrath.project import ProjectStage, ProjectStateStore, StageStatus
from spyrath.studio import (
    ProjectAssetStore,
    ProjectRepository,
    StudioRuntimeConfig,
    StudioService,
    create_app,
    parse_manuscript,
)


class FakeOrchestrator:
    def __init__(self, spec, root):
        self.spec = spec
        self.root = root

    def run(self):
        store = ProjectStateStore(self.root / "project.json")
        state = store.load(self.spec)
        for stage in ProjectStage:
            item = state.stage(stage)
            item.status = StageStatus.COMPLETED
            artifact = self.root / "artifacts" / f"{stage.value}.bin"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"ok")
            item.artifacts = [str(artifact)]
        final = self.root / "final" / "final.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"mp4")
        state.stage(ProjectStage.EXPORT).artifacts = [str(final)]
        store.save(state)

    def resume(self):
        return self.run()


def write_assets(tmp_path: Path):
    manuscript = tmp_path / "book.md"
    manuscript.write_text("# Preface\nHello reader.\n\n# Chapter One\nThis is the first chapter.", encoding="utf-8")
    presenter = tmp_path / "presenter.png"
    presenter.write_bytes(b"png-data")
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"wav-data")
    return manuscript, presenter, voice


def test_manuscript_parser_uses_markdown_headings_as_chapters():
    plan = parse_manuscript("# Preface\nWelcome.\n\n## First Steps\nBuild something useful.")
    assert [c.chapter_id for c in plan.chapters] == ["01_preface", "02_first_steps"]
    assert plan.segment_count == 2
    assert plan.chapters[1].texts == ("Build something useful.",)


def test_manuscript_parser_splits_long_plain_text():
    text = " ".join(["This is a sentence." for _ in range(80)])
    plan = parse_manuscript(text, max_segment_chars=220)
    assert len(plan.chapters) == 1
    assert plan.chapters[0].chapter_id == "chapter_01"
    assert len(plan.chapters[0].texts) > 1
    assert all(len(segment) <= 220 for segment in plan.chapters[0].texts)


def test_asset_store_copies_inputs_into_project_and_builds_spec(tmp_path):
    repo = ProjectRepository(tmp_path / "projects")
    manuscript, presenter, voice = write_assets(tmp_path)
    spec = ProjectAssetStore(repo).create_from_files(
        project_id="ml-book",
        title="Machine Learning for Beginners",
        manuscript_path=manuscript,
        presenter_image_path=presenter,
        voice_reference_path=voice,
    )
    assert spec.project_id == "ml-book"
    assert len(spec.chapters) == 2
    assert spec.presenter_image.parent.name == "assets"
    assert spec.voice_reference.parent.name == "assets"
    assert spec.presenter_image.read_bytes() == b"png-data"
    assert spec.voice_reference.read_bytes() == b"wav-data"


def test_asset_store_rejects_unsupported_manuscript_and_cleans_project(tmp_path):
    repo = ProjectRepository(tmp_path / "projects")
    manuscript, presenter, voice = write_assets(tmp_path)
    manuscript = tmp_path / "book.pdf"
    manuscript.write_bytes(b"pdf")
    with pytest.raises(ValueError, match="Unsupported manuscript"):
        ProjectAssetStore(repo).create_from_files(
            project_id="bad-book",
            title="Bad",
            manuscript_path=manuscript,
            presenter_image_path=presenter,
            voice_reference_path=voice,
        )
    assert not repo.project_root("bad-book").exists()


def test_runtime_config_requires_real_sadtalker_checkout(tmp_path):
    config = StudioRuntimeConfig(projects_root=tmp_path / "projects", sadtalker_repository=None)
    with pytest.raises(RuntimeError, match="SPYRATH_SADTALKER_REPO"):
        config.validate_for_production()

    repo = tmp_path / "SadTalker"
    repo.mkdir()
    (repo / "inference.py").write_text("# fake", encoding="utf-8")
    StudioRuntimeConfig(projects_root=tmp_path / "projects", sadtalker_repository=repo).validate_for_production()


def test_upload_endpoint_creates_durable_project_from_browser_assets(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    repository = ProjectRepository(tmp_path / "projects")
    service = StudioService(
        repository=repository,
        orchestrator_factory=lambda spec, root: FakeOrchestrator(spec, root),
    )
    client = TestClient(create_app(service))
    response = client.post(
        "/api/projects/upload",
        data={"project_id": "browser-book", "title": "Browser Book", "language": "en"},
        files={
            "manuscript": ("book.md", b"# Intro\nHello from browser.", "text/markdown"),
            "presenter_image": ("presenter.png", b"image", "image/png"),
            "voice_reference": ("voice.wav", b"audio", "audio/wav"),
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["project_id"] == "browser-book"
    assert body["status"] == "pending"

    spec = repository.load("browser-book")
    assert spec.chapters[0].texts == ("Hello from browser.",)
    assert spec.presenter_image.is_file()
    assert spec.voice_reference.is_file()
    assert spec.presenter_image.parent == repository.project_root("browser-book") / "assets"

    dashboard = client.get("/")
    assert "+ New Project" in dashboard.text
    assert "/api/projects/upload" in dashboard.text


def test_upload_endpoint_rejects_bad_file_type_without_registering_project(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    repository = ProjectRepository(tmp_path / "projects")
    service = StudioService(repository=repository, orchestrator_factory=lambda spec, root: FakeOrchestrator(spec, root))
    client = TestClient(create_app(service))
    response = client.post(
        "/api/projects/upload",
        data={"project_id": "bad", "title": "Bad"},
        files={
            "manuscript": ("book.pdf", b"pdf", "application/pdf"),
            "presenter_image": ("presenter.png", b"image", "image/png"),
            "voice_reference": ("voice.wav", b"audio", "audio/wav"),
        },
    )
    assert response.status_code == 400
    assert not repository.exists("bad")
