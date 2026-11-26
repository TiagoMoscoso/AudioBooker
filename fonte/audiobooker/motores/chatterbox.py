"""Chatterbox (Resemble AI): clonagem de voz a partir de um áudio de referência e controle de emoção.

Variantes (campo `variante` nos parâmetros da voz):
  turbo        inglês, bem mais rápido (bom na CPU); aceita tags como [laugh], [chuckle], [cough]; ignora exagero/CFG
  original     inglês, com exagero (emoção) e CFG
  multilingue  23 idiomas, incluindo português

Roda em CUDA (NVIDIA) ou CPU. Placas AMD e Intel não têm CUDA: usa CPU (bem mais lento).
"""
from __future__ import annotations

import os

import numpy as np

from .. import caminhos, dispositivos
from ..vozes.modelo import Voz
from .base import Motor, MotorIndisponivel, Progresso

# pesos do Chatterbox ficam junto dos outros modelos, não no cache global do Hugging Face
os.environ.setdefault("HF_HOME", str(caminhos.MODELOS / "hf"))

_REPOS = {"turbo": "ResembleAI/chatterbox-turbo", "original": "ResembleAI/chatterbox", "multilingue": "ResembleAI/chatterbox"}


def escolher_variante(voz: Voz) -> str:
    """Padrão = o modelo mais pesado e expressivo (original em inglês, multilíngue nos demais); o Turbo só se pedido."""
    v = (voz.parametros or {}).get("variante", "")
    if v in _REPOS:
        return v
    return "original" if voz.idioma == "en" else "multilingue"


_CAPACIDADES = {"turbo": {"tags", "clonagem"}, "original": {"emocao", "cfg", "clonagem"},
                "multilingue": {"emocao", "cfg", "clonagem", "multilingue"}}


class MotorChatterbox(Motor):
    nome = "chatterbox"
    rotulo = "Chatterbox (clonagem de voz e emoção)"

    def __init__(self) -> None:
        super().__init__()
        self._modelos: dict[str, object] = {}
        self._ref_ativa: dict[str, str] = {}
        self._conds_padrao: dict[str, object] = {}
        self._dev = "cpu"
        self._threads = 0

    @property
    def carregado(self) -> bool:
        return bool(self._modelos)

    def capacidades(self, voz: Voz | None = None) -> frozenset[str]:
        return frozenset(_CAPACIDADES[escolher_variante(voz)] if voz is not None else _CAPACIDADES["original"])

    def _ambiente(self) -> None:
        os.environ.setdefault("HF_HOME", str(caminhos.MODELOS / "hf"))
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("TQDM_DISABLE", "1")

    def estado(self) -> tuple[bool, str]:
        from importlib.util import find_spec

        # find_spec não importa o pacote: abrir o programa não pode esperar o PyTorch carregar
        if find_spec("chatterbox") is None or find_spec("torch") is None:
            return False, "Chatterbox/PyTorch não instalados. Rode a instalação do Audiobooker."
        pasta = caminhos.MODELOS / "hf"
        if not pasta.exists() or not any(pasta.rglob("*.safetensors")):
            return True, "Pronto (o modelo, ≈3 GB, é baixado na primeira voz clonada)."
        return True, "Pronto"

    def baixar(self, progresso: Progresso | None = None) -> None:
        self._ambiente()
        from huggingface_hub import snapshot_download

        for variante in ("turbo",):
            if progresso:
                progresso(f"Baixando Chatterbox {variante}…")
            snapshot_download(repo_id=_REPOS[variante], allow_patterns=["*.safetensors", "*.json", "*.pt", "*.txt", "*.model"])

    def carregar(self, preferencia: str, threads: int, progresso: Progresso | None = None) -> None:
        ok, msg = self.estado()
        if not ok:
            raise MotorIndisponivel(msg)
        self._ambiente()
        import torch

        self._dev = dispositivos.escolher_chatterbox(preferencia)
        self._threads = dispositivos.threads_efetivas(threads)
        torch.set_num_threads(self._threads)
        self.dispositivo = self._dev
        if self._dev == "cpu" and dispositivos.detectar().nome_gpu and not dispositivos.detectar().cuda:
            self.nota_dispositivo = "Chatterbox precisa de CUDA (NVIDIA) para usar GPU; nesta máquina roda na CPU."

    def _modelo(self, variante: str, progresso: Progresso | None = None):
        if variante in self._modelos:
            return self._modelos[variante]
        # só um modelo por vez, para caber na memória/VRAM
        self.descarregar()
        if progresso:
            progresso(f"Carregando Chatterbox {variante} ({self._dev.upper()})…")
        import torch

        try:
            if variante == "turbo":
                from chatterbox.tts_turbo import ChatterboxTurboTTS as Classe
            elif variante == "original":
                from chatterbox.tts import ChatterboxTTS as Classe
            else:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS as Classe
            modelo = Classe.from_pretrained(torch.device(self._dev) if variante == "multilingue" else self._dev)
        except Exception as e:  # noqa: BLE001
            raise MotorIndisponivel(f"Não consegui carregar o Chatterbox ({variante}): {e}") from e
        self._modelos[variante] = modelo
        self._conds_padrao[variante] = getattr(modelo, "conds", None)
        return modelo

    def descarregar(self) -> None:
        self._modelos.clear()
        self._ref_ativa.clear()
        self._conds_padrao.clear()
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    def sintetizar(self, texto: str, voz: Voz, pronuncias: dict[str, str] | None = None,
                   entrega: dict | None = None) -> np.ndarray:
        import torch

        variante = escolher_variante(voz)
        modelo = self._modelo(variante)
        p = dict(voz.parametros or {})
        for k_in, k_out in (("emocao", "exagero"), ("cfg", "cfg")):  # direção do trecho vence o padrão da voz
            if entrega and entrega.get(k_in) is not None:
                p[k_out] = entrega[k_in]
        ref = voz.caminho_referencia()
        ref_chave = str(ref) if ref and ref.exists() else ""

        # a condicionação da voz é calculada uma vez e reaproveitada em todos os trechos
        if self._ref_ativa.get(variante) != ref_chave:
            if ref_chave:
                if variante == "turbo":
                    modelo.prepare_conditionals(ref_chave, exaggeration=float(p.get("exagero", 0.5)))
                else:
                    modelo.prepare_conditionals(ref_chave, exaggeration=float(p.get("exagero", 0.5)))
            elif self._conds_padrao.get(variante) is not None:
                modelo.conds = self._conds_padrao[variante]
            self._ref_ativa[variante] = ref_chave

        args: dict = {"temperature": float(p.get("temperatura", 0.8))}
        if variante == "original":
            args.update(exaggeration=float(p.get("exagero", 0.5)), cfg_weight=float(p.get("cfg", 0.5)),
                        repetition_penalty=float(p.get("penalidade_repeticao", 1.2)))
        elif variante == "multilingue":
            args.update(exaggeration=float(p.get("exagero", 0.5)), cfg_weight=float(p.get("cfg", 0.5)),
                        repetition_penalty=float(p.get("penalidade_repeticao", 2.0)),
                        language_id=p.get("lingua", {"pt": "pt", "en": "en", "es": "es", "fr": "fr", "it": "it"}.get(voz.idioma, "en")))
        if pronuncias:  # Chatterbox não aceita fonemas: o dicionário já trocou por grafia sonora
            pass
        with torch.inference_mode():
            wav = modelo.generate(texto, **args)
        x = wav.squeeze().detach().cpu().numpy().astype(np.float32)
        if modelo.sr != self.sr:
            from scipy.signal import resample_poly
            from math import gcd

            g = gcd(int(modelo.sr), self.sr)
            x = resample_poly(x, self.sr // g, int(modelo.sr) // g).astype(np.float32)
        if voz.velocidade and abs(voz.velocidade - 1.0) > 0.02:
            import pedalboard as pb

            x = np.squeeze(pb.time_stretch(x, self.sr, stretch_factor=float(voz.velocidade))).astype(np.float32)
        return x
