"""Masterização de audiobook: volume constante (LUFS), pico seguro e relatório de conformidade (ACX)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SR = 24000

PERFIS = {
    "audiobook": {"nome": "Audiobook (−19 LUFS)", "lufs": -19.0, "pico": -3.0},
    "acx": {"nome": "ACX / Audible (≈ −20 LUFS)", "lufs": -20.0, "pico": -3.5},
    "podcast": {"nome": "Podcast (−16 LUFS)", "lufs": -16.0, "pico": -1.5},
    "off": {"nome": "Sem masterização", "lufs": None, "pico": -1.0},
}


@dataclass
class Relatorio:
    lufs: float
    rms_db: float
    pico_db: float
    piso_ruido_db: float

    def avisos_acx(self) -> list[str]:
        av = []
        if not (-23.0 <= self.rms_db <= -18.0):
            av.append(f"RMS {self.rms_db:.1f} dB fora de −23…−18")
        if self.pico_db > -3.0:
            av.append(f"Pico {self.pico_db:.1f} dB acima de −3")
        if self.piso_ruido_db > -60.0:
            av.append(f"Ruído de fundo {self.piso_ruido_db:.1f} dB acima de −60")
        return av


def medir(x: np.ndarray, sr: int = SR) -> Relatorio:
    if len(x) < sr // 2:
        return Relatorio(-70.0, -70.0, -70.0, -90.0)
    import pyloudnorm as pyln

    lufs = float(pyln.Meter(sr).integrated_loudness(x.astype(np.float64)))
    rms = 20 * np.log10(float(np.sqrt(np.mean(x ** 2))) + 1e-9)
    pico = 20 * np.log10(float(np.max(np.abs(x))) + 1e-9)
    passo = int(sr * 0.1)
    n = len(x) // passo
    blocos = np.sqrt(np.mean(x[: n * passo].reshape(n, passo) ** 2, axis=1) + 1e-14)
    piso = 20 * np.log10(float(np.percentile(blocos, 3)) + 1e-9)
    return Relatorio(lufs, float(rms), float(pico), float(piso))


def masterizar(x: np.ndarray, perfil: str = "audiobook", lufs: float | None = None, pico: float | None = None,
               sr: int = SR) -> np.ndarray:
    p = PERFIS.get(perfil, PERFIS["audiobook"])
    alvo = lufs if lufs is not None else p["lufs"]
    teto = pico if pico is not None else p["pico"]
    if len(x) == 0:
        return x
    import pedalboard as pb

    y = x.astype(np.float32)
    if perfil != "off":
        y = pb.Pedalboard([pb.HighpassFilter(65.0)])(y, sr)
    if alvo is not None and len(y) >= sr:
        import pyloudnorm as pyln

        atual = float(pyln.Meter(sr).integrated_loudness(y.astype(np.float64)))
        if np.isfinite(atual):
            ganho = float(np.clip(alvo - atual, -24.0, 24.0))
            y = y * (10 ** (ganho / 20))
    y = limitar(y, teto, sr)
    return np.nan_to_num(y).astype(np.float32)


def limitar(x: np.ndarray, teto_db: float, sr: int = SR) -> np.ndarray:
    """Limitador de pico com antecipação (só reduz o que passa do teto; nunca aumenta o volume)."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d

    teto = 10 ** (teto_db / 20)
    env = np.abs(x)
    if float(env.max(initial=0.0)) <= teto:
        return x
    ganho = np.minimum(1.0, teto / np.maximum(env, 1e-9))
    janela = max(3, int(sr * 0.006))
    ganho = minimum_filter1d(ganho, size=janela * 2 + 1, mode="nearest")
    ganho = uniform_filter1d(ganho, size=janela * 2 + 1, mode="nearest")
    return (x * np.minimum(ganho, 1.0)).astype(np.float32)
