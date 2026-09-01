# Spyrath Studio - Lessons Learned

This document captures engineering lessons discovered while building and running the first real-world Spyrath Studio production workflow.

## 1. Long-Running AI Jobs Need Checkpointing

Generating long-form narration can take hours.

A single chapter may contain multiple TTS segments, and individual segments can take several minutes on a GPU.

We learned that generation must be checkpointed at the smallest practical unit.

### Requirement

Save every completed segment immediately.

Never wait until the entire chapter or book is complete before persisting results.

---

## 2. Runtime Environments Are Disposable

Google Colab runtimes can restart, disconnect, or lose their installed Python environment.

During development, runtime resets caused:

- Python variables to disappear
- Loaded AI models to disappear
- Installed packages to disappear
- GPU sessions to reset

### Requirement

Spyrath must assume:

Runtime = disposable.

Persistent storage = source of truth.

---

## 3. Resume Is a Core Feature

After a runtime failure, completed narration segments remained safely stored in persistent storage.

The workflow successfully detected previously completed work and continued from the first unfinished segment.

### Requirement

Spyrath should automatically:

1. Inspect existing production artifacts.
2. Validate completed outputs.
3. Skip completed segments.
4. Resume from the first unfinished segment.
5. Avoid repeating expensive inference.

---

## 4. Dependency Management Is Critical

AI packages can have strict and conflicting dependencies.

Issues encountered included:

- PyTorch and Torchvision version mismatches
- NumPy binary incompatibility
- Missing Chatterbox installation after runtime reset
- CUDA/GPU environment dependencies

### Requirement

Spyrath should provide a tested dependency matrix and automated environment validation.

Before generation starts, Spyrath should verify:

- Python version
- PyTorch version
- Torchvision compatibility
- CUDA availability
- GPU availability
- Required AI providers

---

## 5. Separate Voice Generation From Video Generation

Narration generation and presenter animation are expensive independent operations.

Generating presenter video before approving narration can waste significant GPU time.

### Requirement

The production workflow should be:

Content
→ Narration
→ Review/Validate
→ Presenter Video
→ Final Assembly

---

## 6. Voice Reference Quality Matters

Voice-conditioned TTS depends strongly on the quality of the reference recording.

The reference should contain:

- Clear speech
- Minimal background noise
- Natural pacing
- Consistent volume
- Enough speech for the model to capture voice characteristics

### Requirement

Spyrath should validate voice-reference files before starting large generation jobs.

---

## 7. Long Text Must Be Segmented

Sending very large passages directly to a TTS model is inefficient and unreliable.

Breaking chapters into natural segments improved manageability and made checkpointing possible.

### Requirement

Spyrath should automatically segment long-form content while preserving sentence and paragraph boundaries.

---

## 8. Expensive Operations Must Be Observable

A user needs to know exactly where a long-running production stands.

Useful progress information includes:

- Current chapter
- Total chapters
- Current segment
- Total segments
- Completed chapters
- Elapsed generation time
- Resume status

### Requirement

Spyrath should provide clear progress reporting for CLI, notebook, and future UI environments.

---

## 9. Personal Assets Must Stay Outside Source Control

Voice recordings, presenter photographs, book manuscripts, generated audio, and generated video should not be committed to the public repository.

### Requirement

Spyrath projects should separate:

Code
from
User Assets
from
Generated Artifacts

The default `.gitignore` should protect these assets.

---

## 10. The First Production Run Is the Reference Test

Spyrath Studio is being designed from a real long-form production workflow rather than a short demonstration.

The first production run validates:

- Long-form text processing
- Voice-conditioned generation
- Segment checkpointing
- Chapter assembly
- Runtime recovery
- Persistent storage
- Presenter generation
- Final media assembly

Problems discovered during this production should become automated protections or features in Spyrath Studio.

---

## Guiding Engineering Principle

If an expensive operation has already completed successfully, Spyrath should never require the user to perform it again unnecessarily.
