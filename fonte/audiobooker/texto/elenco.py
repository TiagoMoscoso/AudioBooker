"""Elenco: separa narração de falas, descobre quem fala (aspas “…”, "…" e travessão do português) e sugere o estilo de cada fala
pelo contexto ("she whispered softly").

Também aceita roteiro explícito: uma linha `@Nome: texto` faz o personagem Nome falar aquela linha.
"""
from __future__ import annotations

import re
from collections import Counter

from . import contexto

NARRADOR = "narrador"
FALA = "fala"  # fala sem nome identificado

_VERBOS = (r"said|asked|replied|answered|cried|whispered|shouted|exclaimed|murmured|added|continued|muttered|"
           r"called|demanded|declared|observed|remarked|retorted|sighed|laughed|growled|snapped|yelled|"
           r"disse|perguntou|respondeu|gritou|sussurrou|exclamou|murmurou|acrescentou|continuou|replicou|"
           r"falou|declarou|observou|suspirou|ordenou|insistiu|rosnou")
_NOME = r"([A-ZÀ-Ý][\wà-ÿ’'.-]+(?:\s+(?:de|da|do|van|von|of)?\s*[A-ZÀ-Ý][\wà-ÿ’'.-]+)?)"
_DEPOIS = re.compile(rf"^[\s,.!?…]*(?:{_VERBOS})\s+(?:the\s+|o\s+|a\s+)?{_NOME}|^[\s,.!?…]*{_NOME}\s+(?:{_VERBOS})\b", re.UNICODE)
_ANTES = re.compile(rf"{_NOME}\s+(?:{_VERBOS})[\s,:]*$", re.UNICODE)
_ASPAS = re.compile(r"“[^”]{1,700}”|\"[^\"]{1,700}\"")
_ROTEIRO = re.compile(r"^@([^:\n]{1,40}):\s*(.+)$")
_PRONOMES = {"he", "she", "it", "they", "i", "we", "you", "ele", "ela", "eles", "elas", "eu", "nós"}

Segmento = tuple[str, str, str]  # (papel, texto, estilo sugerido ou "")


def _nome_valido(n: str | None) -> str | None:
    if not n:
        return None
    n = n.strip(" .,’'")
    if n.lower() in _PRONOMES or len(n) < 2:
        return None
    return n


def eh_roteiro(paragrafo: str) -> bool:
    """Linha `@Nome: texto` (roteiro editado à mão): o papel dela vale mesmo sem a opção de separar falas."""
    return bool(_ROTEIRO.match(paragrafo))


def gerar_roteiro(texto: str, usar_contexto: bool = True) -> str:
    """Texto do capítulo -> roteiro editável: um parágrafo por papel, `@papel: [estilo x]fala[/estilo]`. Para a revisão manual."""
    saida: list[str] = []
    ultimo: list[str] = []
    for par in re.split(r"\n\s*\n", texto):
        par = par.strip()
        if not par:
            continue
        if eh_roteiro(par) or par.startswith("["):
            saida.append(par)
            continue
        for papel, t, estilo in segmentar_com_estilo(par, ultimo, usar_contexto):
            corpo = f"[estilo {estilo}]{t}[/estilo]" if estilo else t
            saida.append(f"@{papel}: {corpo}")
    return "\n\n".join(saida)


def segmentar_com_estilo(paragrafo: str, ultimo: list[str] | None = None, usar_contexto: bool = True) -> list[Segmento]:
    """Lista de (papel, texto, estilo) na ordem. `ultimo` guarda o último falante nomeado (para "he said")."""
    m = _ROTEIRO.match(paragrafo)
    if m:
        return [(m.group(1).strip(), m.group(2).strip(), "")]
    if re.match(r"^\s*[—–]\s*\S", paragrafo):
        return _segmentar_travessao(paragrafo, usar_contexto)
    if not _ASPAS.search(paragrafo):
        return [(NARRADOR, paragrafo, "")]
    saida: list[Segmento] = []
    pos = 0
    for q in _ASPAS.finditer(paragrafo):
        antes = paragrafo[pos:q.start()]
        depois = paragrafo[q.end():q.end() + 90]
        nome = None
        md = _DEPOIS.match(depois)
        if md:
            nome = _nome_valido(md.group(1) or md.group(2))
        if not nome:
            ma = _ANTES.search(paragrafo[max(0, q.start() - 70):q.start()])
            if ma:
                nome = _nome_valido(ma.group(1))
        if antes.strip():
            saida.append((NARRADOR, antes.strip(), ""))
        papel = nome or FALA
        if nome and ultimo is not None:
            ultimo[:] = [nome]
        estilo = contexto.estilo_de(depois, paragrafo[max(0, q.start() - 70):q.start()]) if usar_contexto else ""
        saida.append((papel, q.group(0), estilo))
        pos = q.end()
    resto = paragrafo[pos:].strip()
    if resto:
        saida.append((NARRADOR, resto, ""))
    return _fundir(saida)


def segmentar(paragrafo: str, ultimo: list[str] | None = None) -> list[tuple[str, str]]:
    """Compatível com o uso antigo: (papel, texto)."""
    return [(p, t) for p, t, _e in segmentar_com_estilo(paragrafo, ultimo, usar_contexto=False)]


def _segmentar_travessao(p: str, usar_contexto: bool) -> list[Segmento]:
    partes = re.split(r"\s+[—–]\s+", re.sub(r"^\s*[—–]\s*", "", p))
    saida: list[Segmento] = []
    ultima_fala = -1
    for i, parte in enumerate(partes):
        parte = parte.strip()
        if not parte:
            continue
        eh_narracao = i % 2 == 1 and re.match(rf"^(?:{_VERBOS})\b|^{_NOME}\s+(?:{_VERBOS})", parte)
        if eh_narracao:
            if usar_contexto and ultima_fala >= 0 and not saida[ultima_fala][2]:
                papel, txt, _ = saida[ultima_fala]
                saida[ultima_fala] = (papel, txt, contexto.estilo_de(parte))
            saida.append((NARRADOR, parte, ""))
        else:
            ultima_fala = len(saida)
            saida.append((FALA, parte, ""))
    return _fundir(saida) or [(FALA, p, "")]


def _fundir(seg: list[Segmento]) -> list[Segmento]:
    saida: list[Segmento] = []
    for papel, txt, estilo in seg:
        if saida and saida[-1][0] == papel and saida[-1][2] == estilo:
            saida[-1] = (papel, saida[-1][1] + " " + txt, estilo)
        else:
            saida.append((papel, txt, estilo))
    return saida


def descobrir_falantes(paragrafos: list[str]) -> Counter:
    """Quantas falas cada nome tem no livro (para a tela de elenco)."""
    cont: Counter = Counter()
    ultimo: list[str] = []
    for p in paragrafos:
        for papel, _t, _e in segmentar_com_estilo(p, ultimo, usar_contexto=False):
            if papel not in (NARRADOR, FALA):
                cont[papel] += 1
            elif papel == FALA:
                cont[FALA] += 1
    return cont
