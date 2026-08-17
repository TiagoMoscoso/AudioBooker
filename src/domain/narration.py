"""Domain model for narration configuration: language, style, and voice
reference. Only Portuguese and English are supported — no auto-detection, no
regional variants (see AUDIOBOOKER_SPECS.md §5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class NarrationLanguage(Enum):
    PORTUGUESE = "pt"
    ENGLISH = "en"


class NarrationStyle(Enum):
    NATURAL = "natural"
    CALM = "calmo"
    EXPRESSIVE = "expressivo"
    DRAMATIC = "dramatico"


@dataclass(frozen=True)
class StylePreset:
    """All Chatterbox generation parameters a style preset controls.
    `repetition_penalty` differs between the English and multilingual
    models' own documented defaults (1.2 vs 2.0), so the preset carries both
    and ChatterboxSpeechSynthesizer picks the language-appropriate one."""

    exaggeration: float
    cfg_weight: float
    temperature: float
    repetition_penalty_en: float
    repetition_penalty_multi: float
    min_p: float
    top_p: float


# Each preset maps to every parameter Chatterbox's generate() actually
# documents (see README "Original Chatterbox Tips" + the installed package's
# real signature). Priority order per spec §20 is naturalidade >
# estabilidade > clareza > consistência > teatralidade, so NATURAL stays at
# the library's own documented defaults; CALM nudges temperature down for a
# steadier delivery (pairs with its lower exaggeration/higher cfg_weight);
# EXPRESSIVE/DRAMATIC nudge it up for more variability. repetition_penalty/
# min_p/top_p stay at library defaults across every preset — there is no
# evidence-based tuning for them yet, and repetition_penalty is reserved as
# the retry ladder's stability lever instead (infrastructure/tts/
# reliable_synthesizer.py).
_STYLE_PRESETS: dict[NarrationStyle, StylePreset] = {
    NarrationStyle.NATURAL: StylePreset(0.5, 0.5, 0.8, 1.2, 2.0, 0.05, 1.0),
    NarrationStyle.CALM: StylePreset(0.35, 0.6, 0.7, 1.2, 2.0, 0.05, 1.0),
    NarrationStyle.EXPRESSIVE: StylePreset(0.65, 0.4, 0.9, 1.2, 2.0, 0.05, 1.0),
    NarrationStyle.DRAMATIC: StylePreset(0.8, 0.3, 1.0, 1.2, 2.0, 0.05, 1.0),
}


@dataclass(frozen=True)
class VoiceReference:
    """An optional voice-cloning reference clip, used solely through
    Chatterbox's own audio_prompt_path mechanism (§18) — no parallel cloning
    pipeline."""

    name: str
    path: Path
    duration_seconds: float | None = None


@dataclass(frozen=True)
class NarrationSettings:
    language: NarrationLanguage
    style: NarrationStyle = NarrationStyle.NATURAL
    voice_reference: VoiceReference | None = None
    exaggeration: float = 0.5
    cfg_weight: float = 0.5
    # Left at the library's own documented defaults unless a style preset
    # resolves them differently via with_style() — see StylePreset above.
    temperature: float = 0.8
    repetition_penalty: float = 1.2
    min_p: float = 0.05
    top_p: float = 1.0

    @staticmethod
    def preset_params(style: NarrationStyle) -> tuple[float, float]:
        """Returns (exaggeration, cfg_weight) for a style preset. UI code
        calls this when the user changes the preset selector, then the
        "Avançado" sliders may further override the result."""
        preset = _STYLE_PRESETS[style]
        return preset.exaggeration, preset.cfg_weight

    def with_style(self, style: NarrationStyle) -> "NarrationSettings":
        preset = _STYLE_PRESETS[style]
        repetition_penalty = (
            preset.repetition_penalty_en
            if self.language == NarrationLanguage.ENGLISH
            else preset.repetition_penalty_multi
        )
        return NarrationSettings(
            language=self.language,
            style=style,
            voice_reference=self.voice_reference,
            exaggeration=preset.exaggeration,
            cfg_weight=preset.cfg_weight,
            temperature=preset.temperature,
            repetition_penalty=repetition_penalty,
            min_p=preset.min_p,
            top_p=preset.top_p,
        )

    def to_dict(self) -> dict:
        """Serializes to a plain dict for the generation manifest, so an
        interrupted session can resume with the exact same narration
        configuration after a full app restart (§26)."""
        return {
            "language": self.language.value,
            "style": self.style.value,
            "voice_reference_path": str(self.voice_reference.path) if self.voice_reference else None,
            "voice_reference_name": self.voice_reference.name if self.voice_reference else None,
            "exaggeration": self.exaggeration,
            "cfg_weight": self.cfg_weight,
            "temperature": self.temperature,
            "repetition_penalty": self.repetition_penalty,
            "min_p": self.min_p,
            "top_p": self.top_p,
        }

    @staticmethod
    def from_dict(data: dict) -> "NarrationSettings":
        voice_reference = None
        if data.get("voice_reference_path"):
            voice_reference = VoiceReference(
                name=data.get("voice_reference_name") or Path(data["voice_reference_path"]).name,
                path=Path(data["voice_reference_path"]),
            )
        defaults = NarrationSettings(language=NarrationLanguage(data["language"]))
        return NarrationSettings(
            language=defaults.language,
            style=NarrationStyle(data["style"]),
            voice_reference=voice_reference,
            exaggeration=data["exaggeration"],
            cfg_weight=data["cfg_weight"],
            # .get(...) fallbacks so a manifest written before these fields
            # existed still resumes cleanly, using the library's defaults.
            temperature=data.get("temperature", defaults.temperature),
            repetition_penalty=data.get("repetition_penalty", defaults.repetition_penalty),
            min_p=data.get("min_p", defaults.min_p),
            top_p=data.get("top_p", defaults.top_p),
        )
