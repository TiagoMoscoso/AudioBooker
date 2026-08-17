"""ChatterboxSpeechSynthesizer: the only place in the codebase that calls
chatterbox's `model.generate(...)`. Uses torch.inference_mode() (§43) and
never loads a model itself — it always asks ChatterboxModelManager, which
owns the load-once-reuse-many lifecycle (§22).

Also owns a small voice-conditioning cache: chatterbox's own generate()
recomputes voice conditioning from disk (VoiceEncoder + S3Gen embedding)
every time `audio_prompt_path` is passed — confirmed in the installed
chatterbox==0.1.7 source (tts.py / mtl_tts.py), which means a custom voice
reference would otherwise be re-embedded on every single chunk of a book.
Since `prepare_conditionals(path, exaggeration=...)` populates `model.conds`
and generate() reuses `model.conds` whenever `audio_prompt_path` is omitted
(exactly how the built-in default voice already behaves), calling it once
per (language, voice path) and omitting `audio_prompt_path` afterward both
removes the redundant recomputation and guarantees byte-identical
conditioning across every chunk — a stronger voice-continuity guarantee than
recomputing from disk each time. (`exaggeration` does not need to be part of
that cache key: generate() itself cheaply patches `model.conds.t3.emotion_adv`
in place on every call when it differs, no re-embedding involved.)"""
from __future__ import annotations

import numpy as np

from domain.narration import NarrationLanguage
from infrastructure.tts.model_manager import ChatterboxModelManager
from infrastructure.tts.synthesizer import AudioSegment, SpeechRequest


class ChatterboxSpeechSynthesizer:
    def __init__(self, model_manager: ChatterboxModelManager) -> None:
        self._model_manager = model_manager
        # Keyed by id(model) rather than language alone, so a model reload
        # (ChatterboxModelManager evicts the previous language's model when
        # switching — see model_manager.py) can never be mistaken for the
        # model instance a previous cache entry was prepared against.
        self._prepared_conditioning_key: tuple[int, str] | None = None
        self._default_conds_by_model: dict[int, object] = {}
        self._last_input_token_count: int | None = None

    @property
    def last_input_token_count(self) -> int | None:
        """Best-effort *input*-token count for the most recent synthesize()
        call (mirrors ReliableSpeechSynthesizer.last_diagnostic's pattern),
        used only for the performance report (services.generation_profiler).
        Not the true output speech-token count — generate() never exposes
        that — just the tokenizer's encoding of the input text, which is a
        useful proxy for how "long" a chunk was to the model. None if the
        tokenizer call failed (never allowed to break generation itself)."""
        return self._last_input_token_count

    def synthesize(self, request: SpeechRequest) -> AudioSegment:
        import torch

        settings = request.settings
        model = self._model_manager.get_model(settings.language)
        model_key = id(model)
        # Snapshot the checkpoint's own built-in default conditioning the
        # first time this model instance is ever seen — before anything
        # below could have mutated it — so a later request for the default
        # voice can restore it even after a custom voice reference has been
        # used on this same shared synthesizer/model in between.
        if model_key not in self._default_conds_by_model:
            self._default_conds_by_model[model_key] = getattr(model, "conds", None)

        kwargs: dict = {
            "exaggeration": settings.exaggeration,
            "cfg_weight": settings.cfg_weight,
            "temperature": settings.temperature,
            "repetition_penalty": settings.repetition_penalty,
            "min_p": settings.min_p,
            "top_p": settings.top_p,
        }
        # `language_id` only exists on the multilingual model's API, used
        # here exclusively for Portuguese (see model_manager.py).
        if settings.language == NarrationLanguage.PORTUGUESE:
            kwargs["language_id"] = "pt"

        if settings.voice_reference is not None:
            conditioning_key = (model_key, str(settings.voice_reference.path))
            if conditioning_key != self._prepared_conditioning_key:
                model.prepare_conditionals(
                    str(settings.voice_reference.path), exaggeration=settings.exaggeration
                )
                self._prepared_conditioning_key = conditioning_key
            # audio_prompt_path intentionally omitted: model.conds was just
            # (re)populated above, and generate() reuses it as-is when the
            # path is None — see module docstring.
        else:
            if self._prepared_conditioning_key is not None:
                # A custom voice was active on this model instance before —
                # restore the pristine default rather than letting generate()
                # silently keep using the last custom voice's conditioning.
                model.conds = self._default_conds_by_model[model_key]
            self._prepared_conditioning_key = None

        with torch.inference_mode():
            wav = model.generate(request.text, **kwargs)

        samples = wav.squeeze().detach().cpu().numpy().astype(np.float32)
        self._last_input_token_count = self._count_input_tokens(model, request.text, kwargs.get("language_id"))
        return AudioSegment(samples=samples, sample_rate=model.sr)

    def _count_input_tokens(self, model, text: str, language_id: str | None) -> int | None:
        # A second, throwaway tokenizer call solely for the performance
        # report — negligible cost (microsecond-scale BPE encode on CPU)
        # next to a generate() call that takes seconds, so it's always on
        # rather than threading a profiling flag through three call layers
        # for no measurable benefit. Never allowed to affect generation.
        try:
            if language_id is not None:
                tokens = model.tokenizer.text_to_tokens(text, language_id=language_id)
            else:
                tokens = model.tokenizer.text_to_tokens(text)
            return int(tokens.shape[-1])
        except Exception:  # noqa: BLE001 - a metrics-only helper, never fatal
            return None
