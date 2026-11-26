"""Importa uma voz externa: prepara o áudio de referência para clonagem (Chatterbox).

Boas práticas aplicadas: mono, 24 kHz, corta silêncio das pontas, limita a ~30 s, normaliza o volume,
reduz chiado (opcional) e avisa quando o áudio é curto, ruidoso ou estourado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import caminhos
from ..audio import ffmpeg

SR = 24000
MAX_SEGUNDOS = 30.0
IDEAL_MIN = 6.0


@dataclass
class Relatorio:
    arquivo: Path
    duracao: float
    avisos: list[str] = field(default_factory=list)

    @property
    def bom(self) -> bool:
        return not self.avisos


def _cortar_silencio(x: np.ndarray, sr: int, limiar_db: float = -45.0) -> np.ndarray:
    if len(x) == 0:
        return x
    passo = int(sr * 0.02)
    n = len(x) // passo
    if n < 2:
        return x
    rms = np.sqrt(np.mean(x[: n * passo].reshape(n, passo) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    ativos = np.where(db > max(limiar_db, float(db.max()) - 50))[0]
    if len(ativos) == 0:
        return x
    ini = max(0, (ativos[0] - 3) * passo)
    fim = min(len(x), (ativos[-1] + 4) * passo)
    return x[ini:fim]


def _reduzir_ruido(x: np.ndarray, sr: int, forca: float = 1.0) -> np.ndarray:
    """Porta espectral simples: estima o ruído nos 10% mais calmos do áudio."""
    from scipy.signal import istft, stft

    f, t, Z = stft(x, sr, nperseg=1024)
    mag = np.abs(Z)
    energia = mag.mean(axis=0)
    calmos = mag[:, energia <= np.percentile(energia, 10)]
    if calmos.shape[1] == 0:
        return x
    piso = calmos.mean(axis=1, keepdims=True) * (1.0 + forca)
    ganho = np.clip((mag - piso) / (mag + 1e-9), 0.08, 1.0)
    _, y = istft(Z * ganho, sr, nperseg=1024)
    return y[: len(x)].astype(np.float32)


def analisar(x: np.ndarray, sr: int = SR) -> list[str]:
    avisos = []
    dur = len(x) / sr
    if dur < 3:
        avisos.append(f"Muito curto ({dur:.1f} s). Use pelo menos 6 s de fala limpa.")
    elif dur < IDEAL_MIN:
        avisos.append(f"Curto ({dur:.1f} s). Entre 6 e 20 s costuma dar o melhor resultado.")
    if len(x) and float(np.max(np.abs(x))) >= 0.999:
        avisos.append("Áudio estourado (clipping). Prefira uma gravação com volume menor.")
    passo = int(sr * 0.05)
    n = len(x) // passo
    if n > 10:
        rms = np.sqrt(np.mean(x[: n * passo].reshape(n, passo) ** 2, axis=1) + 1e-12)
        db = 20 * np.log10(rms + 1e-9)
        if np.percentile(db, 90) - np.percentile(db, 8) < 18:
            avisos.append("Pouca diferença entre fala e fundo: ruído ou música ao fundo. Tente 'Reduzir ruído'.")
    return avisos


def importar(origem: Path, nome_voz: str, inicio: float = 0.0, fim: float | None = None,
             reduzir_ruido: bool = False, normalizar: bool = True) -> Relatorio:
    """Lê `origem`, prepara e grava em vozes\\referencias\\<nome-voz>.wav."""
    caminhos.garantir()
    x = ffmpeg.ler_audio(Path(origem), SR)
    i0 = int(max(0.0, inicio) * SR)
    i1 = int(fim * SR) if fim else len(x)
    x = x[i0:i1]
    x = _cortar_silencio(x, SR)
    if reduzir_ruido:
        x = _reduzir_ruido(x, SR)
    if len(x) > MAX_SEGUNDOS * SR:
        x = x[: int(MAX_SEGUNDOS * SR)]
    avisos = analisar(x)
    if normalizar and len(x):
        pico = float(np.max(np.abs(x))) or 1.0
        x = x * (0.89 / pico)
    destino = caminhos.REFERENCIAS / f"{caminhos.nome_seguro(nome_voz)}.wav"
    sf.write(str(destino), x, SR, subtype="PCM_16")
    return Relatorio(arquivo=destino, duracao=len(x) / SR, avisos=avisos)
