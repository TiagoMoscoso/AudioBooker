"""Vozes externas para baixar: catálogo do Piper (rhasspy/piper-voices no Hugging Face), só inglês e português.

Cada voz é um arquivo .onnx (20–120 MB) que roda na CPU, muito rápido, com timbres bem diferentes do Kokoro (narradores,
sotaques). A licença varia por voz (a maioria é livre); ela aparece no cartão da voz em huggingface.co/rhasspy/piper-voices.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .. import caminhos

_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
PASTA = caminhos.MODELOS / "piper"
_CACHE = caminhos.CACHE / "piper-voices.json"
IDIOMAS = ("en", "pt")


@dataclass
class VozExterna:
    chave: str          # en_GB-alan-medium
    nome: str           # alan
    idioma: str         # en | pt
    regiao: str         # Reino Unido, Brasil...
    qualidade: str      # x_low | low | medium | high
    tamanho_mb: float
    falantes: int
    arquivos: dict

    @property
    def instalada(self) -> bool:
        return (PASTA / f"{self.chave}.onnx").exists()


def _ler_catalogo(forcar: bool = False) -> dict:
    caminhos.garantir()
    if not forcar and _CACHE.exists() and time.time() - _CACHE.stat().st_mtime < 7 * 86400:
        try:
            return json.loads(_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    with urllib.request.urlopen(_BASE + "voices.json", timeout=30) as r:
        dados = json.loads(r.read().decode("utf-8"))
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(dados), encoding="utf-8")
    return dados


def listar(forcar: bool = False) -> list[VozExterna]:
    """Vozes de uma pessoa só em inglês/português, da melhor qualidade para a pior."""
    saida = []
    ordem = {"high": 0, "medium": 1, "low": 2, "x_low": 3}
    for chave, d in _ler_catalogo(forcar).items():
        lang = d.get("language", {})
        familia = lang.get("family", "")
        if familia not in IDIOMAS or int(d.get("num_speakers", 1)) != 1:
            continue
        onnx = next((f for f in d.get("files", {}) if f.endswith(".onnx")), None)
        if not onnx:
            continue
        saida.append(VozExterna(chave=chave, nome=d.get("name", chave), idioma=familia,
                                regiao=lang.get("country_english", lang.get("region", "")), qualidade=d.get("quality", ""),
                                tamanho_mb=d["files"][onnx].get("size_bytes", 0) / 1e6, falantes=1, arquivos=d["files"]))
    saida.sort(key=lambda v: (v.idioma != "pt", v.regiao, ordem.get(v.qualidade, 9), v.nome))
    return saida


def baixar(v: VozExterna, progresso=None) -> Path:
    PASTA.mkdir(parents=True, exist_ok=True)
    for caminho_remoto in v.arquivos:
        if not (caminho_remoto.endswith(".onnx") or caminho_remoto.endswith(".onnx.json")):
            continue
        destino = PASTA / Path(caminho_remoto).name
        if destino.exists():
            continue
        tmp = destino.with_suffix(destino.suffix + ".parcial")
        with urllib.request.urlopen(_BASE + caminho_remoto, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            lido = 0
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
                lido += len(bloco)
                if progresso and total:
                    progresso(f"Baixando {v.chave}: {lido * 100 // total}%")
        tmp.replace(destino)
    return PASTA / f"{v.chave}.onnx"


def instaladas() -> list[str]:
    return sorted(p.stem for p in PASTA.glob("*.onnx")) if PASTA.exists() else []


def remover(chave: str) -> None:
    for sufixo in (".onnx", ".onnx.json"):
        (PASTA / f"{chave}{sufixo}").unlink(missing_ok=True)
