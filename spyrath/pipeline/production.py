from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from spyrath.checkpoint import CheckpointManager

Validator = Callable[[Path], bool]
Producer = Callable[[int, Path], None]


@dataclass(frozen=True)
class ProductionProgress:
    total: int
    completed: int

    @property
    def remaining(self) -> int:
        return self.total - self.completed

    @property
    def percent(self) -> float:
        return 100.0 if self.total == 0 else (self.completed / self.total) * 100


class ProductionJob:
    """Reliably produce numbered artifacts and resume from validated outputs."""

    def __init__(
        self,
        *,
        chapter: str,
        segments_total: int,
        output_dir: str | Path,
        checkpoint: CheckpointManager,
        extension: str = ".mp4",
        validator: Validator | None = None,
    ):
        self.chapter = chapter
        self.segments_total = segments_total
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint = checkpoint
        self.extension = extension if extension.startswith(".") else f".{extension}"
        self.validator = validator or self._default_validator
        self.checkpoint.initialize_chapter(chapter, segments_total)

    def artifact_path(self, segment_number: int) -> Path:
        return self.output_dir / f"chunk_{segment_number:03d}{self.extension}"

    def reconcile(self) -> ProductionProgress:
        """Make checkpoint state match artifacts that actually validate on disk."""
        for segment_number in range(self.segments_total):
            path = self.artifact_path(segment_number)
            if self.validator(path):
                self.checkpoint.mark_segment_complete(self.chapter, segment_number)
            elif self.checkpoint.is_segment_complete(self.chapter, segment_number):
                self.checkpoint.mark_segment_incomplete(self.chapter, segment_number)
        return self.progress()

    def missing_segments(self) -> list[int]:
        self.reconcile()
        return self.checkpoint.missing_segments(self.chapter)

    def run(self, producer: Producer, segments: Iterable[int] | None = None) -> ProductionProgress:
        self.reconcile()
        candidates = list(segments) if segments is not None else range(self.segments_total)

        for segment_number in candidates:
            final_path = self.artifact_path(segment_number)
            if self.validator(final_path):
                self.checkpoint.mark_segment_complete(self.chapter, segment_number)
                continue

            temp_path = final_path.with_name(final_path.name + ".tmp")
            temp_path.unlink(missing_ok=True)
            producer(segment_number, temp_path)

            if not self.validator(temp_path):
                temp_path.unlink(missing_ok=True)
                raise RuntimeError(f"Generated artifact failed validation: {temp_path}")

            os.replace(temp_path, final_path)
            self.checkpoint.mark_segment_complete(self.chapter, segment_number)

        return self.progress()

    def progress(self) -> ProductionProgress:
        state = self.checkpoint.get_chapter_state(self.chapter)
        completed = state.segments_completed if state else 0
        return ProductionProgress(total=self.segments_total, completed=completed)

    @staticmethod
    def _default_validator(path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0
