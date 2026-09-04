from pathlib import Path

from spyrath.providers.tts import ChatterboxTTSProvider
from spyrath.providers.tts.base import TTSRequest

SCRIPT_DIR = Path("scripts/ml_youtube")
OUTPUT_DIR = Path("output/ml_youtube")
VOICE = Path("assets/sarath_voice_sample.wav")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

provider = ChatterboxTTSProvider()

files = sorted(SCRIPT_DIR.glob("*.txt"))

print(f"Found {len(files)} narration sections")

for index, script_file in enumerate(files, start=1):
    output_path = OUTPUT_DIR / f"{script_file.stem}.wav"

    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"[{index}/{len(files)}] SKIP {output_path.name}")
        continue

    text = script_file.read_text(encoding="utf-8").strip()

    print(f"[{index}/{len(files)}] Generating {script_file.name}")

    request = TTSRequest(
        text=text,
        voice_reference=VOICE,
        output_path=output_path,
    )

    result = provider.synthesize(request)

    print(f"   -> {result.output_path}")

print("Narration generation complete.")
