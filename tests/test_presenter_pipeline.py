from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline.presenter import PresenterProductionEngine
from spyrath.providers.video import (
    SadTalkerConfig,
    SadTalkerProvider,
    VideoProvider,
    VideoRequest,
    VideoResult,
    validate_mp4,
)


def write_fake_mp4(path: Path, payload: bytes = b"video") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal ISO-BMFF-like bytes sufficient for the core lightweight validator.
    path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + payload)


class FakeVideoProvider(VideoProvider):
    name = "fake-presenter"

    def __init__(self, version: str = "v1") -> None:
        self.version = version
        self.calls: list[int] = []

    def cache_key(self) -> str:
        return f"{self.name}:{self.version}"

    def generate(self, request: VideoRequest) -> VideoResult:
        self.calls.append(request.segment_number)
        write_fake_mp4(request.output_path, f"segment-{request.segment_number}".encode())
        return VideoResult(output_path=request.output_path, provider=self.name)


def make_inputs(tmp_path: Path, count: int) -> tuple[list[Path], Path]:
    audio = []
    for index in range(count):
        path = tmp_path / "audio" / f"chunk_{index:03d}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"audio-{index}".encode())
        audio.append(path)
    image = tmp_path / "presenter.png"
    image.write_bytes(b"presenter-image")
    return audio, image


def test_presenter_pipeline_generates_and_reuses_valid_chunks(tmp_path):
    audio, image = make_inputs(tmp_path, 4)
    checkpoint_file = tmp_path / "checkpoint.json"
    provider = FakeVideoProvider()
    engine = PresenterProductionEngine(
        provider=provider,
        checkpoint=CheckpointManager(checkpoint_file),
    )

    result = engine.render(
        chapter="chapter_01",
        audio_chunks=audio,
        presenter_image=image,
        output_dir=tmp_path / "video" / "chapter_01",
    )
    assert result.progress.completed == 4
    assert result.generated == 4
    assert provider.calls == [0, 1, 2, 3]
    assert all(validate_mp4(path) for path in result.chunk_paths)

    resumed_provider = FakeVideoProvider()
    resumed = PresenterProductionEngine(
        provider=resumed_provider,
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(
        chapter="chapter_01",
        audio_chunks=audio,
        presenter_image=image,
        output_dir=tmp_path / "video" / "chapter_01",
    )
    assert resumed.progress.completed == 4
    assert resumed.generated == 0
    assert resumed.reused == 4
    assert resumed_provider.calls == []


def test_presenter_pipeline_regenerates_corrupt_chunk_only(tmp_path):
    audio, image = make_inputs(tmp_path, 5)
    checkpoint_file = tmp_path / "checkpoint.json"
    output = tmp_path / "video"
    first = FakeVideoProvider()
    PresenterProductionEngine(
        provider=first,
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(chapter="c", audio_chunks=audio, presenter_image=image, output_dir=output)

    (output / "chunk_003.mp4").write_bytes(b"")
    resumed_provider = FakeVideoProvider()
    result = PresenterProductionEngine(
        provider=resumed_provider,
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(chapter="c", audio_chunks=audio, presenter_image=image, output_dir=output)

    assert result.progress.completed == 5
    assert result.generated == 1
    assert resumed_provider.calls == [3]
    assert validate_mp4(output / "chunk_003.mp4")


def test_107_chunk_resume_continues_at_99_without_regenerating_first_98(tmp_path):
    audio, image = make_inputs(tmp_path, 107)
    checkpoint_file = tmp_path / "checkpoint.json"
    output = tmp_path / "presenter"

    first_provider = FakeVideoProvider()
    first_engine = PresenterProductionEngine(
        provider=first_provider,
        checkpoint=CheckpointManager(checkpoint_file),
    )
    partial = first_engine.render(
        chapter="book",
        audio_chunks=audio,
        presenter_image=image,
        output_dir=output,
        segments=range(98),
    )
    assert partial.progress.completed == 98
    assert first_provider.calls == list(range(98))

    resumed_provider = FakeVideoProvider()
    resumed = PresenterProductionEngine(
        provider=resumed_provider,
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(
        chapter="book",
        audio_chunks=audio,
        presenter_image=image,
        output_dir=output,
    )
    assert resumed.progress.completed == 107
    assert resumed_provider.calls == list(range(98, 107))
    assert resumed.generated == 9
    assert all(validate_mp4(output / f"chunk_{i:03d}.mp4") for i in range(107))


def test_changed_presenter_image_invalidates_existing_videos(tmp_path):
    audio, image = make_inputs(tmp_path, 3)
    checkpoint_file = tmp_path / "checkpoint.json"
    output = tmp_path / "video"

    PresenterProductionEngine(
        provider=FakeVideoProvider(),
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(chapter="c", audio_chunks=audio, presenter_image=image, output_dir=output)

    image.write_bytes(b"new-presenter-image")
    provider = FakeVideoProvider()
    result = PresenterProductionEngine(
        provider=provider,
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(chapter="c", audio_chunks=audio, presenter_image=image, output_dir=output)

    assert result.generated == 3
    assert provider.calls == [0, 1, 2]


def test_changed_provider_config_invalidates_existing_videos(tmp_path):
    audio, image = make_inputs(tmp_path, 2)
    checkpoint_file = tmp_path / "checkpoint.json"
    output = tmp_path / "video"

    PresenterProductionEngine(
        provider=FakeVideoProvider("v1"),
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(chapter="c", audio_chunks=audio, presenter_image=image, output_dir=output)

    provider = FakeVideoProvider("v2")
    result = PresenterProductionEngine(
        provider=provider,
        checkpoint=CheckpointManager(checkpoint_file),
    ).render(chapter="c", audio_chunks=audio, presenter_image=image, output_dir=output)
    assert result.generated == 2
    assert provider.calls == [0, 1]


def test_sadtalker_provider_builds_command_and_collects_output(tmp_path):
    repo = tmp_path / "SadTalker"
    repo.mkdir()
    (repo / "inference.py").write_text("# fake", encoding="utf-8")
    audio, image = make_inputs(tmp_path, 1)
    output = tmp_path / "out.mp4.tmp"
    seen: dict[str, object] = {}

    def fake_runner(command, **kwargs):
        seen["command"] = command
        result_dir = Path(command[command.index("--result_dir") + 1])
        write_fake_mp4(result_dir / "run" / "result.mp4")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    provider = SadTalkerProvider(
        SadTalkerConfig(
            repository_dir=repo,
            python_executable="python3.10",
            checkpoint_dir=tmp_path / "checkpoints",
            enhancer="gfpgan",
        ),
        runner=fake_runner,
    )
    result = provider.generate(
        VideoRequest(
            audio_path=audio[0],
            presenter_image_path=image,
            output_path=output,
            chapter="chapter_01",
            segment_number=0,
        )
    )

    command = seen["command"]
    assert command[0] == "python3.10"
    assert "--driven_audio" in command
    assert "--source_image" in command
    assert "--result_dir" in command
    assert "--still" in command
    assert "--checkpoint_dir" in command
    assert "--enhancer" in command
    assert result.output_path == output
    assert validate_mp4(output)


def test_sadtalker_provider_surfaces_process_failure(tmp_path):
    repo = tmp_path / "SadTalker"
    repo.mkdir()
    (repo / "inference.py").write_text("# fake", encoding="utf-8")
    audio, image = make_inputs(tmp_path, 1)

    def failed_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="GPU failed")

    provider = SadTalkerProvider(SadTalkerConfig(repository_dir=repo), runner=failed_runner)
    with pytest.raises(RuntimeError, match="GPU failed"):
        provider.generate(
            VideoRequest(
                audio_path=audio[0],
                presenter_image_path=image,
                output_path=tmp_path / "out.mp4.tmp",
                chapter="chapter_01",
                segment_number=0,
            )
        )
