"""Whole-book loudness mastering (§ loudness normalization + true peak
limiter): measures integrated loudness via pyloudnorm (ITU-R BS.1770-4, the
standard basis for audiobook loudness targets — already an installed
dependency via chatterbox-tts's own librosa chain, and already referenced in
Audiobooker.spec's PyInstaller packaging metadata), then a true-peak limiter
as a safety ceiling. Replaces the previous hard np.clip in
AudioPostProcessor.normalize, which could introduce audible distortion
whenever a peak-normalized chapter's true peak still exceeded full scale.

Applied once across the whole book (a single measured gain applied
uniformly to every chapter — see GenerateAudiobookService._finalize), not
independently per chapter, so chapters never drift apart in perceived
volume."""
from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
from scipy.signal import resample_poly

# ACX/Audible-style single-narrator convention; a starting point meant to be
# tuned after auditory testing, not a hard technical requirement.
DEFAULT_TARGET_LUFS = -19.0
DEFAULT_TRUE_PEAK_CEILING_DBFS = -3.0
_OVERSAMPLE_FACTOR = 4


class LoudnessMaster:
    def __init__(
        self,
        target_lufs: float = DEFAULT_TARGET_LUFS,
        true_peak_ceiling_dbfs: float = DEFAULT_TRUE_PEAK_CEILING_DBFS,
    ) -> None:
        self._target_lufs = target_lufs
        self._true_peak_ceiling = true_peak_ceiling_dbfs

    def measure_lufs(self, samples: np.ndarray, sample_rate: int) -> float:
        if samples.size == 0:
            return float("-inf")
        meter = pyln.Meter(sample_rate)
        try:
            return float(meter.integrated_loudness(samples.astype(np.float64)))
        except Exception:
            # pyloudnorm raises on audio shorter than its measurement block
            # (0.4s) — too little signal to measure meaningfully; treat as
            # silence rather than let a short chapter crash a whole-book pass.
            return float("-inf")

    def compute_gain_for_target(
        self, samples: np.ndarray, sample_rate: int, target_lufs: float | None = None
    ) -> float:
        """Linear gain factor that brings `samples` to `target_lufs` (or the
        instance default). Returns 1.0 (no change) if loudness can't be
        measured, rather than risk an extreme/undefined gain."""
        measured = self.measure_lufs(samples, sample_rate)
        if measured == float("-inf"):
            return 1.0
        target = target_lufs if target_lufs is not None else self._target_lufs
        return float(10.0 ** ((target - measured) / 20.0))

    def true_peak_dbfs(self, samples: np.ndarray) -> float:
        """Estimates true (inter-sample) peak via 4x oversampling — a
        sample-peak measurement alone can miss a peak that occurs between
        two discrete samples, which a downstream lossy encoder's own
        reconstruction filter can then turn into real clipping."""
        if samples.size == 0:
            return float("-inf")
        oversampled = resample_poly(samples, _OVERSAMPLE_FACTOR, 1)
        peak = float(np.max(np.abs(oversampled))) if oversampled.size else 0.0
        return 20.0 * np.log10(peak) if peak > 0 else float("-inf")

    def true_peak_limit(self, samples: np.ndarray, ceiling_dbfs: float | None = None) -> np.ndarray:
        """A single static gain-reduction (not per-sample compression —
        audiobook narration should stay dynamically natural, not squashed)
        applied only if the measured true peak exceeds the ceiling."""
        if samples.size == 0:
            return samples
        ceiling = ceiling_dbfs if ceiling_dbfs is not None else self._true_peak_ceiling
        peak_db = self.true_peak_dbfs(samples)
        if peak_db == float("-inf") or peak_db <= ceiling:
            result = samples.astype(np.float32)
        else:
            gain = 10.0 ** ((ceiling - peak_db) / 20.0)
            result = (samples * gain).astype(np.float32)
        # Final safety net in case the true-peak estimate ever misses an
        # edge case — never let a sample value leave the codec's valid range.
        return np.clip(result, -1.0, 1.0)
