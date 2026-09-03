from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from spyrath.project import ProjectOrchestrator, ProjectSpec, ProjectStage, ProjectState, ProjectStateStore, StageStatus
from spyrath.runtime import ProductionRuntime, RuntimeJob, RuntimeJobStore

from .repository import ProjectRepository

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
    runtime_job: dict[str, object] | None = None

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
            "runtime_job": self.runtime_job,
        }


class StudioService:
    """Application service backed by a durable production runtime.

    Runtime jobs are recorded on disk before execution, bounded by max_workers,
    retried as resumable runs, and recover cleanly after process interruption.
    The project.json/media artifacts remain the pipeline source of truth.
    """

    def __init__(
        self,
        *,
        repository: ProjectRepository,
        orchestrator_factory: OrchestratorFactory,
        max_workers: int = 1,
        max_attempts: int = 1,
        runtime_preflight: Callable[[], object] | None = None,
        runtime: ProductionRuntime | None = None,
    ) -> None:
        if max_workers <= 0 or max_attempts <= 0:
            raise ValueError("max_workers and max_attempts must be > 0")
        self.repository = repository
        self.orchestrator_factory = orchestrator_factory
        self.runtime = runtime or ProductionRuntime(
            job_store=RuntimeJobStore(repository.root / ".runtime" / "jobs.json"),
            max_workers=max_workers,
            max_attempts=max_attempts,
            preflight=runtime_preflight,
        )

    def create_project(self, spec: ProjectSpec) -> ProjectSummary:
        self.repository.create(spec)
        ProjectStateStore(self.repository.state_path(spec.project_id)).save(ProjectState.new(spec))
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
        latest = self.runtime.latest(project_id)
        return ProjectSummary(
            project_id=spec.project_id,
            title=spec.title,
            status=overall,
            progress_percent=progress,
            stages=stages,
            last_error=state.last_error,
            final_path=final_path,
            running=running,
            runtime_job=latest.as_dict() if latest else None,
        )

    def run_project(self, project_id: str, *, resume: bool = False) -> ProjectSummary:
        spec = self.repository.load(project_id)
        self.runtime.submit(
            project_id,
            resume=resume,
            callback=lambda job: self._execute(spec, job),
        )
        return self.get_project(project_id)

    def is_running(self, project_id: str) -> bool:
        return self.runtime.is_running(project_id)

    def wait(self, project_id: str, timeout: float | None = None) -> ProjectSummary:
        self.runtime.wait(project_id, timeout=timeout)
        return self.get_project(project_id)

    def latest_job(self, project_id: str) -> RuntimeJob | None:
        self.repository.load(project_id)  # enforce not-found semantics
        return self.runtime.latest(project_id)

    def list_jobs(self) -> list[RuntimeJob]:
        return self.runtime.job_store.list()

    def final_download(self, project_id: str) -> Path:
        summary = self.get_project(project_id)
        if not summary.final_path:
            raise FileNotFoundError("Final video is not ready")
        path = Path(summary.final_path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise FileNotFoundError("Final video artifact is missing")
        return path

    def _execute(self, spec: ProjectSpec, job: RuntimeJob) -> None:
        orchestrator = self.orchestrator_factory(spec, self.repository.project_root(spec.project_id))
        if job.resume or job.attempts > 1:
            orchestrator.resume()
        else:
            orchestrator.run()
