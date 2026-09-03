from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class VideoRequest:
    """One presenter-video generation request.

    Providers write to ``output_path``. The orchestration layer normally gives
    providers a temporary path and only promotes it to the final artifact after
    validation succeeds.
    """

    audio_path: Path
    presenter_image_path: Path
    output_path: Path
    chapter: str
    segment_number: int
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoResult:
    output_path: Path
    provider: str
    metadata: Mapping[str, object] = field(default_factory=dict)


class VideoProvider(ABC):
    """Provider-neutral contract for image + audio -> presenter video."""

    name = "video-provider"

    @abstractmethod
    def generate(self, request: VideoRequest) -> VideoResult:
        """Generate one presenter video artifact at ``request.output_path``."""

    def cache_key(self) -> str:
        """Stable provider/config fingerprint used to invalidate stale videos."""
        return self.name


def validate_mp4(path: str | Path) -> bool:
    """Perform a lightweight ISO-BMFF/MP4 structural check.

    This deliberately avoids a hard FFmpeg dependency in the core package. A
    later media adapter can add ffprobe-level stream validation while retaining
    the same orchestration contract.
    """

    media_path = Path(path)
    if not media_path.is_file() or media_path.stat().st_size < 16:
        return False

    try:
        with media_path.open("rb") as handle:
            header = handle.read(64)
    except OSError:
        return False

    # MP4 files are ISO Base Media File Format and normally expose an ftyp box
    # near the beginning. Checking the bounded header catches empty/corrupt
    # placeholders without pretending to replace full media probing.
    return b"ftyp" in header[4:32]


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_fingerprint(data: Mapping[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
