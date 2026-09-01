from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline import ProductionJob


def test_resume_107_chunks_from_99_without_regenerating_existing(tmp_path):
    output_dir = tmp_path / "chunks"
    output_dir.mkdir()

    # Simulate the expensive work already completed before a runtime interruption.
    for i in range(98):
        (output_dir / f"chunk_{i:03d}.mp4").write_bytes(f"valid-{i}".encode())

    checkpoint = CheckpointManager(tmp_path / "checkpoint.json")
    job = ProductionJob(
        chapter="book",
        segments_total=107,
        output_dir=output_dir,
        checkpoint=checkpoint,
    )

    generated = []

    def producer(segment_number, temp_path):
        generated.append(segment_number)
        temp_path.write_bytes(f"generated-{segment_number}".encode())

    before = job.reconcile()
    assert before.completed == 98
    assert job.missing_segments() == list(range(98, 107))

    after = job.run(producer)

    assert generated == list(range(98, 107))
    assert after.completed == 107
    assert after.remaining == 0
    assert after.percent == 100.0


def test_invalid_artifact_is_regenerated_even_if_checkpoint_says_complete(tmp_path):
    output_dir = tmp_path / "chunks"
    output_dir.mkdir()
    checkpoint = CheckpointManager(tmp_path / "checkpoint.json")
    checkpoint.initialize_chapter("chapter", 2)
    checkpoint.mark_segment_complete("chapter", 0)

    generated = []
    job = ProductionJob(
        chapter="chapter",
        segments_total=2,
        output_dir=output_dir,
        checkpoint=checkpoint,
    )

    def producer(segment_number, temp_path):
        generated.append(segment_number)
        temp_path.write_bytes(b"valid")

    job.run(producer)
    assert generated == [0, 1]


def test_failed_temp_artifact_never_replaces_final(tmp_path):
    output_dir = tmp_path / "chunks"
    checkpoint = CheckpointManager(tmp_path / "checkpoint.json")
    job = ProductionJob(
        chapter="chapter",
        segments_total=1,
        output_dir=output_dir,
        checkpoint=checkpoint,
    )

    def bad_producer(_segment_number, temp_path):
        temp_path.write_bytes(b"")

    try:
        job.run(bad_producer)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected validation failure")

    assert not job.artifact_path(0).exists()
    assert not checkpoint.is_segment_complete("chapter", 0)
