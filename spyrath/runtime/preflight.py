from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class RuntimeCapability:
    name: str
    ready: bool
    detail: str


@dataclass(frozen=True)
class RuntimePreflightReport:
    capabilities: tuple[RuntimeCapability, ...]

    @property
    def ready(self) -> bool:
        return all(item.ready for item in self.capabilities)

    def as_dict(self) -> dict[str, object]:
        return {"ready": self.ready, "capabilities": [item.__dict__ for item in self.capabilities]}


class RuntimePreflight:
    """Validate worker prerequisites before an expensive production job starts."""

    def __init__(
        self,
        *,
        sadtalker_repository: Path | None,
        sadtalker_python: str,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        require_gpu: bool = True,
        runner: Runner = subprocess.run,
    ) -> None:
        self.sadtalker_repository = sadtalker_repository
        self.sadtalker_python = sadtalker_python
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.require_gpu = require_gpu
        self.runner = runner

    def check(self) -> RuntimePreflightReport:
        caps: list[RuntimeCapability] = []
        repo = self.sadtalker_repository
        inference = repo / "inference.py" if repo else None
        caps.append(RuntimeCapability("sadtalker", bool(inference and inference.is_file()), str(inference or "not configured")))
        caps.append(self._command("python", self.sadtalker_python, ["--version"]))
        caps.append(self._command("ffmpeg", self.ffmpeg, ["-version"]))
        caps.append(self._command("ffprobe", self.ffprobe, ["-version"]))
        gpu = self._gpu()
        if not self.require_gpu and not gpu.ready:
            gpu = RuntimeCapability("gpu", True, "GPU check optional: " + gpu.detail)
        caps.append(gpu)
        return RuntimePreflightReport(tuple(caps))

    def require_ready(self) -> RuntimePreflightReport:
        report = self.check()
        if not report.ready:
            failed = ", ".join(f"{x.name}: {x.detail}" for x in report.capabilities if not x.ready)
            raise RuntimeError(f"Production runtime preflight failed: {failed}")
        return report

    def _command(self, name: str, command: str, args: list[str]) -> RuntimeCapability:
        executable = shutil.which(command) if "/" not in command else (command if Path(command).is_file() else None)
        if not executable:
            return RuntimeCapability(name, False, f"not found: {command}")
        try:
            result = self.runner([executable, *args], capture_output=True, text=True)
        except OSError as exc:
            return RuntimeCapability(name, False, str(exc))
        detail = (result.stdout or result.stderr or "").splitlines()[0:1]
        return RuntimeCapability(name, result.returncode == 0, detail[0] if detail else executable)

    def _gpu(self) -> RuntimeCapability:
        executable = shutil.which("nvidia-smi")
        if not executable:
            return RuntimeCapability("gpu", False, "nvidia-smi not found")
        try:
            result = self.runner([executable, "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
        except OSError as exc:
            return RuntimeCapability("gpu", False, str(exc))
        detail = result.stdout.strip() or result.stderr.strip() or "GPU unavailable"
        return RuntimeCapability("gpu", result.returncode == 0 and bool(result.stdout.strip()), detail)
