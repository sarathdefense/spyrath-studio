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
