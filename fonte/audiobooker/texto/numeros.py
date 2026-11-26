"""Números e símbolos por extenso (inglês e português do Brasil), com cuidado nos casos ambíguos."""
from __future__ import annotations

import re

from num2words import num2words

_ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_PALAVRA_ROMANO = r"(?:chapter|part|book|section|volume|act|scene|canto|cap[íi]tulo|parte|livro|se[çc][ãa]o|ato|cena|tomo|vol\.?)"


_MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _cardeal(n: int, lang: str) -> str:
    # sem vírgulas ("mil, duzentos") para a voz não fazer pausa no meio do número
    return num2words(n, lang="pt_BR" if lang == "pt" else "en").replace(",", "")


def _ordinal(n: int, lang: str) -> str:
    return num2words(n, lang="pt_BR" if lang == "pt" else "en", to="ordinal")


def _ano(n: int, lang: str) -> str:
    if lang == "pt":
        return _cardeal(n, lang)
    return num2words(n, lang="en", to="year").replace(",", "")


def _data_pt(m: re.Match) -> str:
    dia, mes = int(m.group(1)), int(m.group(2))
    if not (1 <= dia <= 31 and 1 <= mes <= 12):
        return m.group(0)
    s = ("primeiro" if dia == 1 else _cardeal(dia, "pt")) + " de " + _MESES_PT[mes - 1]
    if m.group(3):
        ano = int(m.group(3))
        s += " de " + _cardeal(ano + (2000 if ano < 50 else 1900) if ano < 100 else ano, "pt")
    return s


def _romano_para_int(s: str) -> int | None:
    if not s or any(c not in _ROMANOS for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = _ROMANOS[c]
        total += -v if i + 1 < len(s) and _ROMANOS[s[i + 1]] > v else v
    return total if 0 < total < 400 else None


def _decimal(txt: str, lang: str) -> str:
    sep = "," if lang == "pt" else "."
    inteiro, _, frac = txt.partition(sep)
    pt = _cardeal(int(inteiro or 0), lang)
    if not frac:
        return pt
    digitos = " ".join(_cardeal(int(d), lang) for d in frac) if len(frac) > 2 else _cardeal(int(frac), lang)
    return f"{pt} {'vírgula' if lang == 'pt' else 'point'} {digitos}"


def por_extenso(texto: str, lang: str) -> str:
    en = lang != "pt"

    # algarismos romanos depois de "Chapter/Part/Capítulo..."
    def romano(m: re.Match) -> str:
        n = _romano_para_int(m.group(2))
        return f"{m.group(1)} {_cardeal(n, lang)}" if n else m.group(0)

    texto = re.sub(rf"\b({_PALAVRA_ROMANO})\s+([IVXLCDM]{{1,7}})\b", romano, texto, flags=re.IGNORECASE)

    # sinal de seção
    texto = re.sub(r"§§?\s*(\d+)", lambda m: f"{'section' if en else 'seção'} {_cardeal(int(m.group(1)), lang)}", texto)

    # moedas
    if en:
        texto = re.sub(r"\$\s?(\d{1,3}(?:,\d{3})*)(?:\.(\d{2}))?\b",
                       lambda m: _moeda_en(m.group(1), m.group(2)), texto)
        texto = re.sub(r"£\s?(\d{1,3}(?:,\d{3})*)\b", lambda m: f"{_cardeal(int(m.group(1).replace(',', '')), lang)} pounds", texto)
    else:
        texto = re.sub(r"R\$\s?(\d{1,3}(?:\.\d{3})*)(?:,(\d{2}))?",
                       lambda m: _moeda_pt(m.group(1), m.group(2)), texto)

    # porcentagem
    texto = re.sub(r"(\d+(?:[.,]\d+)?)\s?%", lambda m: f"{_decimal(m.group(1), lang)} {'por cento' if not en else 'percent'}", texto)

    # ordinais em inglês (1st, 2nd) e português (1º, 2ª)
    texto = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", lambda m: _ordinal(int(m.group(1)), lang), texto)
    texto = re.sub(r"\b(\d+)[ºª°]", lambda m: _ordinal(int(m.group(1)), lang), texto)

    # horários 3:45
    def hora(m: re.Match) -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 24 or mi > 59:
            return m.group(0)
        if en:
            return f"{_cardeal(h, lang)} {'o’clock' if mi == 0 else (_cardeal(mi, lang) if mi >= 10 else 'oh ' + _cardeal(mi, lang))}"
        return f"{_cardeal(h, lang)} {'horas' if h != 1 else 'hora'}" + (f" e {_cardeal(mi, lang)}" if mi else "")

    texto = re.sub(r"\b(\d{1,2}):(\d{2})\b(?!:)", hora, texto)

    # datas 15/03/1998 (só em português; em inglês é ambíguo)
    if not en:
        texto = re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", _data_pt, texto)

    # intervalos 12-15 / 1914–1918
    texto = re.sub(r"\b(\d{1,4})\s?[–-]\s?(\d{1,4})\b",
                   lambda m: f"{_numero(m.group(1), lang)} {'to' if en else 'a'} {_numero(m.group(2), lang)}", texto)

    # decimais e milhares
    if en:
        texto = re.sub(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b", lambda m: _grande(m.group(0), lang), texto)
        texto = re.sub(r"\b\d+\.\d+\b", lambda m: _decimal(m.group(0), lang), texto)
    else:
        texto = re.sub(r"\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b", lambda m: _grande(m.group(0), lang), texto)
        texto = re.sub(r"\b\d+,\d+\b", lambda m: _decimal(m.group(0), lang), texto)

    # o resto dos inteiros
    texto = re.sub(r"\b\d+\b", lambda m: _numero(m.group(0), lang), texto)
    return texto


def _grande(txt: str, lang: str) -> str:
    if lang == "pt":
        inteiro, _, frac = txt.partition(",")
        v = _cardeal(int(inteiro.replace(".", "")), lang)
        return v + (f" vírgula {_cardeal(int(frac), lang)}" if frac else "")
    inteiro, _, frac = txt.partition(".")
    v = _cardeal(int(inteiro.replace(",", "")), lang)
    return v + (f" point {' '.join(_cardeal(int(d), lang) for d in frac)}" if frac else "")


def _numero(txt: str, lang: str) -> str:
    n = int(txt)
    if n >= 10**12:
        return " ".join(txt)  # número gigante: dígito por dígito
    if len(txt) == 4 and 1100 <= n <= 2099 and not txt.startswith("0"):
        return _ano(n, lang)
    if len(txt) > 1 and txt.startswith("0"):
        return " ".join(_cardeal(int(d), lang) for d in txt)
    return _cardeal(n, lang)


def _moeda_en(inteiro: str, cent: str | None) -> str:
    n = int(inteiro.replace(",", ""))
    s = f"{_cardeal(n, 'en')} dollar{'s' if n != 1 else ''}"
    if cent and int(cent):
        s += f" and {_cardeal(int(cent), 'en')} cent{'s' if int(cent) != 1 else ''}"
    return s


def _moeda_pt(inteiro: str, cent: str | None) -> str:
    n = int(inteiro.replace(".", ""))
    s = f"{_cardeal(n, 'pt')} {'real' if n == 1 else 'reais'}"
    if cent and int(cent):
        s += f" e {_cardeal(int(cent), 'pt')} centavos"
    return s
