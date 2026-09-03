from pathlib import Path

import pytest

from spyrath.media.video import ExportConfig, VideoProbe
from spyrath.pipeline.export import VideoAssemblyEngine


class FakeMedia:
    def __init__(self):
        self.config = ExportConfig()
        self.concat_calls = 0
        self.export_calls = 0

    def probe(self, path):
        p = Path(path)
        if not p.is_file() or p.stat().st_size == 0:
            raise ValueError("bad")
        delivery = b"H264" in p.read_bytes()
        return VideoProbe(30.0, True, True, "h264" if delivery else "mpeg4", "aac", 1400, 1122, "yuv420p")

    def validate_av(self, path):
        try:
            p = self.probe(path)
            return p.has_video and p.has_audio and p.duration > 0
        except ValueError:
            return False

    def concat_copy(self, inputs, output):
        self.concat_calls += 1
        Path(output).write_bytes(b"CHAPTER" + b"".join(Path(p).read_bytes() for p in inputs))

    def export_h264(self, inputs, output):
        self.export_calls += 1
        Path(output).write_bytes(b"H264" + b"".join(Path(p).read_bytes() for p in inputs))


def chunks(tmp_path, chapter, count):
    result = []
    for i in range(count):
        p = tmp_path / "chunks" / chapter / f"chunk_{i:03d}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"{chapter}-{i}".encode())
        result.append(p)
    return result


def test_assembles_chapter_and_reuses_when_sources_unchanged(tmp_path):
    media = FakeMedia(); engine = VideoAssemblyEngine(media)
    source = chunks(tmp_path, "c1", 3); out = tmp_path / "chapters" / "c1.mp4"
    first = engine.assemble_chapter(chapter="c1", chunks=source, output_path=out)
    second = engine.assemble_chapter(chapter="c1", chunks=source, output_path=out)
    assert not first.reused and second.reused
    assert media.concat_calls == 1


def test_changed_chunk_rebuilds_only_affected_chapter(tmp_path):
    media = FakeMedia(); engine = VideoAssemblyEngine(media)
    c1 = chunks(tmp_path, "c1", 2); c2 = chunks(tmp_path, "c2", 2)
    out1 = tmp_path / "chapters" / "c1.mp4"; out2 = tmp_path / "chapters" / "c2.mp4"
    engine.assemble_chapter(chapter="c1", chunks=c1, output_path=out1)
    engine.assemble_chapter(chapter="c2", chunks=c2, output_path=out2)
    c2[1].write_bytes(b"changed")
    r1 = engine.assemble_chapter(chapter="c1", chunks=c1, output_path=out1)
    r2 = engine.assemble_chapter(chapter="c2", chunks=c2, output_path=out2)
    assert r1.reused and not r2.reused
    assert media.concat_calls == 3


def test_final_export_is_h264_aac_yuv420p_and_resumable(tmp_path):
    media = FakeMedia(); engine = VideoAssemblyEngine(media)
    chapters = {"one": chunks(tmp_path, "one", 2), "two": chunks(tmp_path, "two", 1)}
    final = tmp_path / "final" / "book.mp4"
    first = engine.export_final(chapters=chapters, chapter_output_dir=tmp_path / "chapters", final_path=final)
    second = engine.export_final(chapters=chapters, chapter_output_dir=tmp_path / "chapters", final_path=final)
    assert not first.reused and second.reused
    assert media.export_calls == 1
    assert first.probe.video_codec == "h264"
    assert first.probe.audio_codec == "aac"
    assert first.probe.pixel_format == "yuv420p"


def test_invalid_source_chunk_stops_before_assembly(tmp_path):
    media = FakeMedia(); engine = VideoAssemblyEngine(media)
    source = chunks(tmp_path, "c", 2); source[1].write_bytes(b"")
    with pytest.raises(ValueError, match="Invalid presenter chunk"):
        engine.assemble_chapter(chapter="c", chunks=source, output_path=tmp_path / "c.mp4")


def test_failed_or_invalid_temp_never_replaces_existing_final(tmp_path):
    media = FakeMedia(); engine = VideoAssemblyEngine(media)
    source = chunks(tmp_path, "c", 1); out = tmp_path / "c.mp4"
    engine.assemble_chapter(chapter="c", chunks=source, output_path=out)
    original = out.read_bytes()
    source[0].write_bytes(b"new")
    def bad_concat(inputs, output):
        Path(output).write_bytes(b"")
    media.concat_copy = bad_concat
    with pytest.raises(RuntimeError, match="failed validation"):
        engine.assemble_chapter(chapter="c", chunks=source, output_path=out)
    assert out.read_bytes() == original
