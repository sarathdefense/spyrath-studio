from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict


@dataclass
class ChapterState:
    chapter: str
    segments_total: int
    completed_segments: list[int] = field(default_factory=list)
    chapter_complete: bool = False

    @property
    def segments_completed(self) -> int:
        """Number of individually completed segments (compatibility helper)."""
        return len(self.completed_segments)


class CheckpointManager:
    """Persist exact per-segment completion state using atomic checkpoint writes."""

    def __init__(self, checkpoint_file: str | Path):
        self.checkpoint_file = Path(checkpoint_file)
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        self._state: Dict[str, ChapterState] = {}
        self._load()

    def _load(self) -> None:
        if not self.checkpoint_file.exists():
            return

        data = json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        for chapter, value in data.items():
            # Migrate the original sequential checkpoint format.
            if "completed_segments" not in value:
                count = int(value.pop("segments_completed", 0))
                value["completed_segments"] = list(range(count))
            state = ChapterState(**value)
            state.completed_segments = sorted(set(state.completed_segments))
            state.chapter_complete = len(state.completed_segments) >= state.segments_total
            self._state[chapter] = state

    def _save(self) -> None:
        data = {chapter: asdict(state) for chapter, state in self._state.items()}
        temp_file = self.checkpoint_file.with_name(self.checkpoint_file.name + ".tmp")
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_file.replace(self.checkpoint_file)

    def initialize_chapter(self, chapter: str, segments_total: int) -> ChapterState:
        if segments_total < 0:
            raise ValueError("segments_total must be >= 0")

        state = self._state.get(chapter)
        if state is None:
            state = ChapterState(chapter=chapter, segments_total=segments_total)
            self._state[chapter] = state
            self._save()
        elif state.segments_total != segments_total:
            raise ValueError(
                f"Chapter {chapter!r} already has {state.segments_total} segments; "
                f"cannot reinitialize with {segments_total}."
            )
        return state

    def mark_segment_complete(self, chapter: str, segment_number: int) -> None:
        state = self._state[chapter]
        self._validate_segment_number(state, segment_number)
        if segment_number not in state.completed_segments:
            state.completed_segments.append(segment_number)
            state.completed_segments.sort()
        state.chapter_complete = len(state.completed_segments) >= state.segments_total
        self._save()

    def mark_segment_incomplete(self, chapter: str, segment_number: int) -> None:
        """Remove stale completion state when an output artifact fails validation."""
        state = self._state[chapter]
        self._validate_segment_number(state, segment_number)
        if segment_number in state.completed_segments:
            state.completed_segments.remove(segment_number)
            state.chapter_complete = False
            self._save()

    def is_segment_complete(self, chapter: str, segment_number: int) -> bool:
        state = self._state.get(chapter)
        return bool(state and segment_number in state.completed_segments)

    def is_chapter_complete(self, chapter: str) -> bool:
        state = self._state.get(chapter)
        return bool(state and state.chapter_complete)

    def missing_segments(self, chapter: str) -> list[int]:
        state = self._state[chapter]
        completed = set(state.completed_segments)
        return [i for i in range(state.segments_total) if i not in completed]

    def get_chapter_state(self, chapter: str) -> ChapterState | None:
        return self._state.get(chapter)

    def summary(self) -> dict:
        chapters_total = len(self._state)
        chapters_completed = sum(state.chapter_complete for state in self._state.values())
        segments_total = sum(state.segments_total for state in self._state.values())
        segments_completed = sum(state.segments_completed for state in self._state.values())
        return {
            "chapters_total": chapters_total,
            "chapters_completed": chapters_completed,
            "segments_total": segments_total,
            "segments_completed": segments_completed,
        }

    @staticmethod
    def _validate_segment_number(state: ChapterState, segment_number: int) -> None:
        if not 0 <= segment_number < state.segments_total:
            raise IndexError(
                f"segment_number {segment_number} outside 0..{state.segments_total - 1}"
            )
