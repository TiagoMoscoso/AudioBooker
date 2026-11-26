"""Junta os trechos de um capítulo com pausas naturais (frase < parágrafo < cena < início de capítulo)."""
from __future__ import annotations

import numpy as np

SR = 24000


def silencio(segundos: float, sr: int = SR) -> np.ndarray:
    return np.zeros(int(max(0.0, segundos) * sr), dtype=np.float32)


def _suavizar_pontas(x: np.ndarray, sr: int = SR, ms: float = 8.0) -> np.ndarray:
    n = min(len(x) // 2, int(sr * ms / 1000))
    if n > 1:
        x = x.copy()
        rampa = np.linspace(0.0, 1.0, n, dtype=np.float32)
        x[:n] *= rampa
        x[-n:] *= rampa[::-1]
    return x


def cortar_bordas(x: np.ndarray, sr: int = SR, limiar_db: float = -48.0, manter_ms: float = 60.0) -> np.ndarray:
    """Tira silêncio longo no começo/fim de um trecho sintetizado, deixando um respiro curto."""
    if len(x) == 0:
        return x
    passo = int(sr * 0.01)
    n = len(x) // passo
    if n < 3:
        return x
    rms = np.sqrt(np.mean(x[: n * passo].reshape(n, passo) ** 2, axis=1) + 1e-12)
    ativo = np.where(20 * np.log10(rms + 1e-9) > limiar_db)[0]
    if len(ativo) == 0:
        return x
    folga = int(manter_ms / 10)
    ini = max(0, ativo[0] - folga) * passo
    fim = min(n, ativo[-1] + 1 + folga) * passo
    return x[ini:fim]


def juntar(partes: list[tuple[np.ndarray, float]], sr: int = SR) -> np.ndarray:
    """`partes`: lista de (áudio, pausa_antes_em_segundos)."""
    blocos: list[np.ndarray] = []
    for audio, pausa in partes:
        if pausa > 0:
            blocos.append(silencio(pausa, sr))
        if len(audio):
            blocos.append(_suavizar_pontas(audio, sr))
    return np.concatenate(blocos) if blocos else np.zeros(0, dtype=np.float32)
