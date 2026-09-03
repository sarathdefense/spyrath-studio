from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from spyrath.project import ProjectOrchestrator, ProjectSpec, ProjectStage, ProjectState, ProjectStateStore, StageStatus

from .repository import ProjectNotFoundError, ProjectRepository

OrchestratorFactory = Callable[[ProjectSpec, Path], ProjectOrchestrator]


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    title: str
    status: str
    progress_percent: int
    stages: dict[str, dict[str, object]]
    last_error: str | None
    final_path: str | None
    running: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "stages": self.stages,
            "last_error": self.last_error,
            "final_path": self.final_path,
            "running": self.running,
        }


class StudioService:
    """Application service behind the REST API and Studio dashboard.

    Expensive production runs execute on a worker thread so API requests can
    return immediately. The durable project.json written by ProjectOrchestrator
    remains the source of truth across process restarts.
    """

    def __init__(
        self,
        *,
        repository: ProjectRepository,
        orchestrator_factory: OrchestratorFactory,
        max_workers: int = 1,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be > 0")
        self.repository = repository
        self.orchestrator_factory = orchestrator_factory
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="spyrath")
        self._jobs: dict[str, Future] = {}
        self._lock = threading.Lock()

    def create_project(self, spec: ProjectSpec) -> ProjectSummary:
        self.repository.create(spec)
        # Seed project.json so a newly-created project is immediately visible
        # as four pending stages even before production starts.
        store = ProjectStateStore(self.repository.state_path(spec.project_id))
        store.save(ProjectState.new(spec))
        return self.get_project(spec.project_id)

    def list_projects(self) -> list[ProjectSummary]:
        return [self.get_project(spec.project_id) for spec in self.repository.list()]

    def get_project(self, project_id: str) -> ProjectSummary:
        spec = self.repository.load(project_id)
        state = ProjectStateStore(self.repository.state_path(project_id)).load(spec)
        running = self.is_running(project_id)
        completed = sum(1 for stage in ProjectStage if state.stage(stage).status == StageStatus.COMPLETED)
        progress = round((completed / len(ProjectStage)) * 100)
        stages = {
            stage.value: {
                "status": state.stage(stage).status.value,
                "artifacts": list(state.stage(stage).artifacts),
                "error": state.stage(stage).error,
            }
            for stage in ProjectStage
        }
        final_artifacts = state.stage(ProjectStage.EXPORT).artifacts
        final_path = final_artifacts[0] if final_artifacts else None
        if running:
            overall = "running"
        elif state.completed:
            overall = "completed"
        elif any(state.stage(stage).status == StageStatus.FAILED for stage in ProjectStage):
            overall = "failed"
        elif completed:
            overall = "partial"
        else:
            overall = "pending"
        return ProjectSummary(
            project_id=spec.project_id,
            title=spec.title,
            status=overall,
            progress_percent=progress,
            stages=stages,
            last_error=state.last_error,
            final_path=final_path,
            running=running,
        )

    def run_project(self, project_id: str, *, resume: bool = False) -> ProjectSummary:
        spec = self.repository.load(project_id)
        with self._lock:
            current = self._jobs.get(project_id)
            if current is not None and not current.done():
                raise RuntimeError(f"Project is already running: {project_id}")
            future = self.executor.submit(self._execute, spec, resume)
            self._jobs[project_id] = future
        return self.get_project(project_id)

    def is_running(self, project_id: str) -> bool:
        with self._lock:
            future = self._jobs.get(project_id)
            return bool(future is not None and not future.done())

    def wait(self, project_id: str, timeout: float | None = None) -> ProjectSummary:
        with self._lock:
            future = self._jobs.get(project_id)
        if future is not None:
            future.result(timeout=timeout)
        return self.get_project(project_id)

    def final_download(self, project_id: str) -> Path:
        summary = self.get_project(project_id)
        if not summary.final_path:
            raise FileNotFoundError("Final video is not ready")
        path = Path(summary.final_path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise FileNotFoundError("Final video artifact is missing")
        return path

    def _execute(self, spec: ProjectSpec, resume: bool) -> None:
        orchestrator = self.orchestrator_factory(spec, self.repository.project_root(spec.project_id))
        if resume:
            orchestrator.resume()
        else:
            orchestrator.run()
