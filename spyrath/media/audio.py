from __future__ import annotations

import hashlib
import json
import math
import os
import re
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline.production import ProductionJob, ProductionProgress


@dataclass(frozen=True)
class WavFormat:
    channels: int
    sample_width: int
    frame_rate: int


@dataclass(frozen=True)
class WavInfo:
    format: WavFormat
    frames: int

    @property
    def duration_seconds(self) -> float:
        return 0.0 if self.format.frame_rate == 0 else self.frames / self.format.frame_rate


@dataclass(frozen=True)
class ChapterAssemblyResult:
    output_path: Path
    source_count: int
    frames: int
    duration_seconds: float
    reused: bool


@dataclass(frozen=True)
class AudioSegmentationResult:
    source_path: Path
    output_dir: Path
    chunk_paths: tuple[Path, ...]
    target_duration_seconds: float
    progress: ProductionProgress

    @property
    def chunks_total(self) -> int:
        return len(self.chunk_paths)


@dataclass(frozen=True)
class AudioPreparationResult:
    assembly: ChapterAssemblyResult
    segmentation: AudioSegmentationResult


def inspect_pcm_wav(path: str | Path) -> WavInfo:
    """Read structural metadata from a PCM WAV file.

    Python's standard ``wave`` module intentionally keeps this layer dependency
    free. Provider-specific decoding/transcoding can be added later for formats
    other than uncompressed PCM WAV.
    """

    wav_path = Path(path)
    if not wav_path.is_file() or wav_path.stat().st_size <= 0:
        raise ValueError(f"WAV file does not exist or is empty: {wav_path}")

    try:
        with wave.open(str(wav_path), "rb") as reader:
            if reader.getcomptype() != "NONE":
                raise ValueError(f"Compressed WAV is not supported: {wav_path}")
            info = WavInfo(
                format=WavFormat(
                    channels=reader.getnchannels(),
                    sample_width=reader.getsampwidth(),
                    frame_rate=reader.getframerate(),
                ),
                frames=reader.getnframes(),
            )
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid PCM WAV: {wav_path}") from exc

    if info.format.channels <= 0:
        raise ValueError(f"Invalid channel count in WAV: {wav_path}")
    if info.format.sample_width <= 0:
        raise ValueError(f"Invalid sample width in WAV: {wav_path}")
    if info.format.frame_rate <= 0:
        raise ValueError(f"Invalid frame rate in WAV: {wav_path}")
    if info.frames <= 0:
        raise ValueError(f"WAV contains no audio frames: {wav_path}")
    return info


def validate_pcm_wav(path: str | Path) -> bool:
    try:
        inspect_pcm_wav(path)
    except (OSError, ValueError):
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


def _write_wav_header(writer: wave.Wave_write, wav_format: WavFormat) -> None:
    writer.setnchannels(wav_format.channels)
    writer.setsampwidth(wav_format.sample_width)
    writer.setframerate(wav_format.frame_rate)


class ChapterAssembler:
    """Concatenate compatible narration WAVs into one validated chapter WAV."""

    manifest_version = 1

    def __init__(self, *, copy_frames: int = 262_144) -> None:
        if copy_frames <= 0:
            raise ValueError("copy_frames must be > 0")
        self.copy_frames = copy_frames

    def assemble(
        self,
        sources: Iterable[str | Path],
        output_path: str | Path,
    ) -> ChapterAssemblyResult:
        source_paths = tuple(Path(path) for path in sources)
        if not source_paths:
            raise ValueError("At least one narration WAV is required")

        source_infos = tuple(inspect_pcm_wav(path) for path in source_paths)
        expected_format = source_infos[0].format
        for path, info in zip(source_paths[1:], source_infos[1:]):
            if info.format != expected_format:
                raise ValueError(
                    f"WAV format mismatch for {path}: {info.format} != {expected_format}"
                )

        final_path = Path(output_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path = final_path.with_name(final_path.name + ".manifest.json")
        source_records = [_source_record(path) for path in source_paths]
        expected_manifest = {
            "version": self.manifest_version,
            "kind": "chapter_assembly",
            "sources": source_records,
            "format": asdict(expected_format),
        }

        existing_manifest = _read_json(manifest_path)
        if validate_pcm_wav(final_path) and existing_manifest:
            comparable = {
                key: existing_manifest.get(key)
                for key in ("version", "kind", "sources", "format")
            }
            if comparable == expected_manifest and existing_manifest.get("output_sha256") == _sha256(final_path):
                info = inspect_pcm_wav(final_path)
                return ChapterAssemblyResult(
                    output_path=final_path,
                    source_count=len(source_paths),
                    frames=info.frames,
                    duration_seconds=info.duration_seconds,
                    reused=True,
                )

        temp_path = final_path.with_name(final_path.name + ".tmp")
        temp_path.unlink(missing_ok=True)
        try:
            with wave.open(str(temp_path), "wb") as writer:
                _write_wav_header(writer, expected_format)
                for source_path in source_paths:
                    with wave.open(str(source_path), "rb") as reader:
                        while True:
                            frames = reader.readframes(self.copy_frames)
                            if not frames:
                                break
                            writer.writeframesraw(frames)

            if not validate_pcm_wav(temp_path):
                raise RuntimeError(f"Assembled chapter failed WAV validation: {temp_path}")
            os.replace(temp_path, final_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        info = inspect_pcm_wav(final_path)
        manifest = {
            **expected_manifest,
            "frames": info.frames,
            "duration_seconds": info.duration_seconds,
            "output_sha256": _sha256(final_path),
        }
        _write_json_atomic(manifest_path, manifest)
        return ChapterAssemblyResult(
            output_path=final_path,
            source_count=len(source_paths),
            frames=info.frames,
            duration_seconds=info.duration_seconds,
            reused=False,
        )


class AudioSegmenter:
    """Split a chapter WAV into independently resumable fixed-duration chunks."""

    manifest_version = 1
    _chunk_pattern = re.compile(r"chunk_(\d+)\.wav(?:\.tmp)?$")

    def __init__(
        self,
        *,
        checkpoint: CheckpointManager,
        target_duration_seconds: float = 30.0,
    ) -> None:
        if target_duration_seconds <= 0:
            raise ValueError("target_duration_seconds must be > 0")
        self.checkpoint = checkpoint
        self.target_duration_seconds = float(target_duration_seconds)

    def segment(
        self,
        *,
        chapter: str,
        source_path: str | Path,
        output_dir: str | Path,
    ) -> AudioSegmentationResult:
        if not chapter.strip():
            raise ValueError("chapter must not be empty")

        source = Path(source_path)
        source_info = inspect_pcm_wav(source)
        source_record = _source_record(source)
        frames_per_chunk = max(
            1,
            int(round(source_info.format.frame_rate * self.target_duration_seconds)),
        )
        chunks_total = math.ceil(source_info.frames / frames_per_chunk)
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        manifest_path = destination / "manifest.json"

        expected_manifest_core = {
            "version": self.manifest_version,
            "kind": "audio_segmentation",
            "chapter": chapter,
            "source": source_record,
            "format": asdict(source_info.format),
            "source_frames": source_info.frames,
            "target_duration_seconds": self.target_duration_seconds,
            "frames_per_chunk": frames_per_chunk,
            "chunks_total": chunks_total,
        }

        existing_manifest = _read_json(manifest_path)
        manifest_matches = bool(
            existing_manifest
            and all(existing_manifest.get(key) == value for key, value in expected_manifest_core.items())
        )
        if existing_manifest is not None and not manifest_matches:
            for path in destination.glob("chunk_*.wav"):
                path.unlink(missing_ok=True)
            for path in destination.glob("chunk_*.wav.tmp"):
                path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)

        checkpoint_key = (
            f"audio_chunks:{chapter}:"
            f"{source_record['sha256'][:12]}:"
            f"{int(round(self.target_duration_seconds * 1000))}ms"
        )

        def validator(path: Path) -> bool:
            match = self._chunk_pattern.search(path.name)
            if not match:
                return False
            chunk_number = int(match.group(1))
            if not 0 <= chunk_number < chunks_total:
                return False
            try:
                info = inspect_pcm_wav(path)
            except (OSError, ValueError):
                return False
            expected_frames = min(
                frames_per_chunk,
                source_info.frames - (chunk_number * frames_per_chunk),
            )
            return info.format == source_info.format and info.frames == expected_frames

        job = ProductionJob(
            chapter=checkpoint_key,
            segments_total=chunks_total,
            output_dir=destination,
            checkpoint=self.checkpoint,
            extension=".wav",
            validator=validator,
        )

        def produce(chunk_number: int, temp_path: Path) -> None:
            start_frame = chunk_number * frames_per_chunk
            frame_count = min(frames_per_chunk, source_info.frames - start_frame)
            with wave.open(str(source), "rb") as reader:
                reader.setpos(start_frame)
                frames = reader.readframes(frame_count)
            with wave.open(str(temp_path), "wb") as writer:
                _write_wav_header(writer, source_info.format)
                writer.writeframes(frames)

        progress = job.run(produce)
        chunk_paths = tuple(job.artifact_path(index) for index in range(chunks_total))
        if not all(validator(path) for path in chunk_paths):
            raise RuntimeError("Audio segmentation completed with invalid chunk artifacts")

        manifest = {
            **expected_manifest_core,
            "chunks": [path.name for path in chunk_paths],
        }
        _write_json_atomic(manifest_path, manifest)
        return AudioSegmentationResult(
            source_path=source,
            output_dir=destination,
            chunk_paths=chunk_paths,
            target_duration_seconds=self.target_duration_seconds,
            progress=progress,
        )


class AudioPreparationEngine:
    """Assemble narration segments and prepare presenter-ready audio chunks."""

    def __init__(
        self,
        *,
        checkpoint: CheckpointManager,
        target_duration_seconds: float = 30.0,
    ) -> None:
        self.assembler = ChapterAssembler()
        self.segmenter = AudioSegmenter(
            checkpoint=checkpoint,
            target_duration_seconds=target_duration_seconds,
        )

    def prepare(
        self,
        *,
        chapter: str,
        narration_segments: Iterable[str | Path],
        chapter_output_path: str | Path,
        chunks_output_dir: str | Path,
    ) -> AudioPreparationResult:
        assembly = self.assembler.assemble(narration_segments, chapter_output_path)
        segmentation = self.segmenter.segment(
            chapter=chapter,
            source_path=assembly.output_path,
            output_dir=chunks_output_dir,
        )
        return AudioPreparationResult(assembly=assembly, segmentation=segmentation)
