from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from spyrath.checkpoint import CheckpointManager
from spyrath.media import ExportConfig, FFmpegMedia
from spyrath.media.audio import AudioPreparationEngine
from spyrath.pipeline import NarrationEngine, PresenterProductionEngine, VideoAssemblyEngine
from spyrath.project import ProjectOrchestrator, ProjectSpec
from spyrath.providers.tts import ChatterboxConfig, ChatterboxTTSProvider
from spyrath.providers.video import SadTalkerConfig, SadTalkerProvider
from spyrath.runtime import RuntimePreflight

from .repository import ProjectRepository
from .service import StudioService


@dataclass(frozen=True)
class StudioRuntimeConfig:
    projects_root: Path = Path.home() / ".spyrath" / "projects"
    sadtalker_repository: Path | None = None
    sadtalker_python: str = sys.executable
    sadtalker_checkpoints: Path | None = None
    tts_device: str = "auto"
    audio_chunk_seconds: float = 30.0
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    max_workers: int = 1
    max_attempts: int = 2
    require_gpu: bool = True
    metadata_db: Path | None = None
    auth_enabled: bool = False

    @classmethod
    def from_env(cls) -> "StudioRuntimeConfig":
        repo = os.getenv("SPYRATH_SADTALKER_REPO")
        checkpoints = os.getenv("SPYRATH_SADTALKER_CHECKPOINTS")
        return cls(
            projects_root=Path(os.getenv("SPYRATH_PROJECTS_ROOT", str(Path.home() / ".spyrath" / "projects"))).expanduser(),
            sadtalker_repository=Path(repo).expanduser() if repo else None,
            sadtalker_python=os.getenv("SPYRATH_SADTALKER_PYTHON", sys.executable),
            sadtalker_checkpoints=Path(checkpoints).expanduser() if checkpoints else None,
            tts_device=os.getenv("SPYRATH_TTS_DEVICE", "auto"),
            audio_chunk_seconds=float(os.getenv("SPYRATH_AUDIO_CHUNK_SECONDS", "30")),
            ffmpeg=os.getenv("SPYRATH_FFMPEG", "ffmpeg"),
            ffprobe=os.getenv("SPYRATH_FFPROBE", "ffprobe"),
            max_workers=int(os.getenv("SPYRATH_MAX_WORKERS", "1")),
            max_attempts=int(os.getenv("SPYRATH_MAX_ATTEMPTS", "2")),
            require_gpu=os.getenv("SPYRATH_REQUIRE_GPU", "1").lower() not in {"0", "false", "no"},
            metadata_db=Path(os.getenv("SPYRATH_METADATA_DB", str(Path.home() / ".spyrath" / "studio.db"))).expanduser(),
            auth_enabled=os.getenv("SPYRATH_AUTH_ENABLED", "0").lower() in {"1", "true", "yes"},
        )

    def validate_for_production(self) -> None:
        if self.sadtalker_repository is None:
            raise RuntimeError("SPYRATH_SADTALKER_REPO is required to run presenter production")
        inference = self.sadtalker_repository / "inference.py"
        if not inference.is_file():
            raise RuntimeError(f"SadTalker inference.py not found: {inference}")
        if self.audio_chunk_seconds <= 0:
            raise ValueError("audio_chunk_seconds must be > 0")


class RealOrchestratorFactory:
    """Wire the milestone 1-7 engines to real Chatterbox/SadTalker/FFmpeg adapters."""

    def __init__(self, config: StudioRuntimeConfig):
        self.config = config

    def __call__(self, spec: ProjectSpec, project_root: Path) -> ProjectOrchestrator:
        self.config.validate_for_production()
        checkpoint = CheckpointManager(project_root / "checkpoints.json")

        tts = ChatterboxTTSProvider(ChatterboxConfig(device=self.config.tts_device))
        narration = NarrationEngine(
            provider=tts,
            checkpoint=checkpoint,
            output_root=project_root / "narration",
        )
        audio = AudioPreparationEngine(
            checkpoint=checkpoint,
            target_duration_seconds=self.config.audio_chunk_seconds,
        )
        video = SadTalkerProvider(
            SadTalkerConfig(
                repository_dir=self.config.sadtalker_repository,  # validated above
                python_executable=self.config.sadtalker_python,
                checkpoint_dir=self.config.sadtalker_checkpoints,
            )
        )
        presenter = PresenterProductionEngine(provider=video, checkpoint=checkpoint)
        media = FFmpegMedia(
            ExportConfig(ffmpeg=self.config.ffmpeg, ffprobe=self.config.ffprobe)
        )
        exporter = VideoAssemblyEngine(media)
        return ProjectOrchestrator(
            spec=spec,
            project_root=project_root,
            narration=narration,
            audio=audio,
            presenter=presenter,
            exporter=exporter,
        )


def create_real_service(config: StudioRuntimeConfig | None = None) -> StudioService:
    runtime = config or StudioRuntimeConfig.from_env()
    repository = ProjectRepository(runtime.projects_root)
    preflight = RuntimePreflight(
        sadtalker_repository=runtime.sadtalker_repository,
        sadtalker_python=runtime.sadtalker_python,
        ffmpeg=runtime.ffmpeg,
        ffprobe=runtime.ffprobe,
        require_gpu=runtime.require_gpu,
    )
    return StudioService(
        repository=repository,
        orchestrator_factory=RealOrchestratorFactory(runtime),
        max_workers=runtime.max_workers,
        max_attempts=runtime.max_attempts,
        runtime_preflight=preflight.require_ready,
    )
