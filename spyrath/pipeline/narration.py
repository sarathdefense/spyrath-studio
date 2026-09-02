from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline.production import ProductionJob, ProductionProgress
from spyrath.providers.tts import TTSProvider, TTSRequest

AudioValidator = Callable[[Path], bool]


@dataclass(frozen=True)
class NarrationSegment:
    """One independently resumable unit of narration."""

    segment_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")


@dataclass(frozen=True)
class NarrationPlan:
    chapter: str
    segments: tuple[NarrationSegment, ...]

    @classmethod
    def from_texts(cls, chapter: str, texts: Iterable[str]) -> "NarrationPlan":
        return cls(
            chapter=chapter,
            segments=tuple(
                NarrationSegment(segment_id=f"segment_{index:03d}", text=text)
                for index, text in enumerate(texts)
            ),
        )


class NarrationEngine:
    """Generate narration through a provider with validation and resume support."""

    def __init__(
        self,
        *,
        provider: TTSProvider,
        checkpoint: CheckpointManager,
        output_root: str | Path,
        validator: AudioValidator | None = None,
    ) -> None:
        self.provider = provider
        self.checkpoint = checkpoint
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.validator = validator or self._default_audio_validator

    def output_dir(self, chapter: str) -> Path:
        return self.output_root / chapter

    def run(
        self,
        plan: NarrationPlan,
        *,
        voice_reference: str | Path | None = None,
        language: str = "en",
    ) -> ProductionProgress:
        if not plan.chapter.strip():
            raise ValueError("chapter must not be empty")

        voice_path = Path(voice_reference) if voice_reference is not None else None
        job = ProductionJob(
            chapter=f"narration:{plan.chapter}",
            segments_total=len(plan.segments),
            output_dir=self.output_dir(plan.chapter),
            checkpoint=self.checkpoint,
            extension=".wav",
            validator=self.validator,
        )

        def produce(segment_number: int, temp_path: Path) -> None:
            segment = plan.segments[segment_number]
            result = self.provider.synthesize(
                TTSRequest(
                    text=segment.text,
                    output_path=temp_path,
                    voice_reference=voice_path,
                    language=language,
                    metadata={
                        "chapter": plan.chapter,
                        "segment_id": segment.segment_id,
                        "segment_number": str(segment_number),
                    },
                )
            )
            if Path(result.output_path) != temp_path:
                raise RuntimeError(
                    f"TTS provider returned unexpected output path: {result.output_path}"
                )

        return job.run(produce)

    def progress(self, plan: NarrationPlan) -> ProductionProgress:
        job = ProductionJob(
            chapter=f"narration:{plan.chapter}",
            segments_total=len(plan.segments),
            output_dir=self.output_dir(plan.chapter),
            checkpoint=self.checkpoint,
            extension=".wav",
            validator=self.validator,
        )
        return job.reconcile()

    @staticmethod
    def _default_audio_validator(path: Path) -> bool:
        # Provider-independent foundation check. A WAV/ffprobe validator can be
        # injected later without coupling the orchestration layer to ffmpeg.
        return path.is_file() and path.stat().st_size > 0
