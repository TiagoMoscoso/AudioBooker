"""Leitura de livros: EPUB, PDF (com texto), DOCX, MOBI/AZW, TXT e Markdown."""
from __future__ import annotations

import posixpath
import re
import warnings
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..texto.limpeza import QUEBRA_CENA, limpar, unir_linhas_do_paragrafo
from .modelo import Bloco, Documento, ErroDocumento, Secao

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

FORMATOS = {".epub", ".pdf", ".docx", ".mobi", ".azw", ".azw3", ".txt", ".md", ".markdown"}
_TAGS_TEXTO = {"p", "li", "blockquote", "dd", "dt", "figcaption", "td", "pre", "div", "span"}
_TAGS_TITULO = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


def ler(caminho: Path) -> Documento:
    caminho = Path(caminho)
    ext = caminho.suffix.lower()
    if ext not in FORMATOS:
        raise ErroDocumento(f"Formato não suportado: {ext}. Use EPUB, PDF, DOCX, MOBI, TXT ou Markdown.")
    leitores = {".epub": _epub, ".pdf": _pdf, ".docx": _docx, ".mobi": _mobi, ".azw": _mobi, ".azw3": _mobi,
                ".txt": _txt, ".md": _md, ".markdown": _md}
    doc = leitores[ext](caminho)
    doc.formato, doc.origem = ext.lstrip("."), caminho
    doc.secoes = [s for s in doc.secoes if s.blocos]
    if doc.palavras < 20:
        raise ErroDocumento("Não encontrei texto neste arquivo. Se for um PDF escaneado, ele precisa de OCR antes.")
    return doc


# ---- EPUB -------------------------------------------------------------------------------------------------
def _blocos_html(corpo) -> list[Bloco]:
    for t in corpo.find_all(["script", "style", "nav", "svg", "img"]):
        t.decompose()
    for t in corpo.find_all(["sup", "a"]):
        if t.name == "sup" or "noteref" in (t.get("epub:type") or "") or "footnote" in (t.get("class") or []):
            t.decompose()
    blocos: list[Bloco] = []
    vistos: set[int] = set()
    for el in corpo.find_all(list(_TAGS_TITULO) + list(_TAGS_TEXTO)):
        if id(el) in vistos:
            continue
        if el.name in _TAGS_TITULO:
            t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if t:
                blocos.append(Bloco("titulo", t, _TAGS_TITULO[el.name]))
            continue
        if el.name in ("div", "span") and el.find(list(_TAGS_TITULO) + ["p", "li", "blockquote", "div"]):
            continue  # contêiner: o conteúdo é lido nos filhos
        for filho in el.find_all(True):
            vistos.add(id(filho))
        t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        t = re.sub(r"\s+([,.;:!?”’)])", r"\1", t)
        t = re.sub(r"([“‘(])\s+", r"\1", t)
        if t:
            blocos.append(Bloco("texto", QUEBRA_CENA if re.fullmatch(r"[\s*\-–—_•·~=#]{3,}", t) else t))
    return blocos


def _epub(caminho: Path) -> Documento:
    try:
        z = zipfile.ZipFile(caminho)
    except zipfile.BadZipFile as e:
        raise ErroDocumento("EPUB inválido ou corrompido.") from e
    with z:
        container = BeautifulSoup(z.read("META-INF/container.xml"), "xml")
        opf_path = container.find("rootfile")["full-path"]
        base = posixpath.dirname(opf_path)
        opf = BeautifulSoup(z.read(opf_path), "xml")
        meta = lambda nome: (opf.find(nome).get_text(strip=True) if opf.find(nome) else "")  # noqa: E731
        titulo, autor, idioma = meta("dc:title") or meta("title"), meta("dc:creator") or meta("creator"), meta("dc:language") or meta("language")
        itens = {i["id"]: i for i in opf.find_all("item")}
        ordem = [itens[r["idref"]]["href"] for r in opf.find_all("itemref") if r["idref"] in itens]

        titulos_toc: dict[str, str] = {}
        ncx = next((n for n in z.namelist() if n.endswith(".ncx")), None)
        if ncx:
            for np_ in BeautifulSoup(z.read(ncx), "xml").find_all("navPoint"):
                lab, cont = np_.find("text"), np_.find("content")
                if lab and cont:
                    titulos_toc.setdefault(cont["src"].split("#")[0].split("/")[-1], lab.get_text(strip=True))

        capa = None
        capa_item = next((i for i in opf.find_all("item") if "cover-image" in (i.get("properties") or "")), None)
        if capa_item is not None:
            try:
                capa = z.read(posixpath.normpath(posixpath.join(base, capa_item["href"])))
            except KeyError:
                pass

        secoes: list[Secao] = []
        for href in ordem:
            caminho_z = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
            try:
                html = z.read(caminho_z)
            except KeyError:
                continue
            soup = BeautifulSoup(html, "lxml")
            corpo = soup.body or soup
            blocos = _blocos_html(corpo)
            if not blocos:
                continue
            nome_arq = href.split("/")[-1]
            tit = titulos_toc.get(nome_arq) or next((b.texto for b in blocos if b.tipo == "titulo"), "") or Path(nome_arq).stem
            secoes.append(Secao(_conserta(tit), blocos))
    return Documento(_conserta(titulo) or caminho.stem, _conserta(autor), idioma[:2].lower(), secoes, capa)


def _conserta(t: str) -> str:
    return t.replace("�", "’").strip()


# ---- TXT / Markdown ---------------------------------------------------------------------------------------
_CAP = re.compile(r"^\s*(?:chapter|cap[íi]tulo|part|parte|book|livro|prologue|prólogo|epilogue|ep[íi]logo|introduction|introdu[çc][ãa]o|preface|pref[áa]cio)\b.{0,60}$",
                  re.IGNORECASE)


def _texto_em_secoes(texto: str, titulo: str, usar_md: bool) -> list[Secao]:
    texto = limpar(texto)
    secoes: list[Secao] = []
    atual = Secao(titulo)
    for par in re.split(r"\n\s*\n", unir_linhas_do_paragrafo(texto) if not usar_md else texto):
        par = par.strip()
        if not par:
            continue
        md = re.match(r"^(#{1,6})\s+(.+)$", par) if usar_md else None
        if md or (len(par) <= 70 and "\n" not in par and _CAP.match(par)):
            t = (md.group(2) if md else par).strip()
            nivel = len(md.group(1)) if md else 1
            if nivel <= 1:
                if atual.blocos:
                    secoes.append(atual)
                atual = Secao(t, [Bloco("titulo", t, 1)])
            else:
                atual.blocos.append(Bloco("titulo", t, nivel))
            continue
        atual.blocos.append(Bloco("texto", re.sub(r"\s*\n\s*", " ", par)))
    if atual.blocos:
        secoes.append(atual)
    return secoes


def _txt(caminho: Path) -> Documento:
    bruto = caminho.read_bytes()
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        from charset_normalizer import from_bytes

        melhor = from_bytes(bruto).best()
        texto = str(melhor) if melhor else bruto.decode("latin-1")
    return Documento(caminho.stem, secoes=_texto_em_secoes(texto, caminho.stem, False))


def _md(caminho: Path) -> Documento:
    texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    texto = re.sub(r"^(?:---|\*\*\*|___)\s*$", QUEBRA_CENA, texto, flags=re.MULTILINE)
    texto = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texto)
    texto = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", texto)
    return Documento(caminho.stem, secoes=_texto_em_secoes(texto, caminho.stem, True))


# ---- DOCX -------------------------------------------------------------------------------------------------
def _docx(caminho: Path) -> Documento:
    import docx

    d = docx.Document(str(caminho))
    props = d.core_properties
    secoes: list[Secao] = []
    atual = Secao(props.title or caminho.stem)
    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        estilo = (p.style.name or "").lower() if p.style is not None else ""
        m = re.match(r"(?:heading|título|titulo)\s*(\d)", estilo)
        if estilo == "title" or m:
            nivel = int(m.group(1)) if m else 1
            if nivel <= 1:
                if atual.blocos:
                    secoes.append(atual)
                atual = Secao(t, [Bloco("titulo", t, 1)])
            else:
                atual.blocos.append(Bloco("titulo", t, nivel))
        else:
            atual.blocos.append(Bloco("texto", QUEBRA_CENA if re.fullmatch(r"[\s*\-–—_•·~=#]{3,}", t) else t))
    if atual.blocos:
        secoes.append(atual)
    if len(secoes) <= 1 and secoes:
        todo = "\n\n".join(b.texto for b in secoes[0].blocos if b.tipo == "texto")
        secoes = _texto_em_secoes(todo, props.title or caminho.stem, False) or secoes
    return Documento(props.title or caminho.stem, props.author or "", "", secoes)


# ---- PDF --------------------------------------------------------------------------------------------------
def _pdf(caminho: Path) -> Documento:
    import fitz

    from collections import Counter

    pdf = fitz.open(str(caminho))
    paginas: list[list[str]] = []
    for pg in pdf:
        linhas = [ln.strip() for ln in pg.get_text("text").split("\n")]
        paginas.append([ln for ln in linhas if ln])
    if sum(len(" ".join(p)) for p in paginas) < 200 * max(1, min(len(paginas), 3)):
        raise ErroDocumento("Este PDF parece ser só imagem (escaneado) e não tem texto. Faça OCR antes de importar.")
    # cabeçalhos e rodapés: linhas do topo/fim repetidas em muitas páginas, e números de página soltos
    cont: Counter = Counter()
    for p in paginas:
        for ln in {*(p[:2]), *(p[-2:])}:
            cont[re.sub(r"\d+", "#", ln)] += 1
    limite = max(3, int(len(paginas) * 0.35))
    ruido = {k for k, v in cont.items() if v >= limite}
    texto_paginas = []
    for p in paginas:
        keep = [ln for ln in p if re.sub(r"\d+", "#", ln) not in ruido and not re.fullmatch(r"[\divxlcIVXLC.\- ]{1,8}", ln)]
        texto_paginas.append("\n".join(keep))
    texto = "\n".join(texto_paginas)
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)
    # parágrafo: linha que termina em pontuação seguida de linha com maiúscula curta; junta o resto
    texto = re.sub(r"([^\n.!?:”\"’])\n(?=[a-zà-ÿ0-9“(‘])", r"\1 ", texto)
    texto = re.sub(r"\n(?=[^\n])", "\n\n", texto) if texto.count("\n\n") < len(texto) / 4000 else texto
    meta = pdf.metadata or {}
    titulo = (meta.get("title") or "").strip() or caminho.stem
    # sumário do PDF vira os capítulos quando existe
    toc = [t for t in pdf.get_toc() if t[0] == 1]
    secoes = _texto_em_secoes(texto, titulo, False)
    if len(toc) >= 3 and len(secoes) <= 2:
        secoes = _secoes_por_toc(pdf, toc, ruido)
    return Documento(titulo, (meta.get("author") or "").strip(), "", secoes)


def _secoes_por_toc(pdf, toc, ruido) -> list[Secao]:
    secoes = []
    for i, (_n, tit, pg) in enumerate(toc):
        fim = toc[i + 1][2] - 1 if i + 1 < len(toc) else len(pdf)
        partes = []
        for k in range(pg - 1, max(pg, fim)):
            linhas = [ln.strip() for ln in pdf[k].get_text("text").split("\n") if ln.strip()]
            partes.append("\n".join(ln for ln in linhas if re.sub(r"\d+", "#", ln) not in ruido and not re.fullmatch(r"[\d.\- ]{1,6}", ln)))
        texto = limpar(unir_linhas_do_paragrafo("\n".join(partes)))
        blocos = [Bloco("titulo", tit, 1)] + [Bloco("texto", p) for p in re.split(r"\n\s*\n", texto) if p.strip()]
        secoes.append(Secao(tit, blocos))
    return secoes


# ---- MOBI / AZW -------------------------------------------------------------------------------------------
def _mobi(caminho: Path) -> Documento:
    try:
        import mobi
    except ImportError as e:
        raise ErroDocumento("Para MOBI/AZW instale o pacote 'mobi' (pip install mobi), ou converta para EPUB.") from e
    import shutil

    pasta, extraido = mobi.extract(str(caminho))
    try:
        ex = Path(extraido)
        if ex.suffix.lower() == ".epub":
            return _epub(ex)
        soup = BeautifulSoup(ex.read_bytes(), "lxml")
        return Documento(caminho.stem, secoes=[Secao(caminho.stem, _blocos_html(soup.body or soup))])
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
