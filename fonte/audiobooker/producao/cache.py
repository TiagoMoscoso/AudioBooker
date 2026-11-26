"""Cache dos trechos já sintetizados (áudio seco, sem efeitos). Chave = texto final + voz + motor + parâmetros."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import caminhos

SR = 24000


def chave(texto_final: str, assinatura_voz: str, idioma: str, extra: str = "") -> str:
    return hashlib.sha1("\x1f".join([texto_final, assinatura_voz, idioma, extra]).encode("utf-8")).hexdigest()


def _arq(c: str) -> Path:
    return caminhos.CACHE / "trechos" / c[:2] / f"{c}.flac"


def ler(c: str) -> np.ndarray | None:
    arq = _arq(c)
    if not arq.exists():
        return None
    try:
        x, sr = sf.read(str(arq), dtype="float32")
        return x if sr == SR else None
    except Exception:  # noqa: BLE001 - arquivo corrompido: gera de novo
        arq.unlink(missing_ok=True)
        return None


def gravar(c: str, audio: np.ndarray) -> None:
    arq = _arq(c)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp.flac")
    sf.write(str(tmp), audio, SR, format="FLAC", subtype="PCM_24")
    tmp.replace(arq)


def tamanho_mb() -> float:
    pasta = caminhos.CACHE / "trechos"
    return sum(f.stat().st_size for f in pasta.rglob("*.flac")) / 1e6 if pasta.exists() else 0.0


def limpar() -> None:
    shutil.rmtree(caminhos.CACHE / "trechos", ignore_errors=True)
