from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from spyrath.media.video import FFmpegMedia, VideoProbe, atomic_media_write, source_fingerprint
from spyrath.providers.video.base import stable_fingerprint


@dataclass(frozen=True)
class ChapterVideo:
    chapter: str
    path: Path
    reused: bool


@dataclass(frozen=True)
class FinalExportResult:
    path: Path
    probe: VideoProbe
    chapter_videos: tuple[ChapterVideo, ...]
    reused: bool


class VideoAssemblyEngine:
    """Assemble presenter chunks into chapters and a delivery-ready H.264 MP4."""

    manifest_version = 1

    def __init__(self, media: FFmpegMedia):
        self.media = media

    def assemble_chapter(self, *, chapter: str, chunks: Sequence[str | Path], output_path: str | Path) -> ChapterVideo:
        paths = tuple(Path(p) for p in chunks)
        if not chapter.strip() or not paths:
            raise ValueError("chapter and at least one chunk are required")
        for path in paths:
            if not self.media.validate_av(path):
                raise ValueError(f"Invalid presenter chunk: {path}")
        final = Path(output_path)
        fingerprint = stable_fingerprint({"version": self.manifest_version, "chapter": chapter, "sources": source_fingerprint(paths)})
        manifest = final.with_suffix(final.suffix + ".manifest.json")
        if self._matches(manifest, fingerprint) and self.media.validate_av(final):
            return ChapterVideo(chapter, final, True)
        atomic_media_write(final, lambda temp: self.media.concat_copy(paths, temp), self.media.validate_av)
        self._write_manifest(manifest, {"version": self.manifest_version, "kind": "chapter_video", "chapter": chapter, "fingerprint": fingerprint, "sources": [str(p) for p in paths]})
        return ChapterVideo(chapter, final, False)

    def export_final(self, *, chapters: Mapping[str, Sequence[str | Path]], chapter_output_dir: str | Path, final_path: str | Path) -> FinalExportResult:
        if not chapters:
            raise ValueError("At least one chapter is required")
        chapter_dir = Path(chapter_output_dir)
        assembled = []
        for index, (chapter, chunks) in enumerate(chapters.items(), start=1):
            output = chapter_dir / f"{index:02d}_{chapter}.mp4"
            assembled.append(self.assemble_chapter(chapter=chapter, chunks=chunks, output_path=output))

        chapter_paths = tuple(item.path for item in assembled)
        final = Path(final_path)
        fingerprint = stable_fingerprint({
            "version": self.manifest_version,
            "kind": "final_h264_export",
            "sources": source_fingerprint(chapter_paths),
            "export_config": self.media.config.cache_key(),
        })
        manifest = final.with_suffix(final.suffix + ".manifest.json")
        reused = self._matches(manifest, fingerprint) and self._valid_delivery(final)
        if not reused:
            atomic_media_write(final, lambda temp: self.media.export_h264(chapter_paths, temp), self._valid_delivery)
            self._write_manifest(manifest, {"version": self.manifest_version, "kind": "final_h264_export", "fingerprint": fingerprint, "chapters": [str(p) for p in chapter_paths], "export_config": self.media.config.__dict__})
        return FinalExportResult(final, self.media.probe(final), tuple(assembled), reused)

    def _valid_delivery(self, path: Path) -> bool:
        try:
            probe = self.media.probe(path)
        except (ValueError, RuntimeError, OSError):
            return False
        return probe.duration > 0 and probe.has_video and probe.has_audio and probe.video_codec == "h264" and probe.audio_codec == "aac" and probe.pixel_format == "yuv420p"

    @staticmethod
    def _matches(path: Path, fingerprint: str) -> bool:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return payload.get("fingerprint") == fingerprint

    @staticmethod
    def _write_manifest(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)
