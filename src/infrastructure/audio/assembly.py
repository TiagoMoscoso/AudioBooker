"""Per-chunk assembly primitives (§ montagem sem clicks/cortes perceptíveis):
trims abnormal leading/trailing silence, cuts near a zero crossing to avoid
digital discontinuities, and applies a microscopic edge fade — cheap
insurance against clicks/pops at chunk joins. Kept separate from
post_processor.py (which owns concatenation/pause/mastering orchestration)
so each piece stays small and single-purpose."""
from __future__ import annotations

import numpy as np

_DEFAULT_THRESHOLD_DB = -45.0
_DEFAULT_MAX_LEAD_TRIM_MS = 250
_DEFAULT_MAX_TRAIL_TRIM_MS = 250
_DEFAULT_FADE_MS = 6.0
_ZERO_CROSSING_SEARCH_MS = 5.0


def _db_to_amplitude(db: float) -> float:
    return 10.0 ** (db / 20.0)


def nearest_zero_crossing(samples: np.ndarray, index: int, search_window_samples: int) -> int:
    """Returns the index within [index - window, index + window] where the
    waveform is closest to zero, so a cut made there avoids an abrupt
    sample-value jump (a click). Falls back to `index` unchanged if the
    array is too short to search meaningfully."""
    if samples.size == 0:
        return index
    lo = max(0, index - search_window_samples)
    hi = min(samples.size, index + search_window_samples)
    if hi <= lo:
        return max(0, min(index, samples.size - 1))
    window = samples[lo:hi]
    best_offset = int(np.argmin(np.abs(window)))
    return lo + best_offset


def trim_silence(
    samples: np.ndarray,
    sample_rate: int,
    threshold_db: float = _DEFAULT_THRESHOLD_DB,
    max_lead_trim_ms: float = _DEFAULT_MAX_LEAD_TRIM_MS,
    max_trail_trim_ms: float = _DEFAULT_MAX_TRAIL_TRIM_MS,
) -> np.ndarray:
    """Trims leading/trailing near-silence from a single chunk, capped so a
    genuinely quiet word or breath at the very start/end of the utterance is
    never eaten — only clearly excessive lead-in/lead-out silence (e.g. dead
    air the model sometimes produces before the first phoneme) is removed.
    Cuts land on the nearest zero crossing to avoid introducing a click of
    its own."""
    if samples.size == 0 or sample_rate <= 0:
        return samples

    threshold = _db_to_amplitude(threshold_db)
    above = np.abs(samples) >= threshold
    if not np.any(above):
        return samples  # entirely below threshold — leave to quality validation, not this step

    first_loud = int(np.argmax(above))
    last_loud = int(len(samples) - 1 - np.argmax(above[::-1]))

    max_lead = int(sample_rate * max_lead_trim_ms / 1000)
    max_trail = int(sample_rate * max_trail_trim_ms / 1000)
    search_window = int(sample_rate * _ZERO_CROSSING_SEARCH_MS / 1000)

    start = max(0, min(first_loud, max_lead))
    end = min(len(samples), max(last_loud + 1, len(samples) - max_trail))

    if start > 0:
        start = nearest_zero_crossing(samples, start, search_window)
    if end < len(samples):
        end = nearest_zero_crossing(samples, end, search_window)

    if end <= start:
        return samples
    return samples[start:end]


def apply_edge_fade(
    samples: np.ndarray, sample_rate: int, fade_ms: float = _DEFAULT_FADE_MS
) -> np.ndarray:
    """Short linear fade-in/out at the very start/end of a chunk — a few
    milliseconds, inaudible as a fade in its own right, but cheap insurance
    against a DC-offset click at the join if the waveform doesn't already
    start/end at zero amplitude. Never applied between sentences within a
    chunk — only at the two outer edges."""
    if samples.size == 0 or sample_rate <= 0:
        return samples
    fade_samples = min(int(sample_rate * fade_ms / 1000), samples.size // 2)
    if fade_samples <= 0:
        return samples

    result = samples.astype(np.float32, copy=True)
    ramp = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
    result[:fade_samples] *= ramp
    result[-fade_samples:] *= ramp[::-1]
    return result
