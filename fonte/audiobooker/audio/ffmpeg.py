"""Localiza o ffmpeg (do PATH ou o empacotado pelo imageio-ffmpeg) e decodifica qualquer áudio."""
from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW


@lru_cache(maxsize=1)
def exe() -> str:
    achado = shutil.which("ffmpeg")
    if achado:
        return achado
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def rodar(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([exe(), "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True,
                          text=True, timeout=timeout, creationflags=SEM_JANELA)


def ler_audio(caminho: Path, sr: int = 24000, mono: bool = True) -> np.ndarray:
    """Decodifica qualquer formato (mp3, m4a, ogg, flac, wav, mp4...) para float32 mono em `sr`."""
    cmd = [exe(), "-hide_banner", "-loglevel", "error", "-i", str(caminho), "-vn", "-ac", "1" if mono else "2",
           "-ar", str(sr), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True, creationflags=SEM_JANELA)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"Não consegui ler o áudio: {caminho.name}\n{r.stderr.decode('utf-8', 'ignore')[:300]}")
    return np.frombuffer(r.stdout, dtype=np.float32).copy()
