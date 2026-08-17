"""Loads and caches the Chatterbox model at most once per language per
process (§16, §22, §43 — never reload per chunk), exposing a state machine
so the UI can show "Preparando mecanismo de narração" / "Baixando modelo..."
without ever calling Chatterbox directly.

Two Chatterbox entry points are used, chosen by the selected narration
language (§5):
  - English   -> chatterbox.tts.ChatterboxTTS (dedicated English model).
  - Portuguese -> chatterbox.mtl_tts.ChatterboxMultilingualTTS with
    language_id="pt" — this is Chatterbox's official, documented way to
    narrate Portuguese. The project also ships six "Single Language Pack"
    finetunes on Hugging Face (including separate pt-br/pt-pt checkpoints),
    but as of writing they are only demoed through separate Gradio Spaces
    with no documented `from_pretrained(...)` loading path in the main
    package; using them would mean depending on undocumented internals.
    We therefore use the general multilingual model for Portuguese for this
    MVP (a decision explicitly permitted by AUDIOBOOKER_SPECS.md §53), and
    note the dedicated pt-br checkpoint as a future improvement in the
    README once Resemble AI documents a supported loading path for it.

Note on API drift: the project's GitHub README documents a `t3_model="v3"`
kwarg on `ChatterboxMultilingualTTS.from_pretrained(...)`, but the currently
published PyPI release (chatterbox-tts 0.1.7, pinned in pyproject.toml) does
not accept it — `inspect.signature` on the installed package shows
`from_pretrained(device)` only. Per §53 ("verificar a documentação atual...
confirmar APIs reais"), we call the installed package's real signature
rather than the README's, and do not pass `t3_model`.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum

from domain.narration import NarrationLanguage
from i18n import tr
from infrastructure.tts.hardware import HardwareDetector, HardwareInfo

logger = logging.getLogger(__name__)


class ModelState(Enum):
    UNAVAILABLE = "unavailable"
    DOWNLOADING = "downloading"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass
class ModelStatus:
    state: ModelState
    language: NarrationLanguage | None
    device: str | None
    device_name: str | None
    message: str = ""


class ChatterboxModelManager:
    """Owns at most one loaded model per language at a time. Thread-safe:
    concurrent callers requesting the same language never trigger two
    simultaneous loads."""

    def __init__(
        self, hardware_detector: HardwareDetector | None = None, warm_up: bool = True
    ) -> None:
        self._hardware_detector = hardware_detector or HardwareDetector()
        self._lock = threading.Lock()
        self._models: dict[NarrationLanguage, object] = {}
        self._hardware: HardwareInfo | None = None
        self._status = ModelStatus(
            state=ModelState.UNAVAILABLE, language=None, device=None, device_name=None
        )
        # Always True in production; exposed only so
        # scripts/benchmark_generation.py can measure warm-up's actual effect
        # on first-chunk latency with a --no-warmup run for comparison.
        self._warm_up_enabled = warm_up

    @property
    def status(self) -> ModelStatus:
        return self._status

    def hardware(self) -> HardwareInfo:
        if self._hardware is None:
            self._hardware = self._hardware_detector.detect()
        return self._hardware

    def get_model(self, language: NarrationLanguage):
        with self._lock:
            if language in self._models:
                return self._models[language]

            # A single generation session only ever narrates in one language
            # (§5 — no mid-book language switching), so there is no benefit
            # to keeping a previous language's model resident once a
            # different one is requested — only VRAM risk. On a modest GPU,
            # loading the second ~2GB model while the first stayed cached
            # was observed to raise torch.OutOfMemoryError in practice.
            # Unloading first keeps memory use bounded to one model (§16
            # "descarregar quando apropriado", §43 "estabilidade >
            # paralelismo agressivo").
            if self._models:
                self._unload_locked()

            hardware = self.hardware()
            self._status = ModelStatus(
                state=ModelState.DOWNLOADING,
                language=language,
                device=hardware.device,
                device_name=hardware.device_name,
                message=tr("model.downloading"),
            )
            try:
                model = self._load(language, hardware.device, hardware.device_name)
                if self._warm_up_enabled:
                    self._warm_up(model, language)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI via status
                logger.exception("Falha ao carregar modelo Chatterbox para %s", language)
                self._status = ModelStatus(
                    state=ModelState.FAILED,
                    language=language,
                    device=hardware.device,
                    device_name=hardware.device_name,
                    message=str(exc),
                )
                raise

            self._models[language] = model
            self._status = ModelStatus(
                state=ModelState.READY,
                language=language,
                device=hardware.device,
                device_name=hardware.device_name,
                message=tr("model.ready"),
            )
            return model

    def _load(self, language: NarrationLanguage, device: str, device_name: str):
        self._status = ModelStatus(
            state=ModelState.LOADING,
            language=language,
            device=device,
            device_name=device_name,
            message=tr("model.loading"),
        )
        if language == NarrationLanguage.ENGLISH:
            from chatterbox.tts import ChatterboxTTS
            return ChatterboxTTS.from_pretrained(device=device)

        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        return ChatterboxMultilingualTTS.from_pretrained(device=device)

    def _warm_up(self, model, language: NarrationLanguage) -> None:
        """One throwaway generate() call right after load, so CUDA kernel
        compilation / allocator first-touch cost lands on the already-visible
        "Carregando modelo..." screen (ModelPrepareWorker, off the UI thread)
        instead of the user's first real narration chunk.

        Deliberately bypasses ChatterboxSpeechSynthesizer (never touches its
        voice-conditioning cache state) and reuses whatever `exaggeration`
        value is already baked into the checkpoint's default `model.conds`
        rather than a hardcoded one — confirmed in the installed
        chatterbox==0.1.7 source that generate() only ever *patches*
        `conds.t3.emotion_adv` in place when the passed value differs, no
        re-embedding involved, so this can never perturb the "pristine
        default" conditioning ChatterboxSpeechSynthesizer snapshots on first
        use. Never allowed to block or fail model readiness — any error here
        is swallowed and logged, and the model is still considered READY."""
        try:
            import torch

            conds = getattr(model, "conds", None)
            if conds is None:
                return
            exaggeration = float(conds.t3.emotion_adv[0, 0, 0])
            kwargs: dict = {"exaggeration": exaggeration, "cfg_weight": 0.5, "temperature": 0.8}
            if language == NarrationLanguage.PORTUGUESE:
                kwargs["language_id"] = "pt"
            with torch.inference_mode():
                model.generate("Preparando o motor de narração.", **kwargs)
        except Exception:  # noqa: BLE001 - warm-up is a pure perf nicety, never fatal
            logger.warning("Aquecimento do modelo Chatterbox falhou; continuando sem ele", exc_info=True)

    def unload(self, language: NarrationLanguage | None = None) -> None:
        with self._lock:
            if language is None:
                self._unload_locked()
            else:
                self._models.pop(language, None)
                self._release_cuda_cache()

    def _unload_locked(self) -> None:
        """Drops every cached model and releases CUDA memory. Caller must
        already hold self._lock."""
        self._models.clear()
        self._release_cuda_cache()

    def _release_cuda_cache(self) -> None:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
