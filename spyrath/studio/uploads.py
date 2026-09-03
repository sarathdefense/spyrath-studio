from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from spyrath.project import ProjectSpec

from .manuscript import read_manuscript
from .repository import ProjectRepository


class ProjectAssetStore:
    """Copy user-selected inputs into a project-owned, durable asset directory."""

    presenter_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    voice_extensions = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    manuscript_extensions = {".txt", ".md", ".markdown"}

    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def create_from_files(
        self,
        *,
        project_id: str,
        title: str,
        manuscript_path: str | Path,
        presenter_image_path: str | Path,
        voice_reference_path: str | Path,
        language: str = "en",
    ) -> ProjectSpec:
        # Validate ID before touching disk.
        root = self.repository.project_root(project_id)
        if self.repository.exists(project_id):
            raise ValueError(f"Project already exists: {project_id}")
        if not title.strip():
            raise ValueError("title must not be empty")

        manuscript = Path(manuscript_path)
        presenter = Path(presenter_image_path)
        voice = Path(voice_reference_path)
        self._validate_source(manuscript, self.manuscript_extensions, "manuscript")
        self._validate_source(presenter, self.presenter_extensions, "presenter image")
        self._validate_source(voice, self.voice_extensions, "voice reference")

        assets = root / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        copied_manuscript = self._copy(manuscript, assets / f"manuscript{manuscript.suffix.lower()}")
        copied_presenter = self._copy(presenter, assets / f"presenter{presenter.suffix.lower()}")
        copied_voice = self._copy(voice, assets / f"voice{voice.suffix.lower()}")

        try:
            plan = read_manuscript(copied_manuscript)
            spec = ProjectSpec(
                project_id=project_id,
                title=title.strip(),
                chapters=plan.chapters,
                presenter_image=copied_presenter,
                voice_reference=copied_voice,
                language=language.strip() or "en",
            )
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        return spec

    @staticmethod
    def _validate_source(path: Path, allowed: set[str], label: str) -> None:
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"{label} does not exist or is empty")
        if path.suffix.lower() not in allowed:
            raise ValueError(f"Unsupported {label} file type: {path.suffix or '(none)'}")

    @staticmethod
    def _copy(source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(destination.name + ".tmp")
        shutil.copyfile(source, temp)
        os.replace(temp, destination)
        return destination


def safe_upload_filename(filename: str | None, fallback: str) -> str:
    name = Path(filename or fallback).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or fallback
