# Spyrath Studio

### Your Voice. Your Presence. Your Content.

**Spyrath Studio** is an AI presenter production engine designed to transform long-form content into narrated presenter videos using an authorized voice reference and presenter image.

Instead of manually connecting multiple AI tools, managing long-running GPU jobs, recovering failed generations, and assembling media files, Spyrath Studio aims to orchestrate the complete production workflow.

> **Built for long-form AI production, not just short demos.**

---

## What Can Spyrath Studio Do?

Spyrath Studio is being designed to turn:

```text
Your Content
     +
Your Voice
     +
Your Presenter
     ↓
Spyrath Studio
     ↓
AI-Presented Video
```

Potential use cases include:

- Books and audiobooks
- Online courses
- Technical tutorials
- Training material
- Educational content
- Product demonstrations
- Corporate learning
- Long-form presentations

---

## Why Spyrath Studio?

Generating a short AI voice or avatar demo is relatively easy.

Generating an entire book, course, or training program reliably is a different problem.

Long-running AI workflows introduce challenges such as:

- GPU runtime interruptions
- Notebook disconnects
- Large-text processing
- Voice consistency
- Dependency conflicts
- Failed generations
- Expensive regeneration
- Intermediate artifact management
- Audio/video synchronization
- Production recovery

Spyrath Studio is being designed around these real-world problems.

---

## Core Architecture

```text
                 SPYRATH STUDIO

 Content       Voice Reference      Presenter Image
    │                │                    │
    └────────────────┼────────────────────┘
                     ↓
             Content Processor
                     ↓
             Narration Pipeline
                     ↓
                TTS Provider
                     ↓
              Checkpointing
                     ↓
              Chapter Audio
                     ↓
            Presenter Provider
                     ↓
               Video Segments
                     ↓
              Media Assembly
                     ↓
                 Final MP4
```

---

## Reliability First

One of the core design principles of Spyrath Studio is:

> **Never regenerate expensive work that has already completed successfully.**

Long-running generation jobs are divided into smaller checkpointed units.

If generation stops halfway through a production, Spyrath should be able to discover completed work and continue from the first unfinished unit.

```text
Chapter 6

segment_000.wav  ✅
segment_001.wav  ✅
segment_002.wav  ✅
segment_003.wav  ⏳
segment_004.wav
segment_005.wav
```

After recovery:

```text
Skip 000
Skip 001
Skip 002
Resume 003
```

---

## Provider-Based Architecture

Spyrath Studio is intended to be an orchestration platform rather than a wrapper around one AI model.

AI capabilities are implemented through providers.

```text
TTSProvider
    └── ChatterboxProvider

PresenterProvider
    └── SadTalkerProvider
```

This allows newer or better models to be integrated without redesigning the entire production workflow.

---

## Planned Developer Experience

The goal is to eventually make installation as simple as:

```bash
pip install spyrath
```

Then:

```bash
spyrath generate \
    --voice voice.wav \
    --image presenter.png \
    --input ./chapters \
    --output ./production
```

Python applications could use Spyrath directly:

```python
from spyrath import Studio

studio = Studio(
    voice="voice.wav",
    presenter="presenter.png"
)

studio.generate("./chapters")
```

> **Note:** These APIs represent the planned developer experience and are not yet available in the current development version.

---


## Chatterbox TTS Provider

Spyrath can use Resemble AI's Chatterbox as an optional local TTS provider.
The core package does not import Chatterbox or Torch until this provider is
actually used.

Install the optional provider dependencies:

```bash
pip install -e ".[chatterbox]"
```

Create the provider using the approved reference-production defaults:

```python
from spyrath.providers.tts import ChatterboxTTSProvider

provider = ChatterboxTTSProvider()  # auto-selects CUDA, MPS, or CPU
```

The current English provider uses voice-conditioned synthesis and therefore
expects an authorized voice-reference WAV. Its default generation settings are
`exaggeration=0.3` and `cfg_weight=0.5`, matching the Spyrath reference book
production. Model loading is lazy and the loaded model is reused across
segments.

When used through `NarrationEngine`, generated WAVs still follow Spyrath's
reliability contract: temporary output, validation, atomic promotion, and
resume from already-valid artifacts.

## Roadmap

### v0.1 - Narration Engine

- Long-form content processing
- Automatic text segmentation
- Voice-conditioned narration
- Segment checkpointing
- Chapter checkpointing
- Runtime recovery
- Persistent storage
- Final narration assembly

### v0.2 - Presenter Engine

- Presenter provider interface
- Image-driven presenter generation
- Audio-to-presenter synchronization
- Video checkpointing

### v0.3 - Production Engine

- Chapter video assembly
- Audio/video normalization
- Final MP4 generation
- Production validation

### v0.4 - Spyrath Studio UI

- Project creation
- Asset management
- Production monitoring
- Resume and retry controls
- Video preview

### v1.0 - Complete AI Presenter Studio

End-to-end AI presenter production from content to finished video.

---

## Project Status

🚧 **Spyrath Studio is currently under active development.**

The architecture is being validated against a real long-form production workflow before the reusable engine is released.

Current focus:

```text
Long-form Content
        ↓
Voice Generation
        ↓
Checkpoint / Resume
        ↓
Chapter Narration
        ↓
Presenter Generation
        ↓
Final Video
```

---

## Safety and Responsible Use

Spyrath Studio is intended for authorized and consensual AI media generation.

Users should only use voices, images, likenesses, and source material that they own or have explicit permission to use.

Spyrath Studio should not be used to impersonate individuals, misrepresent identity, or create deceptive media.

Personal voice recordings, presenter images, private manuscripts, and generated production artifacts should remain outside source control.

---

## Documentation

Detailed design documentation is available in:

- `docs/PRODUCT_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/LESSONS_LEARNED.md`

---

## Creator

**Spyrath Studio** was created by **Sarath Vaddi**.

The project grew out of hands-on experimentation with long-form AI voice generation, presenter animation, checkpoint recovery, and automated media production.

The goal is to make AI presenter creation reliable, reusable, and accessible to developers, educators, authors, and content creators.

---

## Contributing

Spyrath Studio is currently in early private development.

Contribution guidelines will be published when the project reaches its first public development release.

---

## License

Licensing is currently under review while dependencies and model-provider licenses are evaluated.

---

**Spyrath Studio**  
Created by **Sarath Vaddi**

*Your Voice. Your Presence. Your Content.*

## Milestone 2: Narration Engine

Spyrath now includes a provider-neutral narration layer:

- `TTSProvider` defines the text-to-speech provider contract.
- `TTSRequest` and `TTSResult` carry provider inputs and outputs.
- `NarrationPlan` defines independently resumable narration segments.
- `NarrationEngine` generates WAV artifacts through the selected provider.
- Existing valid narration is discovered and skipped after restart.
- Missing or invalid narration is regenerated automatically.
- Generation uses the Milestone 1 `.tmp -> validate -> atomic rename` production path.

The next provider implementation can wrap Chatterbox without coupling the core
pipeline to Chatterbox-specific APIs or dependencies.

## Milestone 4: Audio Segmentation + Chapter Assembly

Spyrath now prepares narration for presenter generation without repeating valid work:

- `ChapterAssembler` concatenates compatible PCM WAV narration segments into one chapter WAV.
- Chapter assembly uses `.tmp -> validate -> atomic rename` and a source fingerprint manifest.
- `AudioSegmenter` splits a chapter WAV into fixed-duration chunks (30 seconds by default).
- Every chunk is independently validated and checkpointed through the production engine.
- Restarting after an interruption skips valid chunks and regenerates only missing or corrupt ones.
- If the chapter source changes, stale chunks are invalidated before regeneration.
- `AudioPreparationEngine` provides the end-to-end `narration segments -> chapter WAV -> presenter chunks` workflow.

Example:

```python
from spyrath.checkpoint import CheckpointManager
from spyrath.media import AudioPreparationEngine

engine = AudioPreparationEngine(
    checkpoint=CheckpointManager("production/checkpoint.json"),
    target_duration_seconds=30,
)

result = engine.prepare(
    chapter="chapter_01",
    narration_segments=["segment_000.wav", "segment_001.wav"],
    chapter_output_path="chapters/chapter_01.wav",
    chunks_output_dir="chunks/chapter_01",
)

print(result.segmentation.progress.completed, result.segmentation.chunks_total)
```

The current implementation deliberately targets uncompressed PCM WAV so the core media
pipeline stays dependency-free. FFmpeg-backed transcoding/validation can be added as a
media adapter without changing the checkpoint or orchestration contracts.

## Milestone 5: Presenter Video Provider

Spyrath now has a provider-neutral presenter-video layer and a SadTalker adapter:

- `VideoProvider`, `VideoRequest`, and `VideoResult` define the image + audio -> MP4 provider contract.
- `PresenterProductionEngine` renders independently resumable presenter chunks through the Milestone 1 production engine.
- Existing valid MP4 chunks are reconciled from disk and skipped after restart.
- Missing or corrupt video chunks are regenerated through `.tmp -> validate -> atomic rename`.
- A manifest fingerprints the presenter image, every audio chunk, and the provider configuration so stale videos are invalidated when an input changes.
- `SadTalkerProvider` wraps a local SadTalker checkout through its `inference.py` command without coupling Spyrath's core orchestration to SadTalker internals.
- The core MP4 validator is dependency-free and intentionally lightweight; a later FFmpeg adapter can add stream-level validation.

The milestone regression test reproduces the real long-form recovery case: 98 of 107 presenter chunks exist, Spyrath restarts, and generation resumes at chunk index 98 (human-facing 99/107) without regenerating the first 98.

Example:

```python
from pathlib import Path

from spyrath.checkpoint import CheckpointManager
from spyrath.pipeline import PresenterProductionEngine
from spyrath.providers.video import SadTalkerConfig, SadTalkerProvider

provider = SadTalkerProvider(
    SadTalkerConfig(
        repository_dir=Path("/opt/SadTalker"),
        checkpoint_dir=Path("/opt/SadTalker/checkpoints"),
        preprocess="full",
        still=True,
    )
)

engine = PresenterProductionEngine(
    provider=provider,
    checkpoint=CheckpointManager("production/checkpoint.json"),
)

result = engine.render(
    chapter="chapter_01",
    audio_chunks=sorted(Path("chunks/chapter_01").glob("chunk_*.wav")),
    presenter_image="assets/presenter.png",
    output_dir="presenter/chapter_01",
)

print(result.progress.completed, result.chunks_total)
```

## Milestone 6 — Video Assembly + Final H.264 Export

Spyrath can now assemble validated presenter chunks into reusable chapter videos and produce a delivery-ready final MP4. The final export uses FFmpeg with H.264 (`libx264`), AAC audio, `yuv420p`, configurable CRF/preset, and `+faststart` by default.

The assembly layer validates every input with ffprobe, fingerprints source artifacts, reuses unchanged chapter/final outputs, rebuilds stale outputs, writes through temporary files, validates the result, and atomically promotes it only after success. This preserves the reliability-first behavior used throughout the pipeline.

```python
from spyrath.media.video import ExportConfig, FFmpegMedia
from spyrath.pipeline.export import VideoAssemblyEngine

media = FFmpegMedia(ExportConfig(crf=18, preset="fast"))
engine = VideoAssemblyEngine(media)
result = engine.export_final(
    chapters={"chapter_01": chapter_01_chunks, "chapter_02": chapter_02_chunks},
    chapter_output_dir="output/chapter_videos",
    final_path="output/final/book_presenter.mp4",
)
print(result.probe.duration, result.probe.video_codec, result.probe.audio_codec)
```

FFmpeg and ffprobe must be installed on the production worker. They remain external runtime tools rather than Python package dependencies.

## Project Orchestration

Milestone 7 connects the reliability-first production components into one persistent Spyrath project. `ProjectOrchestrator.run()` and `resume()` coordinate narration, chapter audio preparation, presenter generation, and final H.264 export while writing an atomic `project.json` state file.

The orchestrator records each stage as `pending`, `running`, `completed`, or `failed`, together with its input fingerprint and produced artifacts. Completed stages are reused only when their inputs still match and their artifacts still exist. If an input changes or an artifact disappears, that stage and all dependent downstream stages are rerun. A failure is persisted before it is surfaced, so restarting the process can resume from the failed stage without rerunning earlier valid work.

```text
Project
  -> Narration
  -> Audio Preparation
  -> Presenter Video
  -> Final H.264 Export
  -> Ready
```

This is the orchestration layer intended to sit behind the future Spyrath Studio dashboard and job API.

## Milestone 8: Project API + Studio Dashboard Foundation

Milestone 8 exposes the persistent project orchestrator through a framework-thin application service, a REST API, and an initial Studio dashboard.

Install the optional web dependencies:

```bash
pip install -e ".[studio]"
```

The API surface now includes:

- `GET /api/health`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `POST /api/projects/{project_id}/run`
- `POST /api/projects/{project_id}/resume`
- `GET /api/projects/{project_id}/download`

`StudioService` runs expensive project production on a worker thread and returns immediately to the API. The durable `project.json` written by the Milestone 7 orchestrator remains the source of truth, so process restarts do not erase completed stage state.

The dashboard at `/` polls project status and displays overall progress, per-stage state, failures, Resume Production, and the final video download when export is complete.

Example application wiring:

```python
from spyrath.studio import ProjectRepository, StudioService, create_app

repository = ProjectRepository("./spyrath-projects")
service = StudioService(
    repository=repository,
    orchestrator_factory=build_orchestrator,  # application-specific provider wiring
)
app = create_app(service)
```

Run with Uvicorn after exposing the configured `app` from your application module:

```bash
uvicorn my_spyrath_app:app --reload
```

Provider/model construction deliberately remains outside the HTTP layer. This keeps API concerns separate from Chatterbox, SadTalker, FFmpeg, GPU provisioning, and future remote-job infrastructure.

## Milestone 9: Real Studio Application Wiring + Project Creation UI

Milestone 9 turns the Milestone 8 dashboard into a real project entry point and wires Studio projects to the production providers from Milestones 3, 5, and 6.

### Browser project creation

The dashboard now includes **+ New Project**. A user can upload:

- a UTF-8 `.txt` or `.md` manuscript,
- a voice reference (`.wav`, `.mp3`, `.m4a`, `.flac`, or `.ogg`), and
- a presenter image (`.png`, `.jpg`, `.jpeg`, or `.webp`).

Uploaded assets are copied into the project-owned `assets/` directory before the temporary HTTP upload is removed. Project specs therefore reference durable project files rather than browser temp paths.

Markdown `#` and `##` headings become chapters automatically. Plain text becomes one chapter. Long paragraphs are deterministically split into TTS-friendly narration segments while preserving order.

The upload endpoint is:

```text
POST /api/projects/upload
```

The original JSON `POST /api/projects` endpoint remains available for programmatic clients.

### Real production wiring

`spyrath.studio.runtime.RealOrchestratorFactory` connects one Studio project to:

```text
ChatterboxTTSProvider
        ↓
NarrationEngine
        ↓
AudioPreparationEngine
        ↓
SadTalkerProvider
        ↓
PresenterProductionEngine
        ↓
FFmpegMedia / VideoAssemblyEngine
        ↓
Final H.264/AAC video
```

Every project gets its own checkpoint file and production directories while retaining the resume/reconciliation behavior from earlier milestones.

### Runtime configuration

Install the browser/API dependencies:

```bash
pip install -e ".[studio,chatterbox]"
```

Point Spyrath at the proven SadTalker runtime:

```bash
export SPYRATH_SADTALKER_REPO=/path/to/SadTalker
export SPYRATH_SADTALKER_PYTHON=/path/to/python3.10
export SPYRATH_SADTALKER_CHECKPOINTS=/path/to/SadTalker/checkpoints
```

Optional settings:

```bash
export SPYRATH_PROJECTS_ROOT="$HOME/.spyrath/projects"
export SPYRATH_TTS_DEVICE=auto
export SPYRATH_AUDIO_CHUNK_SECONDS=30
export SPYRATH_FFMPEG=ffmpeg
export SPYRATH_FFPROBE=ffprobe
export SPYRATH_MAX_WORKERS=1
```

Start Studio:

```bash
uvicorn spyrath.studio.app:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` and create a project from the browser.

Milestone 9 intentionally does not hide the requirement for a correctly prepared SadTalker runtime. The Studio UI now owns project creation and durable assets; GPU environment/bootstrap automation remains a separate deployment concern.

## Milestone 10 — Production Runtime & GPU Job Execution

Milestone 10 replaces the Studio's process-local background thread bookkeeping with a bounded, durable production runtime designed for expensive GPU work.

### Runtime job lifecycle

Each production request creates a durable job record before execution:

```text
queued → running → succeeded
             └──→ retry/resume → running
             └──→ failed
```

Runtime metadata is stored under the Studio projects root at:

```text
<projects-root>/.runtime/jobs.json
```

Each job records its project, run/resume mode, attempt count, timestamps, status, and last runtime error. Jobs left in `running` by a dead Studio process are marked failed/recoverable during runtime startup; the project artifacts/checkpoints remain intact and can be resumed.

### Bounded workers and retries

`ProductionRuntime` limits concurrent jobs with `SPYRATH_MAX_WORKERS` and prevents the same project from being launched twice at the same time. Failed jobs can automatically retry using the project's existing resumable pipeline.

```bash
export SPYRATH_MAX_WORKERS=1
export SPYRATH_MAX_ATTEMPTS=2
```

The first attempt uses `run()`. Automatic retry uses `resume()` so completed narration, audio, presenter chunks, and assembly artifacts are not intentionally regenerated.

### Production preflight

Before a real production job begins, Spyrath checks the worker environment for:

- SadTalker `inference.py`
- configured SadTalker Python executable
- FFmpeg
- ffprobe
- NVIDIA GPU availability through `nvidia-smi`

GPU enforcement is enabled by default for the production runtime. It can be disabled for development/CPU-only validation:

```bash
export SPYRATH_REQUIRE_GPU=0
```

This setting does not make SadTalker fast on CPU; it only changes the runtime readiness gate.

### Runtime observability API

```text
GET /api/runtime/jobs
GET /api/projects/{project_id}/runtime
```

Project summaries also include the latest `runtime_job`, allowing the Studio UI to show queued/running/retry/failure metadata without treating in-memory threads as the source of truth.

### Reliability contract

Milestone 10 does not replace the artifact-level checkpointing from earlier milestones. It adds a durable execution layer around it:

```text
API request
   ↓
Durable runtime job
   ↓
Preflight
   ↓
Bounded worker
   ↓
ProjectOrchestrator.run()/resume()
   ↓
Artifact validation + checkpoints
```

A worker/runtime failure therefore does not imply that expensive completed media work is lost.

## Milestone 11: Production Studio UI

Milestone 11 turns the Studio dashboard into a production-control surface while keeping the durable M7-M10 execution model underneath it.

Highlights:
- live 2-second status refresh
- real presenter chunk progress (`completed / total`) derived from durable project artifacts
- weighted overall progress while presenter generation is running
- runtime job status, attempts, elapsed time, and surfaced errors
- presenter-image and voice-reference previews
- inline final-video playback plus explicit download
- Run Again / Resume Production controls driven by durable project state
- responsive project cards and a more polished production workspace

New media endpoints:

```text
GET /api/projects/{project_id}/media/presenter
GET /api/projects/{project_id}/media/voice
GET /api/projects/{project_id}/video
```

The UI deliberately does not claim that a running GPU process can be force-cancelled safely. Resume/retry remains checkpoint-safe; cooperative cancellation can be added later at provider boundaries without risking partially written media.

## Milestone 12 — Accounts, Storage & Deployment

Milestone 12 adds the deployment boundary for Spyrath Studio:

- SQLite-backed user/account and project-ownership metadata (`SPYRATH_METADATA_DB`).
- Optional API-key authentication (`SPYRATH_AUTH_ENABLED=1`, header `X-Spyrath-Key`).
- Bootstrap admin credentials via `SPYRATH_BOOTSTRAP_USER`, `SPYRATH_BOOTSTRAP_NAME`, and `SPYRATH_BOOTSTRAP_API_KEY`.
- Per-user project listing and ownership checks when authentication is enabled.
- `ArtifactStorage` abstraction plus path-safe, atomic `LocalArtifactStorage` for durable filesystem deployments; cloud object-storage adapters can implement the same contract later.
- `/api/health` liveness and `/api/ready` deployment-readiness endpoints.
- Non-root Docker image and docker-compose persistent `/data` volume.

Local development remains backward compatible because authentication defaults to disabled. For an authenticated deployment:

```bash
export SPYRATH_AUTH_ENABLED=1
export SPYRATH_METADATA_DB=/data/studio.db
export SPYRATH_BOOTSTRAP_USER=admin
export SPYRATH_BOOTSTRAP_API_KEY='replace-with-a-secret'
uvicorn spyrath.studio.app:app --host 0.0.0.0 --port 8000
```

Clients then send `X-Spyrath-Key: replace-with-a-secret`. Do not commit production API keys to source control.

Container smoke start (CPU/local mode):

```bash
docker compose up --build
```

Production GPU deployment must additionally provide the prepared SadTalker runtime/checkpoints and NVIDIA container/GPU access required by Milestone 10.
