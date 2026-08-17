"""Post-synthesis chunk quality checks (§ detecção automática de chunks
defeituosos): lightweight, pure-numpy heuristics — no ASR/ML dependency —
that flag audio likely to be broken (empty/silent, clipped, or wildly off
the duration its text should produce) so ReliableSpeechSynthesizer knows
when to retry a chunk. Duration-outlier detection is an honest proxy for
repetition/hallucination, not true content verification — a heavier
ASR-based check was deliberately not added (see the narration pipeline plan,
"out of scope")."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Matches application/analyze_document.py's _WORDS_PER_MINUTE (used there for
# the pre-generation duration estimate shown to the user); duplicated here
# rather than imported so infrastructure/ never depends on application/.
_WORDS_PER_MINUTE = 150
_MIN_WORDS_FOR_DURATION_CHECK = 4  # below this, per-utterance overhead swamps the WPM estimate
_MIN_DURATION_RATIO = 0.4
_MAX_DURATION_RATIO = 2.5
_SILENCE_PEAK_FLOOR = 0.01
_CLIPPING_SAMPLE_THRESHOLD = 0.999
_CLIPPING_FRACTION_LIMIT = 0.001  # 0.1% of samples

_SEVERITY_BY_CODE = {
    "empty": 100, "silent": 80, "too_short": 40, "too_long": 30, "clipping": 20,
}


@dataclass(frozen=True)
class QualityIssue:
    code: str  # "empty" | "silent" | "clipping" | "too_short" | "too_long"
    detail: str


@dataclass
class QualityReport:
    issues: list[QualityIssue] = field(default_factory=list)
    peak: float = 0.0
    duration_seconds: float = 0.0
    expected_duration_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def severity_score(self) -> float:
        """Lower is better. Used to pick the least-bad attempt when every
        retry in the ladder still fails validation, rather than looping
        forever or aborting a multi-hour generation run over one chunk."""
        return sum(_SEVERITY_BY_CODE.get(issue.code, 10) for issue in self.issues)


class AudioQualityValidator:
    def validate(self, samples: np.ndarray, sample_rate: int, text: str) -> QualityReport:
        issues: list[QualityIssue] = []
        duration = (len(samples) / sample_rate) if sample_rate and samples.size else 0.0
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0

        if samples.size == 0:
            issues.append(QualityIssue("empty", "no audio samples were produced"))
        elif peak < _SILENCE_PEAK_FLOOR and text.strip():
            issues.append(QualityIssue("silent", f"peak amplitude {peak:.4f} below silence floor"))

        if samples.size:
            clipped_fraction = float(np.mean(np.abs(samples) >= _CLIPPING_SAMPLE_THRESHOLD))
            if clipped_fraction > _CLIPPING_FRACTION_LIMIT:
                issues.append(
                    QualityIssue("clipping", f"{clipped_fraction:.2%} of samples near full scale")
                )

        word_count = len(text.split())
        expected = (word_count / _WORDS_PER_MINUTE) * 60 if word_count else 0.0
        if word_count >= _MIN_WORDS_FOR_DURATION_CHECK and samples.size:
            if duration < expected * _MIN_DURATION_RATIO:
                issues.append(
                    QualityIssue("too_short", f"{duration:.2f}s vs ~{expected:.2f}s expected")
                )
            elif duration > expected * _MAX_DURATION_RATIO:
                issues.append(
                    QualityIssue(
                        "too_long",
                        f"{duration:.2f}s vs ~{expected:.2f}s expected (possible repetition)",
                    )
                )

        return QualityReport(
            issues=issues, peak=peak, duration_seconds=duration, expected_duration_seconds=expected
        )
