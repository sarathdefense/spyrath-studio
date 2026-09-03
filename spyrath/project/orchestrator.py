from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from spyrath.media.audio import AudioPreparationEngine
from spyrath.pipeline.export import FinalExportResult, VideoAssemblyEngine
from spyrath.pipeline.narration import NarrationEngine, NarrationPlan
from spyrath.pipeline.presenter import PresenterProductionEngine
from spyrath.providers.video.base import file_sha256

from .model import ProjectSpec, ProjectStage, ProjectState, ProjectStateStore, StageStatus


@dataclass(frozen=True)
class ProjectRunResult:
    state: ProjectState
    final_path: Path | None

    @property
    def completed(self) -> bool:
        return self.state.completed


class ProjectOrchestrator:
    """Run or resume one complete Spyrath project as an idempotent pipeline.

    Project state is for orchestration and observability. Media artifacts remain
    the source of truth inside the reliability-first engines from milestones 1-6.
    """

    stage_order = tuple(ProjectStage)

    def __init__(
        self,
        *,
        spec: ProjectSpec,
        project_root: str | Path,
        narration: NarrationEngine,
        audio: AudioPreparationEngine,
        presenter: PresenterProductionEngine,
        exporter: VideoAssemblyEngine,
    ) -> None:
        self.spec = spec
        self.root = Path(project_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.narration = narration
        self.audio = audio
        self.presenter = presenter
        self.exporter = exporter
        self.state_store = ProjectStateStore(self.root / "project.json")

    def run(self) -> ProjectRunResult:
        state = self.state_store.load(self.spec)
        final_path: Path | None = None
        try:
            narration_by_chapter = self._run_narration(state)
            audio_by_chapter = self._run_audio(state, narration_by_chapter)
            presenter_by_chapter = self._run_presenter(state, audio_by_chapter)
            final_path = self._run_export(state, presenter_by_chapter)
        except Exception as exc:
            state.last_error = str(exc)
            self.state_store.save(state)
            raise
        state.last_error = None
        self.state_store.save(state)
        return ProjectRunResult(state=state, final_path=final_path)

    def resume(self) -> ProjectRunResult:
        return self.run()

    def status(self) -> ProjectState:
        return self.state_store.load(self.spec)

    def _run_narration(self, state: ProjectState) -> dict[str, tuple[Path, ...]]:
        stage = ProjectStage.NARRATION
        fingerprint = self._fingerprint({
            "chapters": [(c.chapter_id, list(c.texts)) for c in self.spec.chapters],
            "language": self.spec.language,
            "voice_reference": self._file_identity(self.spec.voice_reference),
            "provider": getattr(self.narration.provider, "name", self.narration.provider.__class__.__name__),
        })
        artifact_paths = [
            self.narration.output_dir(chapter.chapter_id) / f"chunk_{index:03d}.wav"
            for chapter in self.spec.chapters
            for index in range(len(chapter.texts))
        ]
        if self._can_reuse(state, stage, fingerprint, artifact_paths):
            return self._group_narration_artifacts()

        self._begin_stage(state, stage, fingerprint)
        try:
            for chapter in self.spec.chapters:
                plan = NarrationPlan.from_texts(chapter.chapter_id, chapter.texts)
                progress = self.narration.run(
                    plan,
                    voice_reference=self.spec.voice_reference,
                    language=self.spec.language,
                )
                if progress.completed != len(chapter.texts):
                    raise RuntimeError(
                        f"Narration incomplete for {chapter.chapter_id}: "
                        f"{progress.completed}/{len(chapter.texts)}"
                    )
            self._complete_stage(state, stage, fingerprint, artifact_paths)
            return self._group_narration_artifacts()
        except Exception as exc:
            self._fail_stage(state, stage, exc)
            raise

    def _run_audio(
        self,
        state: ProjectState,
        narration_by_chapter: dict[str, tuple[Path, ...]],
    ) -> dict[str, tuple[Path, ...]]:
        stage = ProjectStage.AUDIO
        fingerprint = self._files_fingerprint(
            path for paths in narration_by_chapter.values() for path in paths
        )
        expected = self._audio_artifacts_from_manifests()
        if expected and self._can_reuse(state, stage, fingerprint, expected):
            return self._group_audio_chunk_artifacts()

        self._begin_stage(state, stage, fingerprint)
        try:
            for chapter in self.spec.chapters:
                chapter_id = chapter.chapter_id
                self.audio.prepare(
                    chapter=chapter_id,
                    narration_segments=narration_by_chapter[chapter_id],
                    chapter_output_path=self.root / "audio" / "chapters" / f"{chapter_id}.wav",
                    chunks_output_dir=self.root / "audio" / "chunks" / chapter_id,
                )
            artifacts = self._audio_artifacts_from_manifests()
            self._complete_stage(state, stage, fingerprint, artifacts)
            return self._group_audio_chunk_artifacts()
        except Exception as exc:
            self._fail_stage(state, stage, exc)
            raise

    def _run_presenter(
        self,
        state: ProjectState,
        audio_by_chapter: dict[str, tuple[Path, ...]],
    ) -> dict[str, tuple[Path, ...]]:
        stage = ProjectStage.PRESENTER
        fingerprint = self._fingerprint({
            "audio": self._files_fingerprint(
                path for paths in audio_by_chapter.values() for path in paths
            ),
            "presenter": self._file_identity(self.spec.presenter_image),
            "provider": self.presenter.provider.cache_key(),
        })
        expected = self._presenter_artifacts_from_manifests()
        if expected and self._can_reuse(state, stage, fingerprint, expected):
            return self._group_presenter_artifacts()

        self._begin_stage(state, stage, fingerprint)
        try:
            for chapter in self.spec.chapters:
                chapter_id = chapter.chapter_id
                self.presenter.render(
                    chapter=chapter_id,
                    audio_chunks=audio_by_chapter[chapter_id],
                    presenter_image=self.spec.presenter_image,
                    output_dir=self.root / "video" / "chunks" / chapter_id,
                )
            artifacts = self._presenter_artifacts_from_manifests()
            self._complete_stage(state, stage, fingerprint, artifacts)
            return self._group_presenter_artifacts()
        except Exception as exc:
            self._fail_stage(state, stage, exc)
            raise

    def _run_export(
        self,
        state: ProjectState,
        presenter_by_chapter: dict[str, tuple[Path, ...]],
    ) -> Path:
        stage = ProjectStage.EXPORT
        fingerprint = self._fingerprint({
            "presenter_chunks": self._files_fingerprint(
                path for paths in presenter_by_chapter.values() for path in paths
            ),
            "export_config": self.exporter.media.config.cache_key(),
        })
        final_path = self.root / "final" / f"{self._slug(self.spec.project_id)}_presenter.mp4"
        if self._can_reuse(state, stage, fingerprint, [final_path]):
            return final_path

        self._begin_stage(state, stage, fingerprint)
        try:
            result: FinalExportResult = self.exporter.export_final(
                chapters=presenter_by_chapter,
                chapter_output_dir=self.root / "video" / "chapters",
                final_path=final_path,
            )
            self._complete_stage(state, stage, fingerprint, [result.path])
            return result.path
        except Exception as exc:
            self._fail_stage(state, stage, exc)
            raise

    def _begin_stage(self, state: ProjectState, stage: ProjectStage, fingerprint: str) -> None:
        self._invalidate_downstream(state, stage)
        item = state.stage(stage)
        item.status = StageStatus.RUNNING
        item.input_fingerprint = fingerprint
        item.error = None
        self.state_store.save(state)

    def _complete_stage(
        self,
        state: ProjectState,
        stage: ProjectStage,
        fingerprint: str,
        artifacts: Iterable[Path],
    ) -> None:
        paths = tuple(Path(path) for path in artifacts)
        if not paths or not all(self._artifact_exists(path) for path in paths):
            raise RuntimeError(f"{stage.value} completed without valid artifacts")
        item = state.stage(stage)
        item.status = StageStatus.COMPLETED
        item.input_fingerprint = fingerprint
        item.artifacts = [str(path) for path in paths]
        item.error = None
        state.last_error = None
        self.state_store.save(state)

    def _fail_stage(self, state: ProjectState, stage: ProjectStage, exc: Exception) -> None:
        item = state.stage(stage)
        item.status = StageStatus.FAILED
        item.error = str(exc)
        state.last_error = str(exc)
        self.state_store.save(state)

    def _can_reuse(
        self,
        state: ProjectState,
        stage: ProjectStage,
        fingerprint: str,
        artifacts: Iterable[Path],
    ) -> bool:
        item = state.stage(stage)
        paths = tuple(Path(path) for path in artifacts)
        return (
            item.status == StageStatus.COMPLETED
            and item.input_fingerprint == fingerprint
            and bool(paths)
            and all(self._artifact_exists(path) for path in paths)
        )

    def _invalidate_downstream(self, state: ProjectState, stage: ProjectStage) -> None:
        index = self.stage_order.index(stage)
        for downstream in self.stage_order[index + 1 :]:
            item = state.stage(downstream)
            item.status = StageStatus.PENDING
            item.input_fingerprint = None
            item.artifacts = []
            item.error = None

    def _group_narration_artifacts(self) -> dict[str, tuple[Path, ...]]:
        return {
            chapter.chapter_id: tuple(
                self.narration.output_dir(chapter.chapter_id) / f"chunk_{index:03d}.wav"
                for index in range(len(chapter.texts))
            )
            for chapter in self.spec.chapters
        }

    def _audio_artifacts_from_manifests(self) -> list[Path]:
        artifacts: list[Path] = []
        for chapter in self.spec.chapters:
            directory = self.root / "audio" / "chunks" / chapter.chapter_id
            artifacts.extend(self._manifest_artifacts(directory / "manifest.json", directory, "chunks"))
        return artifacts

    def _group_audio_chunk_artifacts(self) -> dict[str, tuple[Path, ...]]:
        result: dict[str, tuple[Path, ...]] = {}
        for chapter in self.spec.chapters:
            directory = self.root / "audio" / "chunks" / chapter.chapter_id
            result[chapter.chapter_id] = tuple(
                self._manifest_artifacts(directory / "manifest.json", directory, "chunks")
            )
        return result

    def _presenter_artifacts_from_manifests(self) -> list[Path]:
        artifacts: list[Path] = []
        for chapter in self.spec.chapters:
            directory = self.root / "video" / "chunks" / chapter.chapter_id
            artifacts.extend(self._manifest_artifacts(directory / "manifest.json", directory, "chunks"))
        return artifacts

    def _group_presenter_artifacts(self) -> dict[str, tuple[Path, ...]]:
        result: dict[str, tuple[Path, ...]] = {}
        for chapter in self.spec.chapters:
            directory = self.root / "video" / "chunks" / chapter.chapter_id
            result[chapter.chapter_id] = tuple(
                self._manifest_artifacts(directory / "manifest.json", directory, "chunks")
            )
        return result

    @staticmethod
    def _manifest_artifacts(manifest_path: Path, directory: Path, key: str) -> list[Path]:
        if not manifest_path.is_file():
            return []
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        values = payload.get(key, [])
        if not isinstance(values, list):
            return []
        return [directory / str(value) for value in values]

    @staticmethod
    def _artifact_exists(path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0

    @staticmethod
    def _file_identity(path: Path | None) -> dict[str, object] | None:
        if path is None:
            return None
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"Project input does not exist or is empty: {path}")
        return {
            "path": str(path.resolve()),
            "size": path.stat().st_size,
            "sha256": file_sha256(path),
        }

    @classmethod
    def _files_fingerprint(cls, paths: Iterable[Path]) -> str:
        records = [cls._file_identity(Path(path)) for path in paths]
        if not records:
            raise ValueError("Expected at least one project artifact")
        return cls._fingerprint({"files": records})

    @staticmethod
    def _fingerprint(payload: object) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_")
        return slug or "spyrath_project"
