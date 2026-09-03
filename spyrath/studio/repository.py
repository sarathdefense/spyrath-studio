from __future__ import annotations

import json
import os
import re
from pathlib import Path

from spyrath.project import ProjectChapter, ProjectSpec


class ProjectNotFoundError(KeyError):
    pass


class ProjectRepository:
    """Persistent project-spec registry used by the Studio/API layer."""

    version = 1

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: str) -> Path:
        return self.root / self._safe_id(project_id)

    def spec_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "spec.json"

    def state_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "project.json"

    def exists(self, project_id: str) -> bool:
        return self.spec_path(project_id).is_file()

    def create(self, spec: ProjectSpec) -> ProjectSpec:
        if self.exists(spec.project_id):
            raise ValueError(f"Project already exists: {spec.project_id}")
        self.save(spec)
        return spec

    def save(self, spec: ProjectSpec) -> None:
        path = self.spec_path(spec.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "project_id": spec.project_id,
            "title": spec.title,
            "presenter_image": str(spec.presenter_image),
            "voice_reference": str(spec.voice_reference) if spec.voice_reference else None,
            "language": spec.language,
            "chapters": [
                {"chapter_id": chapter.chapter_id, "texts": list(chapter.texts)}
                for chapter in spec.chapters
            ],
        }
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)

    def load(self, project_id: str) -> ProjectSpec:
        path = self.spec_path(project_id)
        if not path.is_file():
            raise ProjectNotFoundError(project_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid project spec: {path}") from exc
        if payload.get("version") != self.version:
            raise RuntimeError(f"Unsupported project spec version: {path}")
        chapters = tuple(
            ProjectChapter.from_texts(item["chapter_id"], item["texts"])
            for item in payload.get("chapters", [])
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

    def list(self) -> tuple[ProjectSpec, ...]:
        specs = []
        for path in sorted(self.root.glob("*/spec.json")):
            try:
                specs.append(self.load(path.parent.name))
            except (ProjectNotFoundError, RuntimeError, ValueError, KeyError, TypeError):
                continue
        return tuple(specs)

    @staticmethod
    def _safe_id(value: str) -> str:
        candidate = value.strip()
        if not candidate or candidate in {".", ".."}:
            raise ValueError("project_id must not be empty")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", candidate):
            raise ValueError("project_id may contain only letters, numbers, '.', '_' and '-'")
        return candidate
