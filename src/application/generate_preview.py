"""Application service: generates a short representative preview clip (§19)
that respects the same language/voice/style/advanced parameters the full
generation would use, without running the whole pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from domain.narration import NarrationSettings
from infrastructure.tts.synthesizer import SpeechRequest, SpeechSynthesizer

_PREVIEW_TEXT = {
    "pt": (
        "Esta é uma prévia da narração. Ela usa o mesmo idioma, a mesma voz "
        "e o mesmo estilo que serão aplicados ao seu audiobook completo."
    ),
    "en": (
        "This is a preview of the narration. It uses the same language, "
        "voice, and style that will be applied to your full audiobook."
    ),
}


@dataclass
class PreviewResult:
    audio_path: Path
    duration_seconds: float


class GeneratePreviewService:
    def __init__(self, synthesizer: SpeechSynthesizer, workspace_dir: Path) -> None:
        self._synthesizer = synthesizer
        self._workspace_dir = workspace_dir

    def generate(self, settings: NarrationSettings, custom_text: str | None = None) -> PreviewResult:
        text = custom_text or _PREVIEW_TEXT[settings.language.value]
        segment = self._synthesizer.synthesize(SpeechRequest(text=text, settings=settings))

        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._workspace_dir / "preview.wav"
        segment.save(output_path)
        return PreviewResult(audio_path=output_path, duration_seconds=segment.duration_seconds)
