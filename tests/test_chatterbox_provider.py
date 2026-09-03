from pathlib import Path

import pytest

from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline import NarrationEngine, NarrationPlan
from spyrath.providers.tts import (
    ChatterboxConfig,
    ChatterboxSynthesisError,
    ChatterboxTTSProvider,
    TTSRequest,
)


class FakeWave:
    def __init__(self) -> None:
        self.cpu_called = False

    def cpu(self):
        self.cpu_called = True
        return self


class FakeModel:
    sr = 24_000

    def __init__(self) -> None:
        self.calls = []

    def generate(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return FakeWave()


def fake_saver(path: Path, wav: FakeWave, sample_rate: int) -> None:
    assert wav.cpu_called
    path.write_bytes(b"RIFF-chatterbox-test-wave")
    assert sample_rate == 24_000


def test_chatterbox_synthesizes_with_reference_and_approved_defaults(tmp_path):
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")
    model = FakeModel()
    provider = ChatterboxTTSProvider(
        model_loader=lambda device: model,
        audio_saver=fake_saver,
        device_resolver=lambda: "cuda",
    )
    output = tmp_path / "segment.wav.tmp"

    result = provider.synthesize(
        TTSRequest(
            text="Hello from Spyrath.",
            output_path=output,
            voice_reference=voice,
            metadata={"chapter": "chapter_01"},
        )
    )

    assert result.output_path == output
    assert result.provider == "chatterbox"
    assert output.exists()
    assert result.metadata["device"] == "cuda"
    assert result.metadata["exaggeration"] == "0.3"
    assert result.metadata["cfg_weight"] == "0.5"
    assert result.metadata["voice_conditioned"] == "true"
    assert model.calls == [
        (
            "Hello from Spyrath.",
            {
                "audio_prompt_path": str(voice),
                "exaggeration": 0.3,
                "cfg_weight": 0.5,
            },
        )
    ]


def test_chatterbox_loads_model_once_for_multiple_segments(tmp_path):
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")
    model = FakeModel()
    loads = []

    def load(device):
        loads.append(device)
        return model

    provider = ChatterboxTTSProvider(
        ChatterboxConfig(device="cpu"),
        model_loader=load,
        audio_saver=fake_saver,
    )

    for index in range(2):
        provider.synthesize(
            TTSRequest(
                text=f"Segment {index}",
                output_path=tmp_path / f"segment_{index}.wav",
                voice_reference=voice,
            )
        )

    assert loads == ["cpu"]
    assert len(model.calls) == 2


def test_chatterbox_requires_existing_voice_reference(tmp_path):
    provider = ChatterboxTTSProvider(
        model_loader=lambda device: FakeModel(),
        audio_saver=fake_saver,
        device_resolver=lambda: "cpu",
    )

    with pytest.raises(FileNotFoundError, match="Voice reference not found"):
        provider.synthesize(
            TTSRequest(
                text="Hello",
                output_path=tmp_path / "out.wav",
                voice_reference=tmp_path / "missing.wav",
            )
        )


def test_chatterbox_failure_removes_partial_output(tmp_path):
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")

    class BrokenModel(FakeModel):
        def generate(self, text, **kwargs):
            raise RuntimeError("GPU out of memory")

    output = tmp_path / "partial.wav"
    output.write_bytes(b"stale")
    provider = ChatterboxTTSProvider(
        model_loader=lambda device: BrokenModel(),
        audio_saver=fake_saver,
        device_resolver=lambda: "cuda",
    )

    with pytest.raises(ChatterboxSynthesisError, match="GPU out of memory"):
        provider.synthesize(
            TTSRequest(
                text="Hello",
                output_path=output,
                voice_reference=voice,
            )
        )

    assert not output.exists()


def test_narration_engine_resumes_with_chatterbox_provider(tmp_path):
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")
    checkpoint_file = tmp_path / "checkpoint.json"
    plan = NarrationPlan.from_texts("chapter_01", ["One", "Two", "Three"])

    first_model = FakeModel()
    first_provider = ChatterboxTTSProvider(
        model_loader=lambda device: first_model,
        audio_saver=fake_saver,
        device_resolver=lambda: "cpu",
    )
    first_engine = NarrationEngine(
        provider=first_provider,
        checkpoint=CheckpointManager(checkpoint_file),
        output_root=tmp_path / "audio",
    )
    first_progress = first_engine.run(plan, voice_reference=voice)
    assert first_progress.completed == 3
    assert len(first_model.calls) == 3

    # Simulate restart: the provider should not even need to load its model
    # because all final WAV artifacts already validate.
    loads = []
    resumed_provider = ChatterboxTTSProvider(
        model_loader=lambda device: loads.append(device),
        audio_saver=fake_saver,
        device_resolver=lambda: "cpu",
    )
    resumed_engine = NarrationEngine(
        provider=resumed_provider,
        checkpoint=CheckpointManager(checkpoint_file),
        output_root=tmp_path / "audio",
    )
    resumed_progress = resumed_engine.run(plan, voice_reference=voice)

    assert resumed_progress.completed == 3
    assert resumed_progress.remaining == 0
    assert loads == []


def test_chatterbox_rejects_non_english_language(tmp_path):
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")
    provider = ChatterboxTTSProvider(
        model_loader=lambda device: FakeModel(),
        audio_saver=fake_saver,
        device_resolver=lambda: "cpu",
    )

    with pytest.raises(ValueError, match="unsupported language"):
        provider.synthesize(
            TTSRequest(
                text="Hola",
                output_path=tmp_path / "out.wav",
                voice_reference=voice,
                language="es",
            )
        )
