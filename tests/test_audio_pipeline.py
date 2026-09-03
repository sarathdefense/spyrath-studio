import math
import time
import wave
from pathlib import Path

import pytest

from spyrath.checkpoint import CheckpointManager
from spyrath.media import (
    AudioPreparationEngine,
    AudioSegmenter,
    ChapterAssembler,
    inspect_pcm_wav,
    validate_pcm_wav,
)


def write_wav(
    path: Path,
    *,
    seconds: float,
    frame_rate: int = 8_000,
    channels: int = 1,
    sample_width: int = 2,
    sample_byte: bytes = b"\x01\x00",
) -> int:
    frames = int(round(seconds * frame_rate))
    frame = sample_byte * channels
    if len(frame) != sample_width * channels:
        frame = b"\x01" * (sample_width * channels)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(frame_rate)
        writer.writeframes(frame * frames)
    return frames


def test_chapter_assembler_concatenates_and_reuses_valid_output(tmp_path):
    first = tmp_path / "segment_000.wav"
    second = tmp_path / "segment_001.wav"
    first_frames = write_wav(first, seconds=1.25)
    second_frames = write_wav(second, seconds=0.75)
    output = tmp_path / "chapter.wav"

    assembler = ChapterAssembler()
    initial = assembler.assemble([first, second], output)

    assert initial.reused is False
    assert initial.frames == first_frames + second_frames
    assert validate_pcm_wav(output)
    assert output.with_name("chapter.wav.manifest.json").is_file()

    reused = assembler.assemble([first, second], output)
    assert reused.reused is True
    assert reused.frames == initial.frames


def test_chapter_assembler_rejects_incompatible_wav_formats(tmp_path):
    first = tmp_path / "a.wav"
    second = tmp_path / "b.wav"
    write_wav(first, seconds=1, frame_rate=8_000)
    write_wav(second, seconds=1, frame_rate=16_000)
    output = tmp_path / "chapter.wav"

    with pytest.raises(ValueError, match="format mismatch"):
        ChapterAssembler().assemble([first, second], output)

    assert not output.exists()


def test_segmenter_splits_65_seconds_into_30_30_5(tmp_path):
    source = tmp_path / "chapter.wav"
    write_wav(source, seconds=65, frame_rate=1_000)
    checkpoint = CheckpointManager(tmp_path / "checkpoint.json")
    segmenter = AudioSegmenter(checkpoint=checkpoint, target_duration_seconds=30)

    result = segmenter.segment(
        chapter="chapter_01",
        source_path=source,
        output_dir=tmp_path / "chunks",
    )

    assert result.chunks_total == 3
    assert result.progress.completed == 3
    assert result.progress.remaining == 0
    assert [inspect_pcm_wav(path).frames for path in result.chunk_paths] == [30_000, 30_000, 5_000]
    assert (tmp_path / "chunks" / "manifest.json").is_file()


def test_segmenter_resume_regenerates_only_invalid_chunk(tmp_path):
    source = tmp_path / "chapter.wav"
    write_wav(source, seconds=65, frame_rate=1_000)
    checkpoint_path = tmp_path / "checkpoint.json"
    output_dir = tmp_path / "chunks"

    first = AudioSegmenter(
        checkpoint=CheckpointManager(checkpoint_path),
        target_duration_seconds=30,
    ).segment(chapter="chapter", source_path=source, output_dir=output_dir)

    mtimes = [path.stat().st_mtime_ns for path in first.chunk_paths]
    first.chunk_paths[1].write_bytes(b"")
    time.sleep(0.01)

    resumed = AudioSegmenter(
        checkpoint=CheckpointManager(checkpoint_path),
        target_duration_seconds=30,
    ).segment(chapter="chapter", source_path=source, output_dir=output_dir)

    assert resumed.progress.completed == 3
    assert resumed.chunk_paths[0].stat().st_mtime_ns == mtimes[0]
    assert resumed.chunk_paths[1].stat().st_mtime_ns > mtimes[1]
    assert resumed.chunk_paths[2].stat().st_mtime_ns == mtimes[2]
    assert all(validate_pcm_wav(path) for path in resumed.chunk_paths)


def test_source_change_invalidates_old_chunks_and_removes_stale_tail(tmp_path):
    source = tmp_path / "chapter.wav"
    write_wav(source, seconds=65, frame_rate=1_000)
    checkpoint = CheckpointManager(tmp_path / "checkpoint.json")
    segmenter = AudioSegmenter(checkpoint=checkpoint, target_duration_seconds=30)
    output_dir = tmp_path / "chunks"

    first = segmenter.segment(chapter="chapter", source_path=source, output_dir=output_dir)
    assert first.chunks_total == 3
    old_first_mtime = first.chunk_paths[0].stat().st_mtime_ns

    time.sleep(0.01)
    write_wav(source, seconds=35, frame_rate=1_000, sample_byte=b"\x02\x00")
    second = segmenter.segment(chapter="chapter", source_path=source, output_dir=output_dir)

    assert second.chunks_total == 2
    assert second.chunk_paths[0].stat().st_mtime_ns > old_first_mtime
    assert not (output_dir / "chunk_002.wav").exists()
    assert [inspect_pcm_wav(path).frames for path in second.chunk_paths] == [30_000, 5_000]


def test_audio_preparation_engine_assembles_then_segments(tmp_path):
    narration_dir = tmp_path / "narration"
    narration_dir.mkdir()
    sources = []
    for index, seconds in enumerate((12.0, 13.0, 12.0)):
        path = narration_dir / f"segment_{index:03d}.wav"
        write_wav(path, seconds=seconds, frame_rate=1_000)
        sources.append(path)

    engine = AudioPreparationEngine(
        checkpoint=CheckpointManager(tmp_path / "checkpoint.json"),
        target_duration_seconds=30,
    )
    result = engine.prepare(
        chapter="chapter_01",
        narration_segments=sources,
        chapter_output_path=tmp_path / "chapters" / "chapter_01.wav",
        chunks_output_dir=tmp_path / "chunks" / "chapter_01",
    )

    assert math.isclose(result.assembly.duration_seconds, 37.0)
    assert result.segmentation.chunks_total == 2
    assert [inspect_pcm_wav(path).frames for path in result.segmentation.chunk_paths] == [30_000, 7_000]
