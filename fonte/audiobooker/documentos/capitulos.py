"""Do documento lido para a lista de capítulos que viram faixas do audiobook."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..texto.limpeza import QUEBRA_CENA, limpar
from .modelo import Bloco, Documento, Secao

_EXCLUIR = re.compile(
    r"^\W*(cover|title page|half title|copyright|contents|table of contents|toc|dedication|acknowledg\w*|about the author|"
    r"also by|e-?reader|epub|index|bibliography|colophon|capa|folha de rosto|sum[áa]rio|[íi]ndice|agradecimentos|sobre o autor|"
    r"direitos autorais|cr[ée]ditos)\b", re.IGNORECASE)
_ROMANO = re.compile(r"^(?=[ivxlcdm]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.IGNORECASE)
_VALORES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


@dataclass
class Capitulo:
    id: str
    titulo: str
    texto: str
    incluir: bool = True
    nota: str = ""

    @property
    def palavras(self) -> int:
        return len(self.texto.split())


def _romano_para_arabico(s: str) -> int:
    s = s.lower()
    total = 0
    for i, c in enumerate(s):
        v = _VALORES[c]
        total += -v if i + 1 < len(s) and _VALORES[s[i + 1]] > v else v
    return total


def _falar_titulo(t: str) -> str:
    t = t.strip()
    if _ROMANO.match(t) and len(t) <= 8 and t.lower() not in ("mix", "mild", "dim", "mid", "civil", "livid", "lid", "did", "mild"):
        return str(_romano_para_arabico(t))
    return t


def _texto_do_bloco(b: Bloco, idioma: str = "en") -> str:
    if b.texto == QUEBRA_CENA:
        return QUEBRA_CENA
    if b.tipo == "titulo":
        t = _falar_titulo(b.texto)
        return t if re.search(r"[.!?:]$", t) else t + "."
    return limpar(b.texto, idioma)


def _montar(blocos: list[Bloco], pular_primeiro_titulo: str | None, idioma: str = "en") -> str:
    partes = []
    for i, b in enumerate(blocos):
        if i == 0 and b.tipo == "titulo" and pular_primeiro_titulo and b.texto.strip().lower() == pular_primeiro_titulo.strip().lower():
            continue
        t = _texto_do_bloco(b, idioma)
        if t:
            partes.append(t)
    return "\n\n".join(partes)


def _titulo_limpo(t: str) -> str:
    t = re.sub(r"\s+", " ", t).replace(chr(0xFFFD), chr(0x2019)).strip()
    if t.isupper() and len(t) > 3:
        palavras = []
        pequenas = {"of", "on", "the", "and", "in", "to", "a", "an", "for", "at", "by", "de", "da", "do", "das", "dos", "e", "em", "o", "a", "os", "as"}
        for i, w in enumerate(t.split(" ")):
            if re.fullmatch(r"[IVXLCDM]{1,5}", w):
                palavras.append(w)
            elif i > 0 and w.lower() in pequenas:
                palavras.append(w.lower())
            else:
                palavras.append(w[:1] + w[1:].lower())
        t = " ".join(palavras)
    return t


def detectar(doc: Documento, max_palavras: int = 6000, idioma: str = "en") -> list[Capitulo]:
    capitulos: list[Capitulo] = []
    for sec in doc.secoes:
        titulo = _titulo_limpo(sec.titulo)
        excluir = bool(_EXCLUIR.match(sec.titulo)) or (sec.palavras < 40 and len(doc.secoes) > 1)
        nota = "Parece material do livro (capa, direitos, nota do ebook): desmarcado." if excluir else ""
        subs = [i for i, b in enumerate(sec.blocos) if b.tipo == "titulo" and i > 0 and b.nivel >= 2]
        if sec.palavras > max_palavras and len(subs) >= 4:
            for grupo in _dividir(sec, subs, max_palavras, titulo, idioma):
                grupo.incluir = not excluir
                grupo.nota = nota
                capitulos.append(grupo)
        else:
            capitulos.append(Capitulo("", titulo, _montar(sec.blocos, sec.titulo, idioma), not excluir, nota))
    for i, c in enumerate(capitulos, 1):
        c.id = f"c{i:03d}"
    return capitulos


def _dividir(sec: Secao, subs: list[int], max_palavras: int, titulo: str, idioma: str = "en") -> list[Capitulo]:
    """Agrupa as subseções (ex.: parágrafos numerados §1…§693) em faixas de tamanho razoável."""
    limites = [0] + subs + [len(sec.blocos)]
    pedacos = [sec.blocos[limites[i]:limites[i + 1]] for i in range(len(limites) - 1)]
    grupos: list[list[Bloco]] = []
    atual: list[Bloco] = []
    palavras = 0
    alvo = max(800, max_palavras * 2 // 3)
    for p in pedacos:
        n = sum(len(b.texto.split()) for b in p if b.tipo == "texto")
        if atual and palavras + n > alvo:
            grupos.append(atual)
            atual, palavras = [], 0
        atual += p
        palavras += n
    if atual:
        grupos.append(atual)
    saida = []
    for k, g in enumerate(grupos, 1):
        subtitulos = [b.texto for b in g if b.tipo == "titulo" and b.nivel >= 2]
        curtos = subtitulos and all(len(s) <= 8 for s in subtitulos)
        if curtos:
            ini, fim = _falar_titulo(subtitulos[0]), _falar_titulo(subtitulos[-1])
            lig = "a" if idioma == "pt" else "to"
            nome = f"{titulo}, {ini}" if ini == fim else f"{titulo}, {ini} {lig} {fim}"
        elif subtitulos:
            nome = f"{titulo}, {'parte' if idioma == 'pt' else 'section'} {k}: {subtitulos[0]}"
        else:
            nome = f"{titulo}, {'parte' if idioma == 'pt' else 'section'} {k}"
        texto = _montar(g, sec.titulo, idioma)
        if len(texto.split()) > max_palavras * 1.6:
            partes = _cortar_por_paragrafos(texto, max(800, max_palavras * 2 // 3))
            for j, parte in enumerate(partes, 1):
                saida.append(Capitulo("", f"{nome} ({j}/{len(partes)})", parte))
        else:
            saida.append(Capitulo("", nome, texto))
    return saida


def _cortar_por_paragrafos(texto: str, alvo: int) -> list[str]:
    sep = chr(10) * 2
    paragrafos = texto.split(sep)
    total = sum(len(p.split()) for p in paragrafos)
    n = max(1, round(total / alvo))
    por_parte = total / n
    partes, atual, palavras = [], [], 0
    for p in paragrafos:
        atual.append(p)
        palavras += len(p.split())
        if palavras >= por_parte and len(partes) < n - 1:
            partes.append(sep.join(atual))
            atual, palavras = [], 0
    if atual:
        partes.append(sep.join(atual))
    return partes
