from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from .jobs import JobStatus, RuntimeJob, RuntimeJobStore, _now


class ProductionRuntime:
    """Bounded worker runtime with durable job state and retry semantics."""

    def __init__(self, *, job_store: RuntimeJobStore, max_workers: int = 1, max_attempts: int = 2, preflight: Callable[[], object] | None = None):
        if max_workers <= 0 or max_attempts <= 0:
            raise ValueError("max_workers and max_attempts must be > 0")
        self.job_store = job_store
        self.max_attempts = max_attempts
        self.preflight = preflight
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="spyrath-worker")
        self._futures: dict[str, Future] = {}
        self._project_jobs: dict[str, str] = {}
        self._lock = threading.RLock()
        self.job_store.recover_interrupted()

    def submit(self, project_id: str, *, resume: bool, callback: Callable[[RuntimeJob], None]) -> RuntimeJob:
        with self._lock:
            existing_id = self._project_jobs.get(project_id)
            if existing_id:
                future = self._futures.get(existing_id)
                if future is not None and not future.done():
                    raise RuntimeError(f"Project is already running: {project_id}")
            job = self.job_store.create(project_id, resume=resume, max_attempts=self.max_attempts)
            future = self.executor.submit(self._run, job.job_id, callback)
            self._futures[job.job_id] = future
            self._project_jobs[project_id] = job.job_id
            return job

    def is_running(self, project_id: str) -> bool:
        with self._lock:
            job_id = self._project_jobs.get(project_id)
            future = self._futures.get(job_id) if job_id else None
            return bool(future is not None and not future.done())

    def wait(self, project_id: str, timeout: float | None = None) -> RuntimeJob | None:
        with self._lock:
            job_id = self._project_jobs.get(project_id)
            future = self._futures.get(job_id) if job_id else None
        if future is not None:
            future.result(timeout=timeout)
        return self.job_store.get(job_id) if job_id else self.job_store.latest_for_project(project_id)

    def latest(self, project_id: str) -> RuntimeJob | None:
        return self.job_store.latest_for_project(project_id)

    def _run(self, job_id: str, callback: Callable[[RuntimeJob], None]) -> None:
        job = self.job_store.get(job_id)
        last_error: Exception | None = None
        for attempt in range(1, job.max_attempts + 1):
            job = self.job_store.get(job_id)
            job.status = JobStatus.RUNNING
            job.attempts = attempt
            job.started_at = job.started_at or _now()
            job.finished_at = None
            job.error = None
            self.job_store.update(job)
            try:
                if self.preflight is not None:
                    self.preflight()
                callback(job)
            except Exception as exc:
                last_error = exc
                job = self.job_store.get(job_id)
                job.error = str(exc)
                self.job_store.update(job)
                if attempt < job.max_attempts:
                    job.resume = True
                    self.job_store.update(job)
                    continue
                job.status = JobStatus.FAILED
                job.finished_at = _now()
                self.job_store.update(job)
                raise
            else:
                job = self.job_store.get(job_id)
                job.status = JobStatus.SUCCEEDED
                job.finished_at = _now()
                job.error = None
                self.job_store.update(job)
                return
        if last_error is not None:
            raise last_error
