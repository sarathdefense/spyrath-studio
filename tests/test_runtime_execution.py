from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from spyrath.project import ProjectChapter, ProjectSpec, ProjectStage, ProjectStateStore, StageStatus
from spyrath.runtime import JobStatus, ProductionRuntime, RuntimeJobStore, RuntimePreflight
from spyrath.studio import ProjectRepository, StudioService, create_app


def test_job_store_recovers_interrupted_running_job(tmp_path):
    store = RuntimeJobStore(tmp_path / "jobs.json")
    job = store.create("book", resume=False)
    job.status = JobStatus.RUNNING
    store.update(job)
    assert store.recover_interrupted() == 1
    recovered = store.get(job.job_id)
    assert recovered.status == JobStatus.FAILED
    assert "interrupted" in recovered.error


def test_runtime_retries_failure_as_resume(tmp_path):
    store = RuntimeJobStore(tmp_path / "jobs.json")
    runtime = ProductionRuntime(job_store=store, max_workers=1, max_attempts=2)
    seen = []

    def callback(job):
        seen.append((job.attempts, job.resume))
        if job.attempts == 1:
            raise RuntimeError("transient GPU failure")

    runtime.submit("book", resume=False, callback=callback)
    runtime.wait("book", timeout=2)
    latest = store.latest_for_project("book")
    assert seen == [(1, False), (2, True)]
    assert latest.status == JobStatus.SUCCEEDED
    assert latest.attempts == 2


def test_runtime_prevents_duplicate_project_execution(tmp_path):
    store = RuntimeJobStore(tmp_path / "jobs.json")
    runtime = ProductionRuntime(job_store=store, max_workers=1)
    gate = threading.Event()
    runtime.submit("book", resume=False, callback=lambda job: gate.wait(1))
    with pytest.raises(RuntimeError, match="already running"):
        runtime.submit("book", resume=True, callback=lambda job: None)
    gate.set()
    runtime.wait("book", timeout=2)


def test_preflight_reports_required_tools_and_gpu(tmp_path, monkeypatch):
    repo = tmp_path / "SadTalker"
    repo.mkdir()
    (repo / "inference.py").write_text("# ok", encoding="utf-8")

    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    def runner(command, capture_output=True, text=True):
        if "nvidia-smi" in command[0]:
            return subprocess.CompletedProcess(command, 0, "Tesla T4, 15360 MiB\n", "")
        return subprocess.CompletedProcess(command, 0, "version ok\n", "")

    report = RuntimePreflight(
        sadtalker_repository=repo,
        sadtalker_python="python3",
        runner=runner,
    ).check()
    assert report.ready
    assert {x.name for x in report.capabilities} == {"sadtalker", "python", "ffmpeg", "ffprobe", "gpu"}


def test_preflight_can_require_gpu(tmp_path, monkeypatch):
    repo = tmp_path / "SadTalker"
    repo.mkdir(); (repo / "inference.py").write_text("# ok")
    monkeypatch.setattr("shutil.which", lambda name: None if name == "nvidia-smi" else f"/usr/bin/{name}")
    def runner(command, capture_output=True, text=True):
        return subprocess.CompletedProcess(command, 0, "ok\n", "")
    with pytest.raises(RuntimeError, match="gpu"):
        RuntimePreflight(sadtalker_repository=repo, sadtalker_python="python3", runner=runner).require_ready()
    assert RuntimePreflight(sadtalker_repository=repo, sadtalker_python="python3", require_gpu=False, runner=runner).check().ready


class FlakyOrchestrator:
    calls = 0
    def __init__(self, spec, root): self.spec, self.root = spec, root
    def run(self):
        type(self).calls += 1
        if type(self).calls == 1: raise RuntimeError("GPU reset")
        self._complete()
    def resume(self):
        type(self).calls += 1
        self._complete()
    def _complete(self):
        store = ProjectStateStore(self.root / "project.json")
        state = store.load(self.spec)
        for stage in ProjectStage:
            item = state.stage(stage); item.status = StageStatus.COMPLETED
            f = self.root / "a" / f"{stage.value}.bin"; f.parent.mkdir(exist_ok=True); f.write_bytes(b"ok")
            item.artifacts=[str(f)]
        final=self.root/"final"/"x.mp4"; final.parent.mkdir(exist_ok=True); final.write_bytes(b"mp4")
        state.stage(ProjectStage.EXPORT).artifacts=[str(final)]
        store.save(state)


def test_studio_service_persists_runtime_job_and_retries(tmp_path):
    FlakyOrchestrator.calls = 0
    repo = ProjectRepository(tmp_path / "projects")
    service = StudioService(repository=repo, orchestrator_factory=lambda s,r: FlakyOrchestrator(s,r), max_attempts=2)
    spec = ProjectSpec("book", "Book", (ProjectChapter.from_texts("c1", ["Hello"]),), Path("p.png"), Path("v.wav"))
    service.create_project(spec)
    service.run_project("book")
    summary = service.wait("book", timeout=2)
    assert summary.status == "completed"
    assert summary.runtime_job["status"] == "succeeded"
    assert summary.runtime_job["attempts"] == 2
    payload = json.loads((repo.root / ".runtime" / "jobs.json").read_text())
    assert payload["jobs"][0]["project_id"] == "book"


def test_runtime_api_exposes_job_state(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    repo = ProjectRepository(tmp_path / "projects")
    service = StudioService(repository=repo, orchestrator_factory=lambda s,r: FlakyOrchestrator(s,r), max_attempts=1)
    spec = ProjectSpec("book", "Book", (ProjectChapter.from_texts("c1", ["Hello"]),), Path("p.png"), Path("v.wav"))
    service.create_project(spec)
    client = TestClient(create_app(service))
    assert client.get("/api/projects/book/runtime").json() == {"job": None}
    service.run_project("book")
    try: service.wait("book", timeout=2)
    except RuntimeError: pass
    body = client.get("/api/projects/book/runtime").json()
    assert body["job"]["project_id"] == "book"
    assert client.get("/api/runtime/jobs").status_code == 200
