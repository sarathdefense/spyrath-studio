from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class TTSRequest:
    text: str
    output_path: Path
    voice_reference: Path | None = None
    language: str = "en"
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TTSResult:
    output_path: Path
    provider: str
    metadata: Mapping[str, str] = field(default_factory=dict)


class TTSProvider(ABC):
    """Provider contract for text-to-speech generation.

    Implementations may wrap local models such as Chatterbox or remote APIs,
    but callers only depend on this small interface.
    """

    name = "base"

    @abstractmethod
    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate narration audio at ``request.output_path``.

        Providers must return only after the requested output file has been
        written. Validation and atomic promotion to the final artifact path are
        handled by the narration pipeline.
        """
        raise NotImplementedError
