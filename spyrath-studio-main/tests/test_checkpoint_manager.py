import json

from spyrath.checkpoint import CheckpointManager


def test_checkpoint_tracks_nonsequential_segments(tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    manager = CheckpointManager(checkpoint_file)
    manager.initialize_chapter("chapter_01", segments_total=4)

    manager.mark_segment_complete("chapter_01", 3)

    assert manager.is_segment_complete("chapter_01", 3)
    assert not manager.is_segment_complete("chapter_01", 0)
    assert manager.missing_segments("chapter_01") == [0, 1, 2]

    resumed = CheckpointManager(checkpoint_file)
    assert resumed.is_segment_complete("chapter_01", 3)
    assert resumed.missing_segments("chapter_01") == [0, 1, 2]


def test_old_checkpoint_format_is_migrated(tmp_path):
    checkpoint_file = tmp_path / "checkpoint.json"
    checkpoint_file.write_text(
        json.dumps({
            "chapter_01": {
                "chapter": "chapter_01",
                "segments_total": 4,
                "segments_completed": 2,
                "chapter_complete": False,
            }
        }),
        encoding="utf-8",
    )

    manager = CheckpointManager(checkpoint_file)
    assert manager.is_segment_complete("chapter_01", 0)
    assert manager.is_segment_complete("chapter_01", 1)
    assert not manager.is_segment_complete("chapter_01", 2)
