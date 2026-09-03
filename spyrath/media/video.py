from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from spyrath.providers.video.base import file_sha256, stable_fingerprint

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class VideoProbe:
    duration: float
    has_video: bool
    has_audio: bool
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    pixel_format: str | None = None


@dataclass(frozen=True)
class ExportConfig:
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "fast"
    crf: int = 18
    audio_bitrate: str = "192k"
    pixel_format: str = "yuv420p"
    faststart: bool = True

    def cache_key(self) -> str:
        return stable_fingerprint(self.__dict__)


class FFmpegMedia:
    """FFmpeg/ffprobe adapter used by the final assembly pipeline."""

    def __init__(self, config: ExportConfig | None = None, *, runner: Runner = subprocess.run):
        self.config = config or ExportConfig()
        self.runner = runner

    def probe(self, path: str | Path) -> VideoProbe:
        media = Path(path)
        if not media.is_file() or media.stat().st_size <= 0:
            raise ValueError(f"Media artifact does not exist or is empty: {media}")
        command = [
            self.config.ffprobe, "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,pix_fmt",
            "-of", "json", str(media),
        ]
        result = self.runner(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed for {media}: {result.stderr.strip()}")
        try:
            payload = json.loads(result.stdout)
            duration = float(payload.get("format", {}).get("duration", 0.0))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid ffprobe response for {media}") from exc
        video = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), None)
        audio = next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), None)
        return VideoProbe(
            duration=duration,
            has_video=video is not None,
            has_audio=audio is not None,
            video_codec=video.get("codec_name") if video else None,
            audio_codec=audio.get("codec_name") if audio else None,
            width=video.get("width") if video else None,
            height=video.get("height") if video else None,
            pixel_format=video.get("pix_fmt") if video else None,
        )

    def validate_av(self, path: str | Path) -> bool:
        try:
            probe = self.probe(path)
        except (ValueError, RuntimeError, OSError):
            return False
        return probe.duration > 0 and probe.has_video and probe.has_audio

    def concat_copy(self, inputs: Sequence[Path], output_path: Path) -> None:
        if not inputs:
            raise ValueError("At least one video input is required")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            concat_file = Path(handle.name)
            for item in inputs:
                escaped = str(item.resolve()).replace("'", "'\\''")
                handle.write(f"file '{escaped}'\n")
        try:
            command = [self.config.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output_path)]
            self._run(command, "FFmpeg concat")
        finally:
            concat_file.unlink(missing_ok=True)

    def export_h264(self, inputs: Sequence[Path], output_path: Path) -> None:
        if not inputs:
            raise ValueError("At least one video input is required")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            concat_file = Path(handle.name)
            for item in inputs:
                escaped = str(item.resolve()).replace("'", "'\\''")
                handle.write(f"file '{escaped}'\n")
        try:
            command = [
                self.config.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c:v", self.config.video_codec, "-preset", self.config.preset, "-crf", str(self.config.crf),
                "-pix_fmt", self.config.pixel_format, "-c:a", self.config.audio_codec, "-b:a", self.config.audio_bitrate,
            ]
            if self.config.faststart:
                command += ["-movflags", "+faststart"]
            command.append(str(output_path))
            self._run(command, "H.264 export")
        finally:
            concat_file.unlink(missing_ok=True)

    def _run(self, command: list[str], label: str) -> None:
        result = self.runner(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"{label} failed: {result.stderr.strip()}")


def source_fingerprint(paths: Iterable[Path]) -> str:
    records = []
    for path in paths:
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"Source video does not exist or is empty: {path}")
        records.append({"path": str(path.resolve()), "size": path.stat().st_size, "sha256": file_sha256(path)})
    return stable_fingerprint({"sources": records})


def atomic_media_write(final_path: Path, producer: Callable[[Path], None], validator: Callable[[Path], bool]) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_name(final_path.name + ".tmp")
    temp_path.unlink(missing_ok=True)
    producer(temp_path)
    if not validator(temp_path):
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Generated media failed validation: {temp_path}")
    os.replace(temp_path, final_path)
