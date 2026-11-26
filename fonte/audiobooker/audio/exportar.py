"""Saídas do audiobook: M4B com capítulos e capa, MP3/FLAC/WAV por capítulo (com etiquetas)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from .. import caminhos
from . import ffmpeg

SR = 24000


@dataclass
class FaixaPronta:
    titulo: str
    arquivo_wav: Path
    duracao: float


def _meta_arg(titulo: str, autor: str, album: str, faixa: int | None = None, total: int | None = None) -> list[str]:
    args = ["-metadata", f"title={titulo}", "-metadata", f"artist={autor}", "-metadata", f"album={album}",
            "-metadata", f"album_artist={autor}", "-metadata", "genre=Audiobook"]
    if faixa:
        args += ["-metadata", f"track={faixa}/{total or faixa}"]
    return args


def _escapar_meta(t: str) -> str:
    for c in ("\\", "=", ";", "#", "\n"):
        t = t.replace(c, "\\" + c)
    return t


def exportar_m4b(faixas: list[FaixaPronta], destino: Path, titulo: str, autor: str, capa: bytes | None = None,
                 kbps: int = 64) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audiobooker_") as tmp:
        tmp = Path(tmp)
        lista = tmp / "lista.txt"
        lista.write_text("\n".join("file '" + str(f.arquivo_wav).replace("'", "'\\''") + "'" for f in faixas), encoding="utf-8")
        meta = [";FFMETADATA1", f"title={_escapar_meta(titulo)}", f"artist={_escapar_meta(autor)}",
                f"album={_escapar_meta(titulo)}", "genre=Audiobook"]
        t = 0
        for f in faixas:
            fim = t + int(round(f.duracao * 1000))
            meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={t}", f"END={fim}", f"title={_escapar_meta(f.titulo)}"]
            t = fim
        (tmp / "capitulos.txt").write_text("\n".join(meta) + "\n", encoding="utf-8")
        cmd = ["-f", "concat", "-safe", "0", "-i", str(lista), "-i", str(tmp / "capitulos.txt")]
        if capa:
            ext = ".png" if capa[:4] == b"\x89PNG" else ".jpg"
            (tmp / f"capa{ext}").write_bytes(capa)
            cmd += ["-i", str(tmp / f"capa{ext}")]
        cmd += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
        if capa:
            cmd += ["-map", "2:v", "-c:v", "copy", "-disposition:v", "attached_pic"]
        cmd += ["-c:a", "aac", "-b:a", f"{kbps}k", "-ac", "1", "-ar", "44100", "-movflags", "+faststart", "-f", "ipod", str(destino)]
        r = ffmpeg.rodar(cmd)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou ao criar o M4B: {r.stderr[:400]}")
    return destino


def exportar_faixa(wav: Path, destino: Path, formato: str, titulo: str, autor: str, album: str, numero: int, total: int,
                   acx: bool = False) -> Path:
    formato = formato.lower()
    destino = destino.with_suffix("." + formato)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if formato == "wav":
        import shutil

        shutil.copyfile(wav, destino)
        return destino
    cmd = ["-i", str(wav), *_meta_arg(titulo, autor, album, numero, total)]
    if formato == "mp3":
        cmd += (["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "1"] if acx else ["-c:a", "libmp3lame", "-q:a", "3", "-ac", "1"])
    elif formato == "flac":
        cmd += ["-c:a", "flac"]
    elif formato == "m4a":
        cmd += ["-c:a", "aac", "-b:a", "64k", "-ac", "1"]
    else:
        raise ValueError(f"Formato não suportado: {formato}")
    cmd.append(str(destino))
    r = ffmpeg.rodar(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ao criar {destino.name}: {r.stderr[:300]}")
    return destino


def gravar_wav(x, destino: Path, sr: int = SR) -> float:
    destino.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(destino), x, sr, subtype="PCM_16")
    return len(x) / sr
