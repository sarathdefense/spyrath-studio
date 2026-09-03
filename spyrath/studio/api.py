from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from spyrath.project import ProjectChapter, ProjectSpec

from .dashboard import DASHBOARD_HTML
from .repository import ProjectNotFoundError
from .service import StudioService
from .uploads import ProjectAssetStore, safe_upload_filename


def create_app(service: StudioService):
    """Create the FastAPI application without making FastAPI a core dependency."""
    try:
        from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
        from fastapi.responses import FileResponse, HTMLResponse
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            'Install Spyrath Studio API dependencies with: pip install -e ".[studio]"'
        ) from exc

    app = FastAPI(title="Spyrath Studio API", version="0.1.0")
    assets = ProjectAssetStore(service.repository)

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return DASHBOARD_HTML

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/projects")
    def list_projects():
        return {"projects": [item.as_dict() for item in service.list_projects()]}

    @app.get("/api/runtime/jobs")
    def list_runtime_jobs():
        return {"jobs": [job.as_dict() for job in service.list_jobs()]}

    @app.get("/api/projects/{project_id}/runtime")
    def project_runtime(project_id: str):
        try:
            job = service.latest_job(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        return {"job": job.as_dict() if job else None}

    @app.post("/api/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: dict):
        """Backward-compatible JSON project creation endpoint."""
        try:
            spec = _spec_from_payload(payload)
            return service.create_project(spec).as_dict()
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/upload", status_code=status.HTTP_201_CREATED)
    async def create_project_upload(
        project_id: str = Form(...),
        title: str = Form(...),
        language: str = Form("en"),
        manuscript: Any = File(...),
        presenter_image: Any = File(...),
        voice_reference: Any = File(...),
    ):
        """Create a durable project from browser-uploaded production assets."""
        try:
            with tempfile.TemporaryDirectory(prefix="spyrath-upload-") as temp_dir:
                temp = Path(temp_dir)
                manuscript_path = await _save_upload(manuscript, temp)
                presenter_path = await _save_upload(presenter_image, temp)
                voice_path = await _save_upload(voice_reference, temp)
                spec = assets.create_from_files(
                    project_id=project_id,
                    title=title,
                    manuscript_path=manuscript_path,
                    presenter_image_path=presenter_path,
                    voice_reference_path=voice_path,
                    language=language,
                )
                return service.create_project(spec).as_dict()
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        try:
            return service.get_project(project_id).as_dict()
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc

    @app.post("/api/projects/{project_id}/run", status_code=status.HTTP_202_ACCEPTED)
    def run_project(project_id: str):
        return _start(project_id, resume=False)

    @app.post("/api/projects/{project_id}/resume", status_code=status.HTTP_202_ACCEPTED)
    def resume_project(project_id: str):
        return _start(project_id, resume=True)

    @app.get("/api/projects/{project_id}/download")
    def download(project_id: str):
        try:
            path = service.final_download(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    def _start(project_id: str, *, resume: bool):
        try:
            summary = service.run_project(project_id, resume=resume)
            return summary.as_dict()
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


async def _save_upload(upload, directory: Path) -> Path:
    filename = safe_upload_filename(getattr(upload, "filename", None), "upload.bin")
    destination = directory / filename
    total = 0
    max_bytes = 100 * 1024 * 1024
    with destination.open("wb") as handle:
        while True:
            block = await upload.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                raise ValueError(f"Upload is too large: {filename} (100 MB maximum per asset)")
            handle.write(block)
    if total == 0:
        raise ValueError(f"Uploaded file is empty: {filename}")
    return destination


def _spec_from_payload(payload: dict) -> ProjectSpec:
    chapters_payload = payload.get("chapters")
    if not isinstance(chapters_payload, list) or not chapters_payload:
        raise ValueError("chapters must be a non-empty list")
    chapters = tuple(
        ProjectChapter.from_texts(str(item["chapter_id"]), item["texts"])
        for item in chapters_payload
    )
    voice = payload.get("voice_reference")
    return ProjectSpec(
        project_id=str(payload["project_id"]),
        title=str(payload["title"]),
        chapters=chapters,
        presenter_image=Path(payload["presenter_image"]),
        voice_reference=Path(voice) if voice else None,
        language=str(payload.get("language", "en")),
    )
