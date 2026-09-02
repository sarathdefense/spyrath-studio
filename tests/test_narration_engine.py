from pathlib import Path

import pytest

from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline import NarrationEngine, NarrationPlan
from spyrath.providers.tts import TTSProvider, TTSRequest, TTSResult


class FakeTTSProvider(TTSProvider):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[TTSRequest] = []

    def synthesize(self, request: TTSRequest) -> TTSResult:
        self.calls.append(request)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(b"RIFF-fake-wave-data")
        return TTSResult(output_path=request.output_path, provider=self.name)


def test_narration_generates_all_segments(tmp_path):
    checkpoint = CheckpointManager(tmp_path / "checkpoint.json")
    provider = FakeTTSProvider()
    plan = NarrationPlan.from_texts("chapter_01", ["Hello.", "World."])
    engine = NarrationEngine(
        provider=provider,
        checkpoint=checkpoint,
        output_root=tmp_path / "audio",
    )

    progress = engine.run(plan, voice_reference=tmp_path / "voice.wav")

    assert progress.completed == 2
    assert progress.total == 2
    assert len(provider.calls) == 2
    assert (tmp_path / "audio/chapter_01/chunk_000.wav").exists()
    assert (tmp_path / "audio/chapter_01/chunk_001.wav").exists()
    assert provider.calls[0].metadata["chapter"] == "chapter_01"


def test_narration_resume_skips_valid_existing_audio(tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    plan = NarrationPlan.from_texts("chapter_01", ["One", "Two", "Three"])

    first_provider = FakeTTSProvider()
    first_engine = NarrationEngine(
        provider=first_provider,
        checkpoint=CheckpointManager(checkpoint_file),
        output_root=tmp_path / "audio",
    )
    first_engine.run(plan)
    assert len(first_provider.calls) == 3

    # Simulate runtime restart. Existing valid audio is the source of truth.
    resumed_provider = FakeTTSProvider()
    resumed_engine = NarrationEngine(
        provider=resumed_provider,
        checkpoint=CheckpointManager(checkpoint_file),
        output_root=tmp_path / "audio",
    )
    progress = resumed_engine.run(plan)

    assert progress.completed == 3
    assert resumed_provider.calls == []


def test_invalid_existing_audio_is_regenerated(tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    plan = NarrationPlan.from_texts("chapter_01", ["One", "Two"])
    output_root = tmp_path / "audio"

    provider = FakeTTSProvider()
    engine = NarrationEngine(
        provider=provider,
        checkpoint=CheckpointManager(checkpoint_file),
        output_root=output_root,
    )
    engine.run(plan)

    # Corrupt one completed artifact with a zero-byte placeholder.
    (output_root / "chapter_01/chunk_001.wav").write_bytes(b"")

    resumed_provider = FakeTTSProvider()
    resumed_engine = NarrationEngine(
        provider=resumed_provider,
        checkpoint=CheckpointManager(checkpoint_file),
        output_root=output_root,
    )
    progress = resumed_engine.run(plan)

    assert progress.completed == 2
    assert len(resumed_provider.calls) == 1
    assert resumed_provider.calls[0].text == "Two"


def test_provider_must_write_to_requested_temp_path(tmp_path):
    class BadProvider(TTSProvider):
        name = "bad"

        def synthesize(self, request: TTSRequest) -> TTSResult:
            other = request.output_path.with_name("wrong.wav")
            other.write_bytes(b"bad")
            return TTSResult(output_path=other, provider=self.name)

    engine = NarrationEngine(
        provider=BadProvider(),
        checkpoint=CheckpointManager(tmp_path / "checkpoint.json"),
        output_root=tmp_path / "audio",
    )

    with pytest.raises(RuntimeError, match="unexpected output path"):
        engine.run(NarrationPlan.from_texts("chapter_01", ["Hello"]))


def test_narration_plan_rejects_empty_text():
    with pytest.raises(ValueError, match="text must not be empty"):
        NarrationPlan.from_texts("chapter_01", [" "])
