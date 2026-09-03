from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from spyrath.project import ProjectChapter


@dataclass(frozen=True)
class ManuscriptPlan:
    chapters: tuple[ProjectChapter, ...]
    source_name: str | None = None

    @property
    def segment_count(self) -> int:
        return sum(len(chapter.texts) for chapter in self.chapters)


def parse_manuscript(
    text: str,
    *,
    source_name: str | None = None,
    max_segment_chars: int = 1400,
) -> ManuscriptPlan:
    """Convert plain text/Markdown into deterministic narration chapters.

    Markdown H1/H2 headings create chapter boundaries. If no headings exist,
    the manuscript becomes a single ``chapter_01``. Long paragraphs are split
    into TTS-friendly sentence groups without changing their order.
    """

    if max_segment_chars < 200:
        raise ValueError("max_segment_chars must be at least 200")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("Manuscript is empty")

    heading_re = re.compile(r"^#{1,2}\s+(.+?)\s*$")
    sections: list[tuple[str | None, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    found_heading = False

    def flush() -> None:
        nonlocal current_lines
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_title, [body]))
        current_lines = []

    for line in normalized.split("\n"):
        match = heading_re.match(line.strip())
        if match:
            found_heading = True
            flush()
            current_title = match.group(1).strip()
        else:
            current_lines.append(line)
    flush()

    if not found_heading:
        sections = [(None, [normalized])]
    if not sections:
        raise ValueError("Manuscript contains headings but no narratable text")

    chapters: list[ProjectChapter] = []
    used_ids: set[str] = set()
    for index, (title, bodies) in enumerate(sections, start=1):
        chapter_id = _unique_chapter_id(title, index, used_ids)
        segments: list[str] = []
        for body in bodies:
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
            for paragraph in paragraphs:
                segments.extend(_split_text(paragraph, max_segment_chars))
        if segments:
            chapters.append(ProjectChapter.from_texts(chapter_id, segments))

    if not chapters:
        raise ValueError("Manuscript contains no narratable text")
    return ManuscriptPlan(chapters=tuple(chapters), source_name=source_name)


def read_manuscript(path: str | Path, *, max_segment_chars: int = 1400) -> ManuscriptPlan:
    source = Path(path)
    if source.suffix.lower() not in {".txt", ".md", ".markdown"}:
        raise ValueError("Milestone 9 manuscript upload supports .txt and .md files")
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Manuscript must be UTF-8 text") from exc
    return parse_manuscript(text, source_name=source.name, max_segment_chars=max_segment_chars)


def _unique_chapter_id(title: str | None, index: int, used: set[str]) -> str:
    if title:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", title.strip()).strip("_").lower()
    else:
        slug = ""
    base = f"{index:02d}_{slug}" if slug else f"chapter_{index:02d}"
    candidate = base[:80]
    counter = 2
    while candidate in used:
        suffix = f"_{counter}"
        candidate = f"{base[:80-len(suffix)]}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def _split_text(text: str, max_chars: int) -> list[str]:
    value = " ".join(text.split())
    if len(value) <= max_chars:
        return [value]

    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", value) if item.strip()]
    if len(sentences) == 1:
        return _hard_wrap(value, max_chars)

    result: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                result.append(current)
                current = ""
            result.extend(_hard_wrap(sentence, max_chars))
            continue
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            result.append(current)
            current = sentence
    if current:
        result.append(current)
    return result


def _hard_wrap(text: str, max_chars: int) -> list[str]:
    words = text.split()
    result: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and length + extra > max_chars:
            result.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        result.append(" ".join(current))
    return result
