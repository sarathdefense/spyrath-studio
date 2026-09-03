from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .base import TTSProvider, TTSRequest, TTSResult


class ChatterboxUnavailableError(RuntimeError):
    """Raised when Chatterbox dependencies are not installed or cannot load."""


class ChatterboxSynthesisError(RuntimeError):
    """Raised when Chatterbox cannot synthesize the requested narration."""


@dataclass(frozen=True)
class ChatterboxConfig:
    """Runtime settings for the English Chatterbox TTS provider.

    The defaults intentionally match the settings that were approved during
    Spyrath's reference book production run.
    """

    device: str = "auto"
    exaggeration: float = 0.3
    cfg_weight: float = 0.5
    require_voice_reference: bool = True

    def __post_init__(self) -> None:
        if self.device not in {"auto", "cuda", "mps", "cpu"}:
            raise ValueError("device must be one of: auto, cuda, mps, cpu")
        if not 0.0 <= self.exaggeration <= 2.0:
            raise ValueError("exaggeration must be between 0.0 and 2.0")
        if not 0.0 <= self.cfg_weight <= 1.0:
            raise ValueError("cfg_weight must be between 0.0 and 1.0")


ModelLoader = Callable[[str], Any]
AudioSaver = Callable[[Path, Any, int], None]
DeviceResolver = Callable[[], str]


class ChatterboxTTSProvider(TTSProvider):
    """Local voice-conditioned TTS provider backed by Resemble AI Chatterbox.

    Chatterbox is imported lazily so the Spyrath core package stays lightweight
    and remains usable without Torch/Chatterbox installed. Install the optional
    provider dependencies with ``pip install -e '.[chatterbox]'``.
    """

    name = "chatterbox"

    def __init__(
        self,
        config: ChatterboxConfig | None = None,
        *,
        model_loader: ModelLoader | None = None,
        audio_saver: AudioSaver | None = None,
        device_resolver: DeviceResolver | None = None,
    ) -> None:
        self.config = config or ChatterboxConfig()
        self._model_loader = model_loader or self._default_model_loader
        self._audio_saver = audio_saver or self._default_audio_saver
        self._device_resolver = device_resolver or self._detect_device
        self._model: Any | None = None
        self._resolved_device: str | None = None

    @property
    def device(self) -> str:
        if self._resolved_device is None:
            self._resolved_device = (
                self._device_resolver()
                if self.config.device == "auto"
                else self.config.device
            )
        return self._resolved_device

    def synthesize(self, request: TTSRequest) -> TTSResult:
        text = request.text.strip()
        if not text:
            raise ValueError("TTS request text must not be empty")
        if request.language.lower() not in {"en", "en-us", "en-gb"}:
            raise ValueError(
                "ChatterboxTTSProvider currently uses the English Chatterbox model; "
                f"unsupported language: {request.language}"
            )

        voice_reference = request.voice_reference
        if self.config.require_voice_reference and voice_reference is None:
            raise ValueError("voice_reference is required for voice-conditioned synthesis")
        if voice_reference is not None:
            voice_reference = Path(voice_reference)
            if not voice_reference.is_file():
                raise FileNotFoundError(f"Voice reference not found: {voice_reference}")

        output_path = Path(request.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model = self._get_model()
        try:
            generate_kwargs: dict[str, Any] = {
                "exaggeration": self.config.exaggeration,
                "cfg_weight": self.config.cfg_weight,
            }
            if voice_reference is not None:
                generate_kwargs["audio_prompt_path"] = str(voice_reference)

            wav = model.generate(text, **generate_kwargs)
            if hasattr(wav, "cpu"):
                wav = wav.cpu()

            sample_rate = int(model.sr)
            self._audio_saver(output_path, wav, sample_rate)
        except Exception as exc:  # provider boundary: normalize model/runtime failures
            output_path.unlink(missing_ok=True)
            if isinstance(exc, (ChatterboxUnavailableError, ChatterboxSynthesisError)):
                raise
            raise ChatterboxSynthesisError(
                f"Chatterbox synthesis failed on device '{self.device}': {exc}"
            ) from exc

        if not output_path.is_file() or output_path.stat().st_size == 0:
            output_path.unlink(missing_ok=True)
            raise ChatterboxSynthesisError(
                f"Chatterbox did not produce a valid audio file: {output_path}"
            )

        metadata = dict(request.metadata)
        metadata.update(
            {
                "device": self.device,
                "sample_rate": str(sample_rate),
                "exaggeration": str(self.config.exaggeration),
                "cfg_weight": str(self.config.cfg_weight),
                "voice_conditioned": str(voice_reference is not None).lower(),
            }
        )
        return TTSResult(
            output_path=output_path,
            provider=self.name,
            metadata=metadata,
        )

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                self._model = self._model_loader(self.device)
            except Exception as exc:
                if isinstance(exc, ChatterboxUnavailableError):
                    raise
                raise ChatterboxUnavailableError(
                    f"Unable to load Chatterbox on device '{self.device}': {exc}"
                ) from exc
        return self._model

    @staticmethod
    def _default_model_loader(device: str) -> Any:
        try:
            from chatterbox.tts import ChatterboxTTS
        except ImportError as exc:
            raise ChatterboxUnavailableError(
                "Chatterbox is not installed. Install Spyrath with the optional "
                "provider dependencies: pip install -e '.[chatterbox]'"
            ) from exc
        return ChatterboxTTS.from_pretrained(device=device)

    @staticmethod
    def _default_audio_saver(path: Path, wav: Any, sample_rate: int) -> None:
        try:
            import torchaudio
        except ImportError as exc:
            raise ChatterboxUnavailableError(
                "torchaudio is required by the Chatterbox provider"
            ) from exc
        torchaudio.save(str(path), wav, sample_rate)

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch
        except ImportError:
            return "cpu"

        if torch.cuda.is_available():
            return "cuda"

        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            return "mps"

        return "cpu"
