"""Onde ficam as coisas.

Dados do usuário (vozes salvas e dicionários de pronúncia): pastas `vozes\\` e `dicionarios\\` ao lado de `fonte\\`
(ignoradas pelo git); mude o lugar com a variável de ambiente AUDIOBOOKER_DADOS.
Dados da instalação (modelos, ambiente Python, projetos, cache, biblioteca, configuração): %LOCALAPPDATA%\\AUDIOBOOKER;
mude com AUDIOBOOKER_LOCAL.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # pasta que contém `fonte\`
DADOS = Path(os.environ.get("AUDIOBOOKER_DADOS") or RAIZ)
VOZES = DADOS / "vozes"
REFERENCIAS = VOZES / "referencias"
DICIONARIOS = DADOS / "dicionarios"

LOCAL = Path(os.environ.get("AUDIOBOOKER_LOCAL") or (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AUDIOBOOKER"))
MODELOS = LOCAL / "modelos"
PROJETOS = LOCAL / "projetos"
CACHE = LOCAL / "cache"
BIBLIOTECA = LOCAL / "biblioteca"
FRASES = LOCAL / "frases"
LOGS = LOCAL / "logs"
CONFIGURACAO = LOCAL / "configuracao.json"


def garantir() -> None:
    for pasta in (VOZES, REFERENCIAS, DICIONARIOS, LOCAL, MODELOS, PROJETOS, CACHE, BIBLIOTECA, FRASES, LOGS):
        pasta.mkdir(parents=True, exist_ok=True)


def nome_seguro(texto: str, limite: int = 80) -> str:
    """Nome de arquivo ASCII, minúsculo, com hífen."""
    import re
    import unicodedata

    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return (base or "sem-nome")[:limite].strip("-")
