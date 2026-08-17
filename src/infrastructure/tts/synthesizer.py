"""SpeechSynthesizer abstraction (§15). Application services and the UI
depend only on this Protocol — never on Chatterbox directly. Application
Service -> SpeechSynthesizer -> Chatterbox."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

from domain.narration import NarrationSettings


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    settings: NarrationSettings


@dataclass
class AudioSegment:
    samples: np.ndarray  # float32 mono, shape (n_samples,)
    sample_rate: int

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), self.samples, self.sample_rate)

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / float(self.sample_rate) if self.sample_rate else 0.0


class SpeechSynthesizer(Protocol):
    def synthesize(self, request: SpeechRequest) -> AudioSegment: ...
