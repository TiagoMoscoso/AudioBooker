"""Dicionário de pronúncias (recurso padrão de produtoras de audiobook).

Camadas, da mais fraca para a mais forte:  embutido  <  global (dicionarios\\global.json)  <  do livro (dicionarios\\livros\\<id>.json)

Cada entrada pode ter:
  respelling  grafia sonora ("Nietzsche" -> "Nee-chuh"): funciona em qualquer motor
  ipa         fonemas IPA ("ˈniːtʃə"): mais preciso, só o Kokoro usa (no Chatterbox vale o respelling)
Tipos: palavra, regex, abreviacao (casa com o ponto final: "Dr." -> "Doctor").
Importa e exporta no formato padrão W3C PLS (.pls), o mesmo de outras ferramentas de produção.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import caminhos

_PLS_NS = "http://www.w3.org/2005/01/pronunciation-lexicon"


@dataclass
class Entrada:
    palavra: str
    respelling: str = ""
    ipa: str = ""
    tipo: str = "palavra"       # palavra | regex | abreviacao
    idioma: str = "*"           # en | pt | *
    sensivel: bool = False      # diferencia maiúsculas
    nota: str = ""

    def valida(self) -> bool:
        return bool(self.palavra.strip()) and bool(self.respelling.strip() or self.ipa.strip())


def _a(p, r, idioma="en") -> Entrada:
    return Entrada(p, respelling=r, tipo="abreviacao", idioma=idioma)


_EMBUTIDAS: list[Entrada] = [
    _a("Mr", "Mister"), _a("Mrs", "Missus"), _a("Ms", "Miss"), _a("Dr", "Doctor"), _a("Prof", "Professor"),
    _a("Jr", "Junior"), _a("vs", "versus"), _a("etc", "et cetera"), _a("e.g", "for example"), _a("i.e", "that is"),
    _a("cf", "compare"), _a("viz", "namely"), _a("Ibid", "ibidem"), _a("pp", "pages"), _a("Fig", "Figure"),
    Entrada(r"(?<![\w.])p\.\s*(?=\d)", respelling="page ", tipo="regex", idioma="en", nota="p. 12"),
    Entrada(r"(?<![\w.])No\.\s*(?=\d)", respelling="number ", tipo="regex", idioma="en", nota="No. 5"),
    Entrada(r"(?<![\w.])n[ºo°]\.?\s*(?=\d)", respelling="número ", tipo="regex", idioma="pt", nota="nº 5"),
    _a("Sr", "Senhor", "pt"), _a("Sra", "Senhora", "pt"), _a("Dr", "Doutor", "pt"), _a("Dra", "Doutora", "pt"),
    _a("Prof", "Professor", "pt"), _a("Profa", "Professora", "pt"), _a("pág", "página", "pt"), _a("págs", "páginas", "pt"),
    _a("etc", "etcétera", "pt"), _a("ex", "exemplo", "pt"), _a("obs", "observação", "pt"), _a("cf", "conferir", "pt"),
    _a("av", "avenida", "pt"), _a("Ltda", "limitada", "pt"),
]
_SO_PROTEGE = {"p", "no", "vol", "ed", "ch", "st", "mt", "sec", "al", "inc", "ltd", "co", "approx", "dept", "est"}


def _arq_global() -> Path:
    return caminhos.DICIONARIOS / "global.json"


def _arq_livro(livro_id: str) -> Path:
    return caminhos.DICIONARIOS / "livros" / f"{caminhos.nome_seguro(livro_id)}.json"


def _ler(arq: Path) -> list[Entrada]:
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        return [Entrada(**{k: v for k, v in d.items() if k in Entrada.__dataclass_fields__}) for d in dados.get("entradas", [])]
    except (OSError, ValueError, TypeError):
        return []


def _gravar(arq: Path, entradas: list[Entrada]) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps({"entradas": [asdict(e) for e in entradas]}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(arq)


def carregar_global() -> list[Entrada]:
    return _ler(_arq_global())


def salvar_global(entradas: list[Entrada]) -> None:
    _gravar(_arq_global(), [e for e in entradas if e.valida()])


def carregar_livro(livro_id: str) -> list[Entrada]:
    return _ler(_arq_livro(livro_id))


def salvar_livro(livro_id: str, entradas: list[Entrada]) -> None:
    _gravar(_arq_livro(livro_id), [e for e in entradas if e.valida()])


class Dicionario:
    """Dicionário já mesclado para um idioma (e opcionalmente um livro)."""

    def __init__(self, idioma: str, livro_id: str | None = None) -> None:
        self.idioma = idioma
        camadas = [_EMBUTIDAS, carregar_global()] + ([carregar_livro(livro_id)] if livro_id else [])
        por_chave: dict[tuple, Entrada] = {}
        for camada in camadas:
            for e in camada:
                if e.idioma not in ("*", idioma):
                    continue
                por_chave[(e.tipo, e.palavra if e.sensivel else e.palavra.lower())] = e
        self.entradas = list(por_chave.values())

    # ---- consultas
    def abreviacoes(self) -> frozenset[str]:
        base = {e.palavra.lower().rstrip(".") for e in self.entradas if e.tipo == "abreviacao"}
        return frozenset(base | _SO_PROTEGE)

    def mapa_ipa(self) -> dict[str, str]:
        return {e.palavra.lower(): e.ipa for e in self.entradas if e.tipo == "palavra" and e.ipa.strip()}

    # ---- aplicação
    def aplicar(self, texto: str, usar_ipa: bool) -> str:
        """Troca por grafia sonora. Com `usar_ipa`, palavras que têm IPA ficam intactas (o motor as fonemiza)."""
        ordem = sorted(self.entradas, key=lambda e: len(e.palavra), reverse=True)
        for e in ordem:
            if not e.respelling.strip():
                continue
            if usar_ipa and e.ipa.strip() and e.tipo == "palavra":
                continue
            flags = 0 if e.sensivel else re.IGNORECASE
            if e.tipo == "regex":
                padrao = re.compile(e.palavra, flags)
            elif e.tipo == "abreviacao":
                padrao = re.compile(rf"(?<![\w.]){re.escape(e.palavra)}\.", flags)
            else:
                padrao = re.compile(rf"(?<![\w’'-]){re.escape(e.palavra)}(?![\w-])", flags)
            texto = padrao.sub(lambda m, r=e.respelling: r, texto)
        return texto


# ---- PLS (W3C) -------------------------------------------------------------------------------------------
def exportar_pls(entradas: list[Entrada], destino: Path, idioma: str = "en-US") -> None:
    ET.register_namespace("", _PLS_NS)
    raiz = ET.Element(f"{{{_PLS_NS}}}lexicon", {"version": "1.0", "alphabet": "ipa", "{http://www.w3.org/XML/1998/namespace}lang": idioma})
    for e in entradas:
        if e.tipo != "palavra":
            continue
        lex = ET.SubElement(raiz, f"{{{_PLS_NS}}}lexeme")
        ET.SubElement(lex, f"{{{_PLS_NS}}}grapheme").text = e.palavra
        if e.ipa:
            ET.SubElement(lex, f"{{{_PLS_NS}}}phoneme").text = e.ipa
        elif e.respelling:
            ET.SubElement(lex, f"{{{_PLS_NS}}}alias").text = e.respelling
    ET.ElementTree(raiz).write(destino, encoding="utf-8", xml_declaration=True)


def importar_pls(arquivo: Path, idioma: str = "*") -> list[Entrada]:
    ns = {"p": _PLS_NS}
    raiz = ET.parse(arquivo).getroot()
    saida = []
    for lex in raiz.findall("p:lexeme", ns):
        graf = [g.text.strip() for g in lex.findall("p:grapheme", ns) if g.text]
        fon = lex.find("p:phoneme", ns)
        ali = lex.find("p:alias", ns)
        for g in graf:
            e = Entrada(g, ipa=(fon.text or "").strip() if fon is not None else "",
                        respelling=(ali.text or "").strip() if ali is not None else "", idioma=idioma)
            if e.valida():
                saida.append(e)
    return saida


# ---- sugestões a partir do texto ---------------------------------------------------------------------------
def candidatos(texto: str, idioma: str, ja_tem: set[str] | None = None, limite: int = 80) -> list[tuple[str, int, str]]:
    """Termos que costumam sair errados: palavras fora do dicionário do idioma (nomes, jargão, estrangeirismos) e siglas."""
    ja_tem = {x.lower() for x in (ja_tem or set())}
    try:
        from spellchecker import SpellChecker

        dic = SpellChecker(language=idioma if idioma in ("en", "es", "fr", "pt", "de", "it") else "en")
    except Exception:  # noqa: BLE001 - sem o corretor, só siglas e acentos
        dic = None
    cont: Counter[str] = Counter()
    motivo: dict[str, str] = {}
    for m in re.finditer(r"\b[\wÀ-ÿ][\wÀ-ÿ’'-]{1,}\b", texto):
        w = m.group(0).strip("’'-")
        if len(w) < 2 or any(ch.isdigit() for ch in w):
            continue
        baixa = w.lower().replace("’", "'")
        if dic is not None:
            base = re.sub(r"(n't|'s|'ll|'re|'ve|'d|'m)$", "", baixa)
            if all((parte in dic or parte == "" or len(parte) < 2) for parte in re.split("-", base)) or baixa in dic:
                continue
        if w.isupper() and len(w) <= 7:
            cont[w] += 1
            motivo.setdefault(w, "sigla")
        elif dic is not None:
            cont[w] += 1
            motivo.setdefault(w, "fora do dicionário (nome, termo técnico ou palavra estrangeira)")
        elif w[0].isupper() or re.search(r"[À-ÿ]", w):
            cont[w] += 1
            motivo.setdefault(w, "nome próprio ou acento")
    saida = [(w, c, motivo[w]) for w, c in cont.most_common() if w.lower() not in ja_tem and (c >= 2 or motivo[w] == "sigla" or len(w) >= 6)]
    return saida[:limite]
