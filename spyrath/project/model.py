from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable


class ProjectStage(str, Enum):
    NARRATION = "narration"
    AUDIO = "audio_preparation"
    PRESENTER = "presenter_video"
    EXPORT = "final_export"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ProjectChapter:
    chapter_id: str
    texts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.chapter_id.strip():
            raise ValueError("chapter_id must not be empty")
        if not self.texts or any(not text.strip() for text in self.texts):
            raise ValueError("Each chapter must contain at least one non-empty narration segment")

    @classmethod
    def from_texts(cls, chapter_id: str, texts: Iterable[str]) -> "ProjectChapter":
        return cls(chapter_id=chapter_id, texts=tuple(texts))


@dataclass(frozen=True)
class ProjectSpec:
    project_id: str
    title: str
    chapters: tuple[ProjectChapter, ...]
    presenter_image: Path
    voice_reference: Path | None = None
    language: str = "en"

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.chapters:
            raise ValueError("Project must contain at least one chapter")
        chapter_ids = [chapter.chapter_id for chapter in self.chapters]
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError("chapter_id values must be unique")


@dataclass
class StageState:
    status: StageStatus = StageStatus.PENDING
    input_fingerprint: str | None = None
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ProjectState:
    project_id: str
    title: str
    stages: dict[str, StageState]
    last_error: str | None = None

    @classmethod
    def new(cls, spec: ProjectSpec) -> "ProjectState":
        return cls(
            project_id=spec.project_id,
            title=spec.title,
            stages={stage.value: StageState() for stage in ProjectStage},
        )

    def stage(self, stage: ProjectStage) -> StageState:
        return self.stages[stage.value]

    @property
    def completed(self) -> bool:
        return all(self.stage(stage).status == StageStatus.COMPLETED for stage in ProjectStage)


class ProjectStateStore:
    """Atomic JSON persistence for user-visible project orchestration state."""

    version = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, spec: ProjectSpec) -> ProjectState:
        if not self.path.is_file():
            return ProjectState.new(spec)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ProjectState.new(spec)
        if payload.get("version") != self.version or payload.get("project_id") != spec.project_id:
            return ProjectState.new(spec)

        stages: dict[str, StageState] = {}
        raw_stages = payload.get("stages", {})
        for stage in ProjectStage:
            raw = raw_stages.get(stage.value, {})
            try:
                status = StageStatus(raw.get("status", StageStatus.PENDING.value))
            except ValueError:
                status = StageStatus.PENDING
            stages[stage.value] = StageState(
                status=status,
                input_fingerprint=raw.get("input_fingerprint"),
                artifacts=list(raw.get("artifacts", [])),
                error=raw.get("error"),
            )
        return ProjectState(
            project_id=spec.project_id,
            title=payload.get("title", spec.title),
            stages=stages,
            last_error=payload.get("last_error"),
        )

    def save(self, state: ProjectState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "project_id": state.project_id,
            "title": state.title,
            "last_error": state.last_error,
            "stages": {
                name: {
                    **asdict(stage),
                    "status": stage.status.value,
                }
                for name, stage in state.stages.items()
            },
        }
        temp = self.path.with_name(self.path.name + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self.path)
