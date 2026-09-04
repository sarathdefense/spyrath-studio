from __future__ import annotations

import argparse
import re
from pathlib import Path

from spyrath.providers.tts import ChatterboxConfig, ChatterboxTTSProvider, TTSRequest


def load_sections(markdown_path: Path) -> list[tuple[str, str]]:
    text = markdown_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^###\s+(\d{3})\s+—\s+(.+?)\n(.*?)(?=^###\s+\d{3}\s+—|\Z)", re.M | re.S)
    sections = []
    for number, title, body in pattern.findall(text):
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        sections.append((f"{number}_{slug}", body.strip()))
    if not sections:
        raise SystemExit(f"No narration sections found in {markdown_path}")
    return sections


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Linear Regression narration with Spyrath Studio.")
    parser.add_argument("--voice-reference", type=Path, required=True)
    parser.add_argument(
        "--script",
        type=Path,
        default=Path("content/linear_regression_5min_script.md"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/linear_regression"),
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "mps", "cpu"),
        default="auto",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    voice_reference = args.voice_reference.expanduser().resolve()
    script_path = args.script.expanduser().resolve()
    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not voice_reference.is_file():
        raise SystemExit(f"Voice reference not found: {voice_reference}")
    if not script_path.is_file():
        raise SystemExit(f"Narration script not found: {script_path}")

    sections = load_sections(script_path)

    provider = ChatterboxTTSProvider(
        ChatterboxConfig(
            device=args.device,
            exaggeration=0.3,
            cfg_weight=0.5,
            require_voice_reference=True,
        )
    )

    print("Spyrath Studio — Linear Regression Explained in 5 Minutes")
    print(f"Device: {provider.device}")
    print(f"Voice reference: {voice_reference}")
    print(f"Sections: {len(sections)}")
    print(f"Output: {output_dir}")

    generated = skipped = 0

    for i, (name, text) in enumerate(sections, 1):
        output_path = output_dir / f"{name}.wav"

        if output_path.is_file() and output_path.stat().st_size > 0 and not args.force:
            print(f"[{i:02d}/{len(sections):02d}] SKIP {output_path}")
            skipped += 1
            continue

        print(f"[{i:02d}/{len(sections):02d}] GEN  {output_path}")
        provider.synthesize(
            TTSRequest(
                text=text,
                output_path=output_path,
                voice_reference=voice_reference,
                language="en-US",
                metadata={
                    "project": "linear-regression-explained-in-5-minutes",
                    "section": name,
                },
            )
        )
        generated += 1

    print(f"\nDone. Generated: {generated}; skipped: {skipped}; total: {len(sections)}")


if __name__ == "__main__":
    main()
