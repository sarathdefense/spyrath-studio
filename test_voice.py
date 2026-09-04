from pathlib import Path

from spyrath.providers.tts import ChatterboxTTSProvider
from spyrath.providers.tts.base import TTSRequest

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

provider = ChatterboxTTSProvider()

request = TTSRequest(
    text="""
Hello, I'm Sarath Vaddi.

Machine learning can look complicated because there are so many algorithms.

In this video, I'll explain the most important machine learning algorithms
in simple language.
""",
    voice_reference=Path("assets/sarath_voice_sample.wav"),
    output_path=Path("output/sarath_test.wav"),
)

print("Generating Sarath voice test...")

result = provider.synthesize(request)

print("Done!")
print(f"Audio: {result.output_path}")
print(f"Provider: {result.provider}")
print(f"Details: {result.metadata}")