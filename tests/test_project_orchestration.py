from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from spyrath.project import (
    ProjectChapter,
    ProjectOrchestrator,
    ProjectSpec,
    ProjectStage,
    StageStatus,
)


class FakeNarration:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.provider = SimpleNamespace(name="fake-tts")
        self.calls: list[str] = []

    def output_dir(self, chapter: str) -> Path:
        return self.output_root / chapter

    def run(self, plan, *, voice_reference=None, language="en"):
        self.calls.append(plan.chapter)
        directory = self.output_dir(plan.chapter)
        directory.mkdir(parents=True, exist_ok=True)
        for index, segment in enumerate(plan.segments):
            (directory / f"chunk_{index:03d}.wav").write_bytes(
                f"wav:{plan.chapter}:{segment.text}".encode()
            )
        return SimpleNamespace(completed=len(plan.segments))


class FakeAudio:
    def __init__(self):
        self.calls: list[str] = []

    def prepare(self, *, chapter, narration_segments, chapter_output_path, chunks_output_dir):
        self.calls.append(chapter)
        source_payload = b"".join(Path(path).read_bytes() for path in narration_segments)
        chapter_output_path = Path(chapter_output_path)
        chapter_output_path.parent.mkdir(parents=True, exist_ok=True)
        chapter_output_path.write_bytes(source_payload or b"chapter")
        directory = Path(chunks_output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        chunk = directory / "chunk_000.wav"
        chunk.write_bytes(source_payload or b"audio")
        (directory / "manifest.json").write_text(
            json.dumps({"chunks": [chunk.name]}), encoding="utf-8"
        )
        return SimpleNamespace()


class FakeVideoProvider:
    name = "fake-video"

    def cache_key(self):
        return "fake-video:v1"


class FakePresenter:
    def __init__(self, *, fail=False):
        self.provider = FakeVideoProvider()
        self.calls: list[str] = []
        self.fail = fail

    def render(self, *, chapter, audio_chunks, presenter_image, output_dir):
        self.calls.append(chapter)
        if self.fail:
            raise RuntimeError("presenter GPU interrupted")
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        chunk = directory / "chunk_000.mp4"
        payload = b"".join(Path(path).read_bytes() for path in audio_chunks)
        chunk.write_bytes(b"mp4:" + Path(presenter_image).read_bytes() + payload)
        (directory / "manifest.json").write_text(
            json.dumps({"chunks": [chunk.name]}), encoding="utf-8"
        )
        return SimpleNamespace()


class FakeConfig:
    def cache_key(self):
        return "h264:crf18"


class FakeExporter:
    def __init__(self):
        self.media = SimpleNamespace(config=FakeConfig())
        self.calls = 0

    def export_final(self, *, chapters, chapter_output_dir, final_path):
        self.calls += 1
        final = Path(final_path)
        final.parent.mkdir(parents=True, exist_ok=True)
        payload = b"".join(
            Path(path).read_bytes()
            for chapter_paths in chapters.values()
            for path in chapter_paths
        )
        final.write_bytes(b"final:" + payload)
        return SimpleNamespace(path=final)


def make_spec(tmp_path: Path) -> ProjectSpec:
    presenter = tmp_path / "presenter.png"
    presenter.write_bytes(b"presenter-v1")
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice-v1")
    return ProjectSpec(
        project_id="ml-book",
        title="Machine Learning for Beginners",
        chapters=(
            ProjectChapter.from_texts("01_preface", ["Welcome", "Before we begin"]),
            ProjectChapter.from_texts("02_chapter_1", ["What is machine learning?"]),
        ),
        presenter_image=presenter,
        voice_reference=voice,
    )


def build(tmp_path: Path, spec: ProjectSpec, *, presenter=None):
    project_root = tmp_path / "project"
    narration = FakeNarration(project_root / "narration")
    audio = FakeAudio()
    video = presenter or FakePresenter()
    exporter = FakeExporter()
    orchestrator = ProjectOrchestrator(
        spec=spec,
        project_root=project_root,
        narration=narration,
        audio=audio,
        presenter=video,
        exporter=exporter,
    )
    return orchestrator, narration, audio, video, exporter


def test_project_run_completes_every_stage_and_persists_state(tmp_path):
    spec = make_spec(tmp_path)
    orchestrator, narration, audio, presenter, exporter = build(tmp_path, spec)

    result = orchestrator.run()

    assert result.completed
    assert result.final_path is not None and result.final_path.is_file()
    assert narration.calls == ["01_preface", "02_chapter_1"]
    assert audio.calls == ["01_preface", "02_chapter_1"]
    assert presenter.calls == ["01_preface", "02_chapter_1"]
    assert exporter.calls == 1
    state = orchestrator.status()
    assert all(state.stage(stage).status == StageStatus.COMPLETED for stage in ProjectStage)
    assert (tmp_path / "project" / "project.json").is_file()


def test_second_run_reuses_all_completed_project_stages(tmp_path):
    spec = make_spec(tmp_path)
    first, *_ = build(tmp_path, spec)
    first.run()

    resumed, narration, audio, presenter, exporter = build(tmp_path, spec)
    result = resumed.resume()

    assert result.completed
    assert narration.calls == []
    assert audio.calls == []
    assert presenter.calls == []
    assert exporter.calls == 0


def test_failure_is_persisted_and_resume_continues_from_failed_stage(tmp_path):
    spec = make_spec(tmp_path)
    failing_presenter = FakePresenter(fail=True)
    first, narration, audio, _, exporter = build(tmp_path, spec, presenter=failing_presenter)

    with pytest.raises(RuntimeError, match="GPU interrupted"):
        first.run()

    failed = first.status()
    assert failed.stage(ProjectStage.NARRATION).status == StageStatus.COMPLETED
    assert failed.stage(ProjectStage.AUDIO).status == StageStatus.COMPLETED
    assert failed.stage(ProjectStage.PRESENTER).status == StageStatus.FAILED
    assert failed.stage(ProjectStage.EXPORT).status == StageStatus.PENDING
    assert "GPU interrupted" in (failed.last_error or "")
    assert exporter.calls == 0

    resumed, narration2, audio2, presenter2, exporter2 = build(tmp_path, spec)
    result = resumed.resume()

    assert result.completed
    assert narration2.calls == []
    assert audio2.calls == []
    assert presenter2.calls == ["01_preface", "02_chapter_1"]
    assert exporter2.calls == 1


def test_changed_presenter_image_reruns_presenter_and_export_only(tmp_path):
    spec = make_spec(tmp_path)
    first, *_ = build(tmp_path, spec)
    first.run()

    spec.presenter_image.write_bytes(b"presenter-v2")
    resumed, narration, audio, presenter, exporter = build(tmp_path, spec)
    result = resumed.resume()

    assert result.completed
    assert narration.calls == []
    assert audio.calls == []
    assert presenter.calls == ["01_preface", "02_chapter_1"]
    assert exporter.calls == 1


def test_missing_audio_artifact_rebuilds_audio_and_downstream_only(tmp_path):
    spec = make_spec(tmp_path)
    first, *_ = build(tmp_path, spec)
    first.run()

    missing = tmp_path / "project" / "audio" / "chunks" / "01_preface" / "chunk_000.wav"
    missing.unlink()

    resumed, narration, audio, presenter, exporter = build(tmp_path, spec)
    result = resumed.resume()

    assert result.completed
    assert narration.calls == []
    assert audio.calls == ["01_preface", "02_chapter_1"]
    assert presenter.calls == ["01_preface", "02_chapter_1"]
    assert exporter.calls == 1
