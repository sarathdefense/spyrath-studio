from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

from .base import VideoProvider, VideoRequest, VideoResult, stable_fingerprint, validate_mp4

Runner = Callable[..., subprocess.CompletedProcess]


class SadTalkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SadTalkerConfig:
    repository_dir: Path
    python_executable: str = sys.executable
    checkpoint_dir: Path | None = None
    preprocess: str = "full"
    expression_scale: float = 1.0
    still: bool = True
    enhancer: str | None = None
    extra_args: tuple[str, ...] = ()


class SadTalkerProvider(VideoProvider):
    """Subprocess adapter for a local SadTalker checkout.

    SadTalker chooses its own result filename, so each request receives an
    isolated result directory. The provider locates the generated MP4 and copies
    it to Spyrath's requested temporary artifact path.
    """

    name = "sadtalker"

    def __init__(
        self,
        config: SadTalkerConfig,
        *,
        runner: Runner = subprocess.run,
    ) -> None:
        self.config = config
        self.runner = runner

    def cache_key(self) -> str:
        config_data = asdict(self.config)
        config_data["repository_dir"] = str(self.config.repository_dir.resolve())
        if self.config.checkpoint_dir is not None:
            config_data["checkpoint_dir"] = str(self.config.checkpoint_dir.resolve())
        return f"{self.name}:{stable_fingerprint(config_data)[:20]}"

    def generate(self, request: VideoRequest) -> VideoResult:
        self._validate_request(request)
        inference_script = self.config.repository_dir / "inference.py"
        if not inference_script.is_file():
            raise SadTalkerError(f"SadTalker inference.py not found: {inference_script}")

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="spyrath-sadtalker-") as temp_dir:
            result_dir = Path(temp_dir) / "results"
            result_dir.mkdir(parents=True, exist_ok=True)
            command = self._build_command(request, result_dir)

            try:
                completed = self.runner(
                    command,
                    cwd=str(self.config.repository_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                raise SadTalkerError(f"Unable to start SadTalker: {exc}") from exc

            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                stdout = (completed.stdout or "").strip()
                details = stderr or stdout or f"exit code {completed.returncode}"
                raise SadTalkerError(f"SadTalker generation failed: {details}")

            candidates = sorted(
                result_dir.rglob("*.mp4"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
            if not candidates:
                raise SadTalkerError("SadTalker completed without producing an MP4")

            source = candidates[0]
            if not validate_mp4(source):
                raise SadTalkerError(f"SadTalker produced an invalid MP4: {source}")
            shutil.copyfile(source, request.output_path)

        return VideoResult(
            output_path=request.output_path,
            provider=self.name,
            metadata={"cache_key": self.cache_key()},
        )

    def _build_command(self, request: VideoRequest, result_dir: Path) -> list[str]:
        command: list[str] = [
            self.config.python_executable,
            "inference.py",
            "--driven_audio",
            str(request.audio_path.resolve()),
            "--source_image",
            str(request.presenter_image_path.resolve()),
            "--result_dir",
            str(result_dir),
            "--preprocess",
            self.config.preprocess,
            "--expression_scale",
            str(self.config.expression_scale),
        ]
        if self.config.still:
            command.append("--still")
        if self.config.checkpoint_dir is not None:
            command.extend(["--checkpoint_dir", str(self.config.checkpoint_dir.resolve())])
        if self.config.enhancer:
            command.extend(["--enhancer", self.config.enhancer])
        command.extend(self.config.extra_args)
        return command

    @staticmethod
    def _validate_request(request: VideoRequest) -> None:
        if not request.audio_path.is_file() or request.audio_path.stat().st_size <= 0:
            raise SadTalkerError(f"Audio input does not exist or is empty: {request.audio_path}")
        if not request.presenter_image_path.is_file() or request.presenter_image_path.stat().st_size <= 0:
            raise SadTalkerError(
                f"Presenter image does not exist or is empty: {request.presenter_image_path}"
            )
