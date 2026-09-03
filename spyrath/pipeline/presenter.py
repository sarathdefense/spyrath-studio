from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline.production import ProductionJob, ProductionProgress
from spyrath.providers.video import (
    VideoProvider,
    VideoRequest,
    file_sha256,
    stable_fingerprint,
    validate_mp4,
)


@dataclass(frozen=True)
class PresenterProductionResult:
    chapter: str
    output_dir: Path
    chunk_paths: tuple[Path, ...]
    progress: ProductionProgress
    generated: int
    reused: int

    @property
    def chunks_total(self) -> int:
        return len(self.chunk_paths)


def _file_record(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"Input artifact does not exist or is empty: {path}")
    return {
        "path": str(path.resolve()),
        "size": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _read_manifest(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_manifest_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


class PresenterProductionEngine:
    """Generate presenter MP4 chunks with validation, checkpointing and resume."""

    manifest_version = 1

    def __init__(
        self,
        *,
        provider: VideoProvider,
        checkpoint: CheckpointManager,
    ) -> None:
        self.provider = provider
        self.checkpoint = checkpoint

    def render(
        self,
        *,
        chapter: str,
        audio_chunks: Iterable[str | Path],
        presenter_image: str | Path,
        output_dir: str | Path,
        segments: Iterable[int] | None = None,
    ) -> PresenterProductionResult:
        if not chapter.strip():
            raise ValueError("chapter must not be empty")

        audio_paths = tuple(Path(path) for path in audio_chunks)
        if not audio_paths:
            raise ValueError("At least one audio chunk is required")
        presenter_path = Path(presenter_image)
        presenter_record = _file_record(presenter_path)
        audio_records = [_file_record(path) for path in audio_paths]

        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        manifest_path = destination / "manifest.json"
        provider_key = self.provider.cache_key()
        expected_core = {
            "version": self.manifest_version,
            "kind": "presenter_video_chunks",
            "chapter": chapter,
            "presenter_image": presenter_record,
            "audio_chunks": audio_records,
            "provider": self.provider.name,
            "provider_cache_key": provider_key,
            "chunks_total": len(audio_paths),
        }

        existing = _read_manifest(manifest_path)
        manifest_matches = bool(
            existing
            and all(existing.get(key) == value for key, value in expected_core.items())
        )
        if existing is not None and not manifest_matches:
            self._invalidate_outputs(destination)

        fingerprint = stable_fingerprint(expected_core)
        checkpoint_key = f"presenter:{chapter}:{fingerprint[:20]}"
        job = ProductionJob(
            chapter=checkpoint_key,
            segments_total=len(audio_paths),
            output_dir=destination,
            checkpoint=self.checkpoint,
            extension=".mp4",
            validator=validate_mp4,
        )

        missing_before = set(job.missing_segments())

        def produce(segment_number: int, temp_path: Path) -> None:
            request = VideoRequest(
                audio_path=audio_paths[segment_number],
                presenter_image_path=presenter_path,
                output_path=temp_path,
                chapter=chapter,
                segment_number=segment_number,
                metadata={"provider_cache_key": provider_key},
            )
            result = self.provider.generate(request)
            if Path(result.output_path) != temp_path:
                raise RuntimeError(
                    "Video provider must return the exact output path requested by Spyrath"
                )

        progress = job.run(produce, segments=segments)
        chunk_paths = tuple(job.artifact_path(index) for index in range(len(audio_paths)))

        selected = set(range(len(audio_paths))) if segments is None else set(segments)
        generated = len(missing_before & selected)
        reused = len(selected) - generated

        # Persist the source/provider manifest even for partial production. It is
        # what makes a later restart safe to reconcile against the same inputs.
        _write_manifest_atomic(
            manifest_path,
            {
                **expected_core,
                "chunks": [path.name for path in chunk_paths],
                "completed": progress.completed,
            },
        )

        return PresenterProductionResult(
            chapter=chapter,
            output_dir=destination,
            chunk_paths=chunk_paths,
            progress=progress,
            generated=generated,
            reused=reused,
        )

    @staticmethod
    def _invalidate_outputs(destination: Path) -> None:
        for path in destination.glob("chunk_*.mp4"):
            path.unlink(missing_ok=True)
        for path in destination.glob("chunk_*.mp4.tmp"):
            path.unlink(missing_ok=True)
        (destination / "manifest.json").unlink(missing_ok=True)
        (destination / "manifest.json.tmp").unlink(missing_ok=True)
