"""ReliableSpeechSynthesizer: a drop-in SpeechSynthesizer decorator (§
detecção automática de chunks defeituosos + retry inteligente) that
validates every generated chunk (infrastructure.audio.quality) and retries
with progressively more conservative parameters when a chunk looks broken,
without ever changing what the caller sees — same synthesize() signature,
so GenerateAudiobookService's per-chunk loop needs no changes at all; only
the composition root wraps ChatterboxSpeechSynthesizer with this before
injecting it.

Retry ladder (never repeats identical parameters on a real failure):
  1. original NarrationSettings, unmodified.
  2. same settings — PyTorch's global RNG has already advanced from attempt
     1's sampling, so this alone yields a fresh draw (do_sample=True
     inside chatterbox's T3, confirmed in the installed 0.1.7 source);
     under an explicit `base_seed` this instead reseeds deterministically.
  3. a "stability nudge": lower temperature, higher cfg_weight, within safe
     bounds — trading expressiveness for determinism just for this chunk.
  4. (chunks long enough to have a natural clause boundary) split at the
     midpoint clause, synthesize both halves with attempt-1 settings, and
     concatenate them in memory with a short internal pause — written to the
     single already-allocated chunk_path, so checkpoint/manifest shape is
     never touched by this fallback.
If every attempt still fails validation, the least-bad attempt (by
QualityReport.severity_score) is kept and diagnosed, rather than looping
forever or aborting a multi-hour run over one chunk."""
from __future__ import annotations

import re
from dataclasses import replace

import numpy as np

from domain.narration import NarrationSettings
from infrastructure.audio.quality import AudioQualityValidator, QualityReport
from infrastructure.tts.synthesizer import AudioSegment, SpeechRequest, SpeechSynthesizer
from services.generation_diagnostics import ChunkDiagnostic

_CLAUSE_BOUNDARY = re.compile(r"(?<=[,;:])\s+")
_ADAPTIVE_SPLIT_MIN_CHARS = 150
_ADAPTIVE_SPLIT_INTERNAL_PAUSE_MS = 80
_STABILITY_TEMPERATURE = 0.4
_STABILITY_CFG_WEIGHT = 0.7


def _split_roughly_in_half(text: str) -> tuple[str, str] | None:
    parts = [p for p in _CLAUSE_BOUNDARY.split(text) if p.strip()]
    if len(parts) < 2:
        words = text.split(" ")
        if len(words) < 2:
            return None
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])

    total = len(text)
    best_index, best_diff = 1, None
    for i in range(1, len(parts)):
        running = len(" ".join(parts[:i]))
        diff = abs(running - total / 2)
        if best_diff is None or diff < best_diff:
            best_diff, best_index = diff, i
    return " ".join(parts[:best_index]), " ".join(parts[best_index:])


class ReliableSpeechSynthesizer:
    def __init__(
        self,
        inner: SpeechSynthesizer,
        validator: AudioQualityValidator | None = None,
        max_attempts: int = 4,
        base_seed: int | None = None,
    ) -> None:
        self._inner = inner
        self._validator = validator or AudioQualityValidator()
        self._max_attempts = max_attempts
        self._base_seed = base_seed
        self._last_diagnostic: ChunkDiagnostic | None = None

    @property
    def last_diagnostic(self) -> ChunkDiagnostic | None:
        """The ChunkDiagnostic for the most recent synthesize() call, so the
        caller can collect it into a GenerationDiagnosticsReport without
        this class needing to know about the report format itself."""
        return self._last_diagnostic

    @property
    def last_input_token_count(self) -> int | None:
        """Passthrough to the wrapped synthesizer's own property (see
        ChatterboxSpeechSynthesizer), so callers driving this decorator don't
        need to know the concrete inner type to collect performance metrics."""
        return getattr(self._inner, "last_input_token_count", None)

    def synthesize(self, request: SpeechRequest) -> AudioSegment:
        best: tuple[AudioSegment, QualityReport] | None = None
        attempts_made = 0
        used_adaptive_split = False

        for attempt in range(1, self._max_attempts + 1):
            attempts_made = attempt
            settings = self._settings_for_attempt(request.settings, attempt)
            self._maybe_seed(request.text, attempt)

            if attempt == self._max_attempts and len(request.text) >= _ADAPTIVE_SPLIT_MIN_CHARS:
                segment = self._synthesize_split(request.text, request.settings)
                used_adaptive_split = True
            else:
                segment = self._inner.synthesize(SpeechRequest(text=request.text, settings=settings))

            report = self._validator.validate(segment.samples, segment.sample_rate, request.text)
            # Strict improvement only, so a run of identically-bad attempts
            # (a plausible real failure mode — e.g. a consistently silent
            # chunk from a corrupted voice reference) doesn't repeatedly
            # overwrite `best`; attempts_made (tracked separately above)
            # still correctly reflects that every attempt really ran.
            if best is None or report.severity_score < best[1].severity_score:
                best = (segment, report)
            if report.passed:
                break

        segment, report = best
        self._last_diagnostic = ChunkDiagnostic(
            chunk_id="",  # filled in by the caller, which knows the chunk_id
            attempt_count=attempts_made,
            final_attempt_reason="ok" if report.passed else (report.issues[0].code if report.issues else "ok"),
            duration_seconds=report.duration_seconds,
            peak=report.peak,
            flags=tuple(
                (["retry_used"] if attempts_made > 1 else [])
                + [issue.code for issue in report.issues]
                + (["adaptive_split_used"] if used_adaptive_split else [])
            ),
        )
        return segment

    def _settings_for_attempt(self, settings: NarrationSettings, attempt: int) -> NarrationSettings:
        if attempt < 3:
            return settings
        # Attempt 3+ (and the two adaptive-split halves on attempt 4 use the
        # original settings instead — see _synthesize_split): trade some
        # expressiveness for stability on a chunk that's already failed twice.
        temperature = min(settings.temperature, _STABILITY_TEMPERATURE)
        cfg_weight = max(settings.cfg_weight, _STABILITY_CFG_WEIGHT)
        return replace(settings, temperature=temperature, cfg_weight=cfg_weight)

    def _maybe_seed(self, text: str, attempt: int) -> None:
        if self._base_seed is None:
            return
        import torch

        torch.manual_seed(self._base_seed + (hash(text) % 1_000_000) + attempt * 7919)

    def _synthesize_split(self, text: str, settings: NarrationSettings) -> AudioSegment:
        halves = _split_roughly_in_half(text)
        if halves is None:
            return self._inner.synthesize(SpeechRequest(text=text, settings=settings))

        first, second = halves
        segment_a = self._inner.synthesize(SpeechRequest(text=first, settings=settings))
        segment_b = self._inner.synthesize(SpeechRequest(text=second, settings=settings))
        if segment_a.sample_rate != segment_b.sample_rate:
            return segment_a  # inconsistent rates should never happen in practice; fail safe to one half rather than corrupt audio

        gap = np.zeros(
            int(segment_a.sample_rate * _ADAPTIVE_SPLIT_INTERNAL_PAUSE_MS / 1000), dtype=np.float32
        )
        combined = np.concatenate([segment_a.samples, gap, segment_b.samples])
        return AudioSegment(samples=combined, sample_rate=segment_a.sample_rate)
