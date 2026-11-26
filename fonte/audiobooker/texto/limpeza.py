"""Limpeza do texto antes de falar: símbolos, notas, links, hifenização, quebras de cena."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

QUEBRA_CENA = "⁣CENA⁣"

_TROCAS = {" ": " ", "​": "", "﻿": "", "­": "", " ": "\n", " ": "\n\n",
           "‘": "‘", "’": "’"}
_URL = re.compile(r"https?://\S+|www\.\S+")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_NOTA_COLCHETE = re.compile(r"\[(?:\d{1,3}|[a-z]|\*+|†|‡)\]")
_NOTA_SOBRESCRITA = re.compile(r"(?<=[A-Za-zÀ-ÿ.,;:!?”’)])[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
_HIFEN_QUEBRA = re.compile(r"(\w)-\n(\w)")
_SO_SIMBOLOS = re.compile(r"^[\s*\-–—―_•·~=#.]{3,60}$")
_MARCADORES_MD = re.compile(r"(\*\*\*|\*\*|__|`)")
_REPETIDA = re.compile(r"([!?])\1{2,}")


def _consertar_substituicao(texto: str) -> str:
    """Caractere de substituição (U+FFFD) no lugar de aspas e apóstrofos: devolve o sinal certo pelo contexto."""
    r = chr(0xFFFD)
    if r not in texto:
        return texto
    texto = re.sub(r"(?<=\w)" + r + r"(?=\w)", chr(0x2019), texto)
    texto = re.sub(r"(^|[\s(\[—])" + r + r"(?=[\w(\[])", lambda m: m.group(1) + chr(0x201C), texto)
    texto = texto.replace(r, chr(0x201D))
    return texto


def limpar(texto: str, idioma: str = "en") -> str:
    texto = _consertar_substituicao(texto)
    texto = unicodedata.normalize("NFC", texto)
    for a, b in _TROCAS.items():
        texto = texto.replace(a, b)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = _HIFEN_QUEBRA.sub(r"\1\2", texto)
    texto = _URL.sub("", texto)
    texto = _EMAIL.sub("", texto)
    texto = _NOTA_COLCHETE.sub("", texto)
    texto = _NOTA_SOBRESCRITA.sub("", texto)
    texto = _MARCADORES_MD.sub("", texto)
    texto = _REPETIDA.sub(r"\1", texto)
    linhas = []
    for ln in texto.split("\n"):
        s = ln.strip()
        linhas.append(QUEBRA_CENA if s and _SO_SIMBOLOS.match(s) else re.sub(r"[^\S\n]+", " ", ln).strip())
    texto = "\n".join(linhas)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return reparar_palavras_partidas(texto, idioma).strip()


def unir_linhas_do_paragrafo(texto: str) -> str:
    """Texto de PDF/TXT: junta linhas soltas dentro do mesmo parágrafo."""
    saida = []
    for par in re.split(r"\n\s*\n", texto):
        saida.append(re.sub(r"\s*\n\s*", " ", par).strip())
    return "\n\n".join(p for p in saida if p)


_PAR_PALAVRAS = re.compile(r"\b([A-Za-z]{3,})(?= ([a-z]{2,10})\b)")


_FRAGMENTOS = {"ment", "ments", "tion", "tions", "sion", "sions", "ness", "ity", "ence", "ance", "ally", "ical"}


@lru_cache(maxsize=4)
def _corretor(idioma: str):
    try:
        from spellchecker import SpellChecker

        return SpellChecker(language=idioma if idioma in ("en", "es", "fr", "pt", "de", "it") else "en")
    except Exception:  # noqa: BLE001
        return None


def reparar_palavras_partidas(texto: str, idioma: str = "en") -> str:
    """Livros convertidos de PDF trazem 'proposi tion', 'descrip tion': junta quando a palavra inteira existe e a metade não."""
    dic = _corretor(idioma)
    if dic is None or idioma not in ("en", "es", "fr", "pt", "de", "it"):
        return texto

    saida, pos = [], 0
    for m in _PAR_PALAVRAS.finditer(texto):
        a, b = m.group(1), m.group(2)
        if m.start() < pos:
            continue
        fragmento = b.lower() in _FRAGMENTOS
        if (a + b).lower() in dic and (fragmento or (a.lower() not in dic and b.lower() not in dic)):
            saida.append(texto[pos:m.start()])
            saida.append(a + b)
            pos = m.end() + 1 + len(b)
    saida.append(texto[pos:])
    return "".join(saida)
