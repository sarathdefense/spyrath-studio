# Spyrath Studio - Product Specification

## Vision

Spyrath Studio is an AI presenter production engine that transforms long-form content into narrated presenter videos using an authorized voice reference and presenter image.

## Tagline

Your Voice. Your Presence. Your Content.

## Problem

Creating long-form AI presenter videos currently requires combining multiple tools, managing GPU environments, splitting content manually, recovering from failed jobs, tracking intermediate files, and assembling final media.

Long-running AI generation jobs are especially difficult because notebook runtimes can disconnect or reset, causing users to lose progress.

Spyrath Studio simplifies and orchestrates this complete workflow.

## Core Workflow

Content
+
Authorized Voice Reference
+
Presenter Image
↓
Content Processing
↓
Voice Generation
↓
Checkpoint / Resume
↓
Presenter Animation
↓
Media Assembly
↓
Final Presenter Video

## Primary Use Cases

- Books and audiobooks
- Online courses
- Training material
- Tutorials
- Technical education
- Product demonstrations
- Internal corporate learning
- Long-form narrated presentations

## v0.1 Scope

The first release focuses on long-form narration generation.

### Features

- Multiple input text files
- Chapter-aware processing
- Automatic text segmentation
- Voice-conditioned speech generation
- Segment-level checkpointing
- Chapter-level checkpointing
- Resume after interruption
- GPU detection
- Local and persistent storage support
- Final chapter audio assembly
- Final audiobook assembly

## Future Releases

### v0.2
Presenter image animation and video generation.

### v0.3
Automatic audio/video assembly and final MP4 export.

### v0.4
Web interface and simplified project management.

### v1.0
Complete AI presenter production studio.

## Architecture Principle

Spyrath Studio is an orchestration platform.

Voice and video models are providers rather than hard-coded components.

Examples:

- TTS Provider: Chatterbox
- Video Provider: SadTalker
- Future providers can be added without changing the main user workflow.

## Reliability

Long-running generative AI workflows must be resumable.

Spyrath Studio should:

- Save every completed generation segment
- Detect previously completed work
- Resume from the first unfinished segment
- Persist production artifacts outside temporary runtimes
- Recover cleanly after runtime resets
- Avoid repeating expensive completed generations

## Developer Experience

Future installation:

```bash
pip install spyrath

Example:
spyrath generate \
  --voice voice.wav \
  --image presenter.png \
  --input ./chapters \
  --output ./production

Python API:
from spyrath import Studio

studio = Studio(
    voice="voice.wav",
    presenter="presenter.png"
)

studio.generate("./chapters")


## Safety and Consent

Spyrath Studio is intended only for voices, images, and likenesses that users own or have explicit authorization to use.

Voice cloning and presenter generation should require clear user consent.

The project should never include private voice samples, personal presenter images, generated books, or model checkpoints in the public repository.

## Project Status

Spyrath Studio v0.1 is currently being developed and validated using a real long-form book-to-presenter production workflow.

The first milestone is completing and validating the full production pipeline before extracting it into the reusable Spyrath engine.
