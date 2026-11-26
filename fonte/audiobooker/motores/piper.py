"""Piper (OHF-Voice/piper1-gpl): vozes externas leves, rodam na CPU muito rápido (≈ 15× o tempo real).

As vozes são baixadas pelo catálogo (Vozes → Baixar vozes) e ficam em %LOCALAPPDATA%\\AUDIOBOOKER\\modelos\\piper.
Em uma voz do programa, `base = {"<chave da voz>": 1.0}` (ex.: en_GB-alan-medium).
"""
from __future__ import annotations

from importlib.util import find_spec
from math import gcd

import numpy as np

from ..vozes import catalogo_externo
from ..vozes.modelo import Voz
from .base import Motor, MotorIndisponivel, Progresso


class MotorPiper(Motor):
    nome = "piper"
    rotulo = "Piper (vozes externas baixadas)"

    def __init__(self) -> None:
        super().__init__()
        self._vozes: dict[str, object] = {}
        self._ok = False

    @property
    def carregado(self) -> bool:
        return self._ok

    def capacidades(self, voz=None) -> frozenset[str]:
        return frozenset()

    def estado(self) -> tuple[bool, str]:
        if find_spec("piper") is None:
            return False, "Pacote piper-tts não instalado. Rode a instalação do Audiobooker."
        n = len(catalogo_externo.instaladas())
        return True, f"Pronto ({n} voz(es) baixada(s))" if n else "Pronto, mas nenhuma voz baixada ainda (Vozes → Baixar vozes)."

    def baixar(self, progresso: Progresso | None = None) -> None:
        raise MotorIndisponivel("As vozes do Piper são baixadas uma a uma em Vozes → Baixar vozes.")

    def carregar(self, preferencia: str, threads: int, progresso: Progresso | None = None) -> None:
        ok, msg = self.estado()
        if not ok:
            raise MotorIndisponivel(msg)
        self.dispositivo = "cpu"   # rápido o bastante na CPU e não disputa a memória da placa com os outros motores
        self._ok = True

    def descarregar(self) -> None:
        self._vozes.clear()
        self._ok = False

    def _voz(self, chave: str):
        if chave in self._vozes:
            return self._vozes[chave]
        modelo = catalogo_externo.PASTA / f"{chave}.onnx"
        if not modelo.exists():
            raise MotorIndisponivel(f"A voz externa '{chave}' não está baixada (Vozes → Baixar vozes).")
        from piper import PiperVoice

        v = PiperVoice.load(str(modelo), str(modelo) + ".json", use_cuda=False)
        self._vozes[chave] = v
        return v

    def sintetizar(self, texto: str, voz: Voz, pronuncias: dict[str, str] | None = None,
                   entrega: dict | None = None) -> np.ndarray:
        from piper import SynthesisConfig

        if not voz.base:
            raise MotorIndisponivel("Esta voz não tem modelo do Piper escolhido.")
        chave = next(iter(voz.base))
        v = self._voz(chave)
        vel = float(np.clip(voz.velocidade or 1.0, 0.5, 2.0))
        cfg = SynthesisConfig(length_scale=1.0 / vel, noise_scale=float((voz.parametros or {}).get("variacao", 0.667)),
                              noise_w_scale=0.8, normalize_audio=True)
        pedacos, sr = [], 22050
        for c in v.synthesize(texto, cfg):
            pedacos.append(np.asarray(c.audio_float_array, dtype=np.float32))
            sr = c.sample_rate
        if not pedacos:
            return np.zeros(0, dtype=np.float32)
        x = np.concatenate(pedacos)
        if sr != self.sr:
            from scipy.signal import resample_poly

            g = gcd(sr, self.sr)
            x = resample_poly(x, self.sr // g, sr // g).astype(np.float32)
        return x
