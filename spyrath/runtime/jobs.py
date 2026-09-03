from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeJob:
    job_id: str
    project_id: str
    resume: bool
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    max_attempts: int = 1
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


class RuntimeJobStore:
    """Small atomic JSON job ledger used for runtime observability/recovery."""

    version = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def create(self, project_id: str, *, resume: bool, max_attempts: int = 1) -> RuntimeJob:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be > 0")
        job = RuntimeJob(
            job_id=uuid.uuid4().hex,
            project_id=project_id,
            resume=resume,
            max_attempts=max_attempts,
            created_at=_now(),
        )
        with self._lock:
            jobs = self._load_all()
            jobs[job.job_id] = job
            self._save_all(jobs)
        return job

    def get(self, job_id: str) -> RuntimeJob:
        with self._lock:
            jobs = self._load_all()
            if job_id not in jobs:
                raise KeyError(job_id)
            return jobs[job_id]

    def latest_for_project(self, project_id: str) -> RuntimeJob | None:
        with self._lock:
            matches = [j for j in self._load_all().values() if j.project_id == project_id]
        return max(matches, key=lambda j: j.created_at) if matches else None

    def list(self) -> list[RuntimeJob]:
        with self._lock:
            return sorted(self._load_all().values(), key=lambda j: j.created_at)

    def update(self, job: RuntimeJob) -> None:
        with self._lock:
            jobs = self._load_all()
            jobs[job.job_id] = job
            self._save_all(jobs)

    def recover_interrupted(self) -> int:
        """Mark jobs left RUNNING by a dead process as failed/recoverable."""
        changed = 0
        with self._lock:
            jobs = self._load_all()
            for job in jobs.values():
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.FAILED
                    job.finished_at = _now()
                    job.error = "Worker process interrupted; project can be resumed safely"
                    changed += 1
            if changed:
                self._save_all(jobs)
        return changed

    def _load_all(self) -> dict[str, RuntimeJob]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if payload.get("version") != self.version:
            return {}
        result: dict[str, RuntimeJob] = {}
        for raw in payload.get("jobs", []):
            try:
                job = RuntimeJob(
                    job_id=str(raw["job_id"]),
                    project_id=str(raw["project_id"]),
                    resume=bool(raw.get("resume", False)),
                    status=JobStatus(raw.get("status", "queued")),
                    attempts=int(raw.get("attempts", 0)),
                    max_attempts=int(raw.get("max_attempts", 1)),
                    created_at=str(raw.get("created_at", "")),
                    started_at=raw.get("started_at"),
                    finished_at=raw.get("finished_at"),
                    error=raw.get("error"),
                )
            except (KeyError, ValueError, TypeError):
                continue
            result[job.job_id] = job
        return result

    def _save_all(self, jobs: dict[str, RuntimeJob]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        payload = {"version": self.version, "jobs": [j.as_dict() for j in jobs.values()]}
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self.path)
