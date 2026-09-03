from __future__ import annotations

from pathlib import Path

from spyrath.project import ProjectChapter, ProjectSpec

from .dashboard import DASHBOARD_HTML
from .repository import ProjectNotFoundError
from .service import StudioService


def create_app(service: StudioService):
    """Create the FastAPI application without making FastAPI a core dependency."""
    try:
        from fastapi import FastAPI, HTTPException, Response, status
        from fastapi.responses import FileResponse, HTMLResponse
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError('Install Spyrath Studio API dependencies with: pip install -e ".[studio]"') from exc

    app = FastAPI(title="Spyrath Studio API", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return DASHBOARD_HTML

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/projects")
    def list_projects():
        return {"projects": [item.as_dict() for item in service.list_projects()]}

    @app.post("/api/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: dict):
        try:
            spec = _spec_from_payload(payload)
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
