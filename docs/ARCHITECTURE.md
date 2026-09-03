# Spyrath Studio - Architecture

## Overview

Spyrath Studio is an orchestration layer for long-form AI presenter production.

The core principle is separation of concerns:

- Content processing
- Voice generation
- Checkpointing and recovery
- Storage
- Presenter generation
- Media assembly

Underlying AI models are treated as replaceable providers rather than being tightly coupled to Spyrath Studio.

---

## High-Level Architecture

```text
                    SPYRATH STUDIO

 Content        Voice Reference       Presenter Image
    │                 │                     │
    └─────────────────┼─────────────────────┘
                      ↓
              Content Processor
                      ↓
              Narration Pipeline
                      ↓
                TTS Provider
                      ↓
             Generated Narration
                      ↓
              Checkpoint Manager
                      ↓
              Presenter Provider
                      ↓
              Generated Videos
                      ↓
               Media Assembler
                      ↓
                 Final MP4
```

---

## 1. Content Processor

The Content Processor prepares long-form material for AI narration.

Responsibilities:

- Load one or multiple text files
- Preserve chapter ordering
- Normalize text
- Prepare text for natural narration
- Split large chapters into TTS-safe segments
- Avoid unnecessary sentence breaks
- Preserve natural paragraph flow

Example:

```text
Chapter
   ↓
Prepare narration
   ↓
Split for TTS
   ↓
segment_000
segment_001
segment_002
```

---

## 2. TTS Provider

Spyrath Studio should not depend permanently on a single voice-generation model.

Instead, voice models implement a common provider interface.

Conceptually:

```python
class TTSProvider:

    def generate(self, text, voice_reference):
        raise NotImplementedError
```

The initial provider is:

```text
ChatterboxProvider
```

Future TTS models can be added without changing the main Spyrath workflow.

---

## 3. Narration Pipeline

The Narration Pipeline coordinates long-form speech generation.

Responsibilities:

- Process chapters sequentially
- Generate individual audio segments
- Save every completed segment immediately
- Combine segments into chapter audio
- Detect existing completed work
- Skip valid completed segments
- Resume generation after interruption

Example:

```text
Chapter 6

segment_000.wav  ✅
segment_001.wav  ✅
segment_002.wav  ✅
segment_003.wav  ⏳
segment_004.wav
segment_005.wav
```

If execution stops while generating `segment_003.wav`, the next run should preserve segments 0–2 and continue from the unfinished work.

---

## 4. Checkpoint Manager

Checkpointing is a core Spyrath Studio capability.

Long-running generative AI workloads can take hours, so completed work must not be lost because of a runtime restart or network interruption.

The Checkpoint Manager tracks:

- Completed segments
- Completed chapters
- Failed segments
- Generation configuration
- Provider information
- Output locations
- Production status

Example:

```json
{
  "chapter": "chapter_06",
  "segments_total": 6,
  "segments_completed": 3,
  "chapter_complete": false
}
```

### Resume Workflow

```text
Start Spyrath
      ↓
Read production state
      ↓
Discover existing artifacts
      ↓
Validate completed outputs
      ↓
Skip completed work
      ↓
Find first unfinished unit
      ↓
Resume generation
```

---

## 5. Storage Layer

Spyrath Studio separates temporary runtime resources from persistent production storage.

Core principle:

```text
Runtime = Disposable
Storage = Persistent
```

Initial storage implementations may include:

```text
LocalStorage
GoogleDriveStorage
```

Future implementations may include:

```text
S3Storage
GCSStorage
AzureBlobStorage
```

Storage responsibilities include:

- Artifact paths
- Directory creation
- Safe writes
- File existence checks
- Output validation
- Checkpoint persistence

No critical production state should exist only in temporary runtime memory.

---

## 6. Runtime Recovery

Spyrath Studio assumes execution environments can fail.

Examples include:

- Google Colab runtime reset
- GPU session expiration
- Network interruption
- Process crash
- Out-of-memory termination
- Notebook restart

Spyrath should therefore be capable of reconstructing production state from persistent storage and continuing from the last valid checkpoint.

---

## 7. Provider Architecture

AI models are adapters behind stable Spyrath interfaces.

### Voice Providers

```text
TTSProvider
    │
    └── ChatterboxProvider
```

### Presenter Providers

```text
PresenterProvider
    │
    └── SadTalkerProvider
```

This architecture allows models to be replaced as better technologies become available.

For example:

```python
studio = Studio(
    tts_provider="chatterbox",
    presenter_provider="sadtalker"
)
```

A future configuration could use different providers without changing the rest of the production pipeline.

---

## 8. Presenter Pipeline

The Presenter Pipeline consumes:

```text
Presenter Image
       +
Generated Narration
       ↓
Presenter Provider
       ↓
Talking Presenter Video
```

Presenter rendering should normally begin only after narration has been generated and validated.

This prevents expensive GPU video rendering from being performed against incorrect or unapproved narration.

---

## 9. Media Assembly

The Media Assembler creates production-ready output.

Responsibilities:

- Combine narration segments
- Combine chapter audio
- Combine presenter video segments
- Synchronize audio and video
- Normalize media formats
- Produce browser-compatible video
- Export final MP4
- Validate final duration

Preferred final video format:

```text
Video: H.264
Pixel Format: yuv420p
Audio: AAC
Container: MP4
```

---

## 10. Project Workspace

A Spyrath production project could use:

```text
project/
│
├── input/
│   └── chapters/
│
├── assets/
│   ├── voice.wav
│   └── presenter.png
│
├── work/
│   ├── audio_segments/
│   ├── chapter_audio/
│   └── video_segments/
│
├── output/
│   └── final.mp4
│
└── spyrath.yaml
```

---

## 11. Proposed Python Package

```text
spyrath/
│
├── cli/
│
├── pipeline/
│   ├── content.py
│   ├── narration.py
│   ├── presenter.py
│   └── production.py
│
├── providers/
│   ├── tts/
│   └── video/
│
├── checkpoint/
│
├── storage/
│
└── media/
```

---

## 12. Reliability Principles

Spyrath Studio follows these principles:

1. Never regenerate valid completed work.
2. Persist expensive outputs immediately.
3. Make runtime recovery automatic.
4. Separate production state from runtime state.
5. Validate inputs before expensive generation.
6. Keep AI model providers replaceable.
7. Treat long-form generation as a workflow rather than a single inference call.

---

## 13. Safety and Consent

Spyrath Studio must not assume permission to clone a person's voice or likeness.

Users must own or have explicit authorization to use:

- Voice reference recordings
- Presenter images
- Personal likenesses
- Source content

Consent checks should be incorporated into the CLI and API before generation begins.

Personal voice recordings, presenter images, private content, generated books, and model checkpoints should not be included in the public Spyrath Studio repository.

---

## v0.1 Architecture Boundary

Spyrath Studio v0.1 focuses first on the narration pipeline:

```text
Content
   ↓
Content Processing
   ↓
TTS Provider
   ↓
Segment Generation
   ↓
Checkpoint / Resume
   ↓
Chapter Audio
   ↓
Final Narration
```

Presenter generation and complete video assembly will follow after the narration pipeline has been fully validated.

---

## Long-Term Direction

Spyrath Studio should evolve from a working AI narration pipeline into a provider-independent AI presenter production platform.

The goal is to make a complex workflow feel simple:

```text
Your Voice
+
Your Presenter
+
Your Content
      ↓
Spyrath Studio
      ↓
Your AI-Presented Video
```

## Studio application boundary (Milestone 9)

The Studio application layer owns browser/API concerns only: project registration, durable input assets, manuscript parsing, background job submission, status, and downloads. Provider/model code remains behind the existing orchestration interfaces.

`RealOrchestratorFactory` is the composition root. It constructs one checkpoint manager and the concrete Chatterbox, audio-preparation, SadTalker, and FFmpeg engines for each project. This keeps HTTP code independent from GPU/media implementation details and allows tests to replace the composition root with fake orchestrators.
