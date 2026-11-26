"""Divide o capítulo em trechos que o motor aguenta, sem cortar frase, abreviação ou fala no meio,
guardando que tipo de pausa vem antes de cada trecho."""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import direcoes as _dir
from . import elenco as _elenco
from .direcoes import Direcao
from .limpeza import QUEBRA_CENA

_PAUSA = re.compile(r"\[\s*(?:pausa|pause)\s+([\d.,]+)\s*(ms|s)?\s*\]", re.IGNORECASE)
_FRONTEIRA = re.compile(r"(?<=[.!?…])[”’\"')\]]*\s+(?=[“‘\"'(\[]?[A-ZÀ-Ý0-9])")
_CLAUSULA = re.compile(r"(?<=[,;:—])\s+")
_ULTIMA_PALAVRA = re.compile(r"([A-Za-zÀ-ÿ.]+)[.]?$")


@dataclass(frozen=True)
class Trecho:
    texto: str
    antes: str = "frase"        # frase | paragrafo | cena | capitulo
    papel: str = _elenco.NARRADOR
    pausa: float = 0.0          # > 0: silêncio explícito (tag [pausa 2s]); texto vazio
    direcao: Direcao = Direcao()  # intonação deste trecho (estilo, emoção, velocidade, tom, volume...)


def _frases(paragrafo: str, abreviacoes: frozenset[str]) -> list[str]:
    partes = _FRONTEIRA.split(paragrafo)
    saida, buf = [], ""
    for p in partes:
        cand = f"{buf} {p}".strip() if buf else p.strip()
        m = _ULTIMA_PALAVRA.search(cand.rstrip("”’\"')]"))
        palavra = m.group(1).lower().rstrip(".") if m else ""
        if cand.endswith(".") and palavra in abreviacoes and not cand.endswith(("..", "…")):
            buf = cand
            continue
        buf = ""
        saida.append(cand)
    if buf:
        saida.append(buf)
    return [s for s in saida if s]


def _quebrar_longa(frase: str, limite: int) -> list[str]:
    partes = _CLAUSULA.split(frase)
    saida, atual = [], ""
    for parte in partes:
        cand = f"{atual} {parte}".strip() if atual else parte
        if len(cand) <= limite:
            atual = cand
            continue
        if atual:
            saida.append(atual)
            atual = ""
        if len(parte) > limite:
            palavras, linha = parte.split(), ""
            for w in palavras:
                c = f"{linha} {w}".strip()
                if len(c) <= limite:
                    linha = c
                else:
                    if linha:
                        saida.append(linha)
                    linha = w
            atual = linha
        else:
            atual = parte
    if atual:
        saida.append(atual)
    return saida


def _empacotar(frases: list[str], alvo: int, limite: int) -> list[str]:
    saida, atual = [], ""
    for f in frases:
        if len(f) > limite:
            if atual:
                saida.append(atual)
                atual = ""
            saida.extend(_quebrar_longa(f, limite))
            continue
        cand = f"{atual} {f}".strip() if atual else f
        if len(cand) <= alvo or not atual:
            atual = cand
        else:
            saida.append(atual)
            atual = f
    if atual:
        saida.append(atual)
    return saida


def dividir(texto: str, abreviacoes: frozenset[str], alvo: int = 260, limite: int = 380,
            separar_falas: bool = False, usar_contexto: bool = True, base: Direcao | None = None) -> list[Trecho]:
    """`separar_falas`: quebra cada parágrafo em narração × fala (vozes de elenco diferentes).
    `usar_contexto`: sugere o estilo de cada fala pelo entorno ("she whispered"). A marcação [estilo]/[emoção]/... do texto vence."""
    trechos: list[Trecho] = []
    antes = "capitulo"
    ultimo: list[str] = []
    base = base or Direcao()
    for paragrafo in re.split(r"\n\s*\n", texto):
        paragrafo = paragrafo.strip()
        if not paragrafo:
            continue
        if paragrafo == QUEBRA_CENA:
            antes = "cena"
            continue
        if separar_falas or usar_contexto:
            segmentos = _elenco.segmentar_com_estilo(paragrafo, ultimo, usar_contexto)
            if not separar_falas and not _elenco.eh_roteiro(paragrafo):
                segmentos = [(_elenco.NARRADOR, t, e) for _p, t, e in segmentos]
        else:
            segmentos = [(_elenco.NARRADOR, paragrafo, "")]
        primeiro_do_paragrafo = True
        for papel, seg, estilo in segmentos:
            for peca in _dir.interpretar(seg, base.mesclar(Direcao(estilo=estilo))):
                if peca.pausa > 0:
                    trechos.append(Trecho("", antes="frase", papel=papel, pausa=peca.pausa))
                    continue
                txt = peca.texto.strip()
                if not txt:
                    continue
                for i, t in enumerate(_empacotar(_frases(txt, abreviacoes), alvo, limite)):
                    if i == 0 and primeiro_do_paragrafo:
                        marca = antes if antes in ("cena", "capitulo") else "paragrafo"
                    else:
                        marca = "frase"
                    trechos.append(Trecho(t, antes=marca, papel=papel, direcao=peca.direcao))
                    primeiro_do_paragrafo = False
                    antes = "paragrafo"
        antes = "paragrafo"
    if trechos:
        t0 = trechos[0]
        trechos[0] = Trecho(t0.texto, "capitulo", t0.papel, t0.pausa, t0.direcao)
    return trechos
