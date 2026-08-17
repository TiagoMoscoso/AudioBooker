"""Converts digits/numerals to their spoken form, language-aware (§ narration
quality — "não enviar números... cegamente ao TTS"). Pure regex + a small
hand-written cardinal/ordinal word converter per language — no NLP/num2words
dependency, matching the project's existing minimal, inspectable style.

Deliberately conservative on ambiguous cases (documented per-pattern below)
rather than guessing wrong: a number that isn't confidently recognized as a
date/currency/percentage/time is read as a plain cardinal, which is always a
safe, intelligible fallback.
"""
from __future__ import annotations

import re

_EN_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_EN_TEENS = [
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_EN_SCALES = [(1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")]
_EN_ORDINAL_SUFFIX = {
    "one": "first", "two": "second", "three": "third", "four": "fourth", "five": "fifth",
    "six": "sixth", "seven": "seventh", "eight": "eighth", "nine": "ninth", "ten": "tenth",
    "eleven": "eleventh", "twelve": "twelfth", "thirteen": "thirteenth", "fourteen": "fourteenth",
    "fifteen": "fifteenth", "sixteen": "sixteenth", "seventeen": "seventeenth",
    "eighteen": "eighteenth", "nineteen": "nineteenth", "twenty": "twentieth",
    "thirty": "thirtieth", "forty": "fortieth", "fifty": "fiftieth", "sixty": "sixtieth",
    "seventy": "seventieth", "eighty": "eightieth", "ninety": "ninetieth",
    "hundred": "hundredth", "thousand": "thousandth", "million": "millionth", "billion": "billionth",
}

_PT_ONES = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
_PT_TEENS = [
    "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis",
    "dezessete", "dezoito", "dezenove",
]
_PT_TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_PT_HUNDREDS = [
    "", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
    "seiscentos", "setecentos", "oitocentos", "novecentos",
]
_PT_SCALES = [(1_000_000_000, "bilhão", "bilhões"), (1_000_000, "milhão", "milhões"), (1_000, "mil", "mil")]
_PT_ORDINALS = {
    1: "primeiro", 2: "segundo", 3: "terceiro", 4: "quarto", 5: "quinto",
    6: "sexto", 7: "sétimo", 8: "oitavo", 9: "nono", 10: "décimo",
    11: "décimo primeiro", 12: "décimo segundo", 13: "décimo terceiro",
    14: "décimo quarto", 15: "décimo quinto", 16: "décimo sexto",
    17: "décimo sétimo", 18: "décimo oitavo", 19: "décimo nono", 20: "vigésimo",
    30: "trigésimo", 40: "quadragésimo", 50: "quinquagésimo", 60: "sexagésimo",
    70: "septuagésimo", 80: "octogésimo", 90: "nonagésimo", 100: "centésimo",
}

_MAX_SUPPORTED = 1_000_000_000_000  # below one trillion; larger numbers fall back to digits


def _en_below_1000(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(f"{_EN_ONES[n // 100]} hundred")
        n %= 100
    if n >= 20:
        tens_word = _EN_TENS[n // 10]
        parts.append(f"{tens_word}-{_EN_ONES[n % 10]}" if n % 10 else tens_word)
    elif n >= 10:
        parts.append(_EN_TEENS[n - 10])
    elif n > 0:
        parts.append(_EN_ONES[n])
    return " ".join(parts)


def cardinal_en(n: int) -> str:
    if n == 0:
        return "zero"
    negative = n < 0
    n = abs(n)
    if n >= _MAX_SUPPORTED:
        return str(n)
    chunks = []
    for value, name in _EN_SCALES:
        if n >= value:
            count = n // value
            chunks.append(f"{_en_below_1000(count)} {name}")
            n %= value
    if n > 0:
        remainder = _en_below_1000(n)
        chunks.append(f"and {remainder}" if chunks and n < 100 else remainder)
    result = " ".join(chunks) if chunks else "zero"
    return f"negative {result}" if negative else result


def ordinal_en(n: int) -> str:
    cardinal = cardinal_en(n)
    last_token = cardinal.rsplit(" ", 1)[-1]
    if "-" in last_token:
        prefix, last = cardinal.rsplit("-", 1)
        return f"{prefix}-{_EN_ORDINAL_SUFFIX.get(last, last + 'th')}"
    words = cardinal.split(" ")
    words[-1] = _EN_ORDINAL_SUFFIX.get(words[-1], words[-1] + "th")
    return " ".join(words)


def _is_year_like(n: int) -> bool:
    return 1000 <= n <= 2999 and n % 1000 != 0


def year_en(n: int) -> str:
    high, low = divmod(n, 100)
    if low == 0:
        return f"{cardinal_en(high)} hundred"
    if low < 10:
        return f"{cardinal_en(high)} oh {_EN_ONES[low]}"
    return f"{cardinal_en(high)} {_en_below_1000(low)}"


def _pt_below_1000(n: int) -> str:
    if n == 100:
        return "cem"
    parts = []
    if n >= 100:
        parts.append(_PT_HUNDREDS[n // 100])
        n %= 100
    if n >= 20:
        tens_word = _PT_TENS[n // 10]
        parts.append(f"{tens_word} e {_PT_ONES[n % 10]}" if n % 10 else tens_word)
    elif n >= 10:
        parts.append(_PT_TEENS[n - 10])
    elif n > 0:
        parts.append(_PT_ONES[n])
    return " e ".join(parts)


def cardinal_pt(n: int) -> str:
    if n == 0:
        return "zero"
    negative = n < 0
    n = abs(n)
    if n >= _MAX_SUPPORTED:
        return str(n)
    chunks = []
    for value, singular, plural in _PT_SCALES:
        if n >= value:
            count = n // value
            if value == 1_000:
                word = "mil" if count == 1 else f"{_pt_below_1000(count)} mil"
            else:
                word = f"um {singular}" if count == 1 else f"{_pt_below_1000(count)} {plural}"
            chunks.append(word)
            n %= value
    if n > 0:
        remainder = _pt_below_1000(n)
        chunks.append(f"e {remainder}" if chunks and n < 100 else remainder)
    result = " ".join(chunks) if chunks else "zero"
    return f"menos {result}" if negative else result


def ordinal_pt(n: int) -> str:
    if n in _PT_ORDINALS:
        return _PT_ORDINALS[n]
    if 21 <= n <= 99:
        tens, ones = (n // 10) * 10, n % 10
        if tens in _PT_ORDINALS and ones in _PT_ORDINALS:
            return f"{_PT_ORDINALS[tens]} {_PT_ORDINALS[ones]}"
    return f"número {cardinal_pt(n)}"


def _digits_spoken(digits: str, ones: list[str]) -> str:
    zero = "zero"
    return " ".join(ones[int(d)] if d != "0" else zero for d in digits)


# "In 1998" / "since 1998" / "by 1998" etc. — the only context cheap enough
# to detect reliably where a bare 4-digit number is confidently a year and
# should use the "nineteen ninety-eight" idiom rather than the full cardinal
# ("one thousand nine hundred ninety-eight"). Anything else (e.g. "1998
# items", per the ambiguity the feature is explicitly meant to respect) falls
# through to the plain-cardinal pass below, which is always intelligible.
_EN_YEAR_CONTEXT = re.compile(
    r"\b(in|since|by|until|before|after|year|copyright|©)\s+(1[0-9]{3}|2[0-9]{3})\b(?!\.\d)",
    re.IGNORECASE,
)
_EN_YEAR_STANDALONE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\b(?=[.,;:!?)]|$)")

_EN_CURRENCY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{2}))?")
_EN_PERCENT = re.compile(r"\b(\d+)(?:\.(\d+))?\s?%")
_EN_TEMPERATURE = re.compile(r"(-?\d+)\s?°\s?([CF])\b")
_EN_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b(\s?([AaPp])\.?[Mm]\b)?")
_EN_ORDINAL = re.compile(r"\b(\d{1,4})(st|nd|rd|th)\b", re.IGNORECASE)
_EN_DECIMAL = re.compile(r"\b(\d+)\.(\d+)\b")
_EN_GROUPED_INT = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")
_EN_PLAIN_INT = re.compile(r"\b\d+\b")

_PT_CURRENCY = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?")
_PT_PERCENT = re.compile(r"\b(\d+)(?:,(\d+))?\s?%")
_PT_TEMPERATURE = re.compile(r"(-?\d+)\s?°\s?([CF])\b")
_PT_TIME = re.compile(r"\b([01]?\d|2[0-3])[:h]([0-5]\d)\b")
_PT_ORDINAL = re.compile(r"\b(\d{1,3})[ºª]")
_PT_DECIMAL = re.compile(r"\b(\d+),(\d+)\b")
_PT_GROUPED_INT = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")
_PT_PLAIN_INT = re.compile(r"\b\d+\b")


class NumberNormalizer:
    """Regex-driven number/date/currency/percentage/time/ordinal-to-spoken-
    form conversion, one language-specific pass per pattern, most specific
    first so a generic integer pattern never swallows a more specific match
    (each pass replaces digits with words, so later passes never re-match
    already-converted text)."""

    def normalize(self, text: str, language: str) -> str:
        return self._normalize_en(text) if language == "en" else self._normalize_pt(text)

    # -- English ------------------------------------------------------------

    def _normalize_en(self, text: str) -> str:
        text = _EN_YEAR_CONTEXT.sub(lambda m: f"{m.group(1)} {year_en(int(m.group(2)))}", text)
        text = _EN_YEAR_STANDALONE.sub(lambda m: year_en(int(m.group(1))), text)
        text = _EN_CURRENCY.sub(self._en_currency, text)
        text = _EN_TEMPERATURE.sub(self._en_temperature, text)
        text = _EN_PERCENT.sub(self._en_percent, text)
        text = _EN_TIME.sub(self._en_time, text)
        text = _EN_ORDINAL.sub(lambda m: ordinal_en(int(m.group(1))), text)
        text = _EN_DECIMAL.sub(self._en_decimal, text)
        text = _EN_GROUPED_INT.sub(lambda m: cardinal_en(int(m.group(0).replace(",", ""))), text)
        text = _EN_PLAIN_INT.sub(lambda m: cardinal_en(int(m.group(0))), text)
        return text

    def _en_currency(self, m: re.Match) -> str:
        whole = int(m.group(1).replace(",", ""))
        cents = int(m.group(2)) if m.group(2) else 0
        result = f"{cardinal_en(whole)} dollar{'s' if whole != 1 else ''}"
        if cents:
            result += f" and {cardinal_en(cents)} cent{'s' if cents != 1 else ''}"
        return result

    def _en_percent(self, m: re.Match) -> str:
        whole = cardinal_en(int(m.group(1)))
        if m.group(2):
            whole += f" point {_digits_spoken(m.group(2), _EN_ONES)}"
        return f"{whole} percent"

    def _en_temperature(self, m: re.Match) -> str:
        value = cardinal_en(int(m.group(1)))
        unit = "Celsius" if m.group(2) == "C" else "Fahrenheit"
        return f"{value} degrees {unit}"

    def _en_time(self, m: re.Match) -> str:
        hour, minute = int(m.group(1)), int(m.group(2))
        spoken = f"{cardinal_en(hour)} o'clock" if minute == 0 else f"{cardinal_en(hour)} {_en_below_1000(minute)}"
        if m.group(4):
            spoken += f" {m.group(4).upper()} M"
        return spoken

    def _en_decimal(self, m: re.Match) -> str:
        return f"{cardinal_en(int(m.group(1)))} point {_digits_spoken(m.group(2), _EN_ONES)}"

    # -- Portuguese -----------------------------------------------------------

    def _normalize_pt(self, text: str) -> str:
        text = _PT_CURRENCY.sub(self._pt_currency, text)
        text = _PT_TEMPERATURE.sub(self._pt_temperature, text)
        text = _PT_PERCENT.sub(self._pt_percent, text)
        text = _PT_TIME.sub(self._pt_time, text)
        text = _PT_ORDINAL.sub(lambda m: ordinal_pt(int(m.group(1))), text)
        text = _PT_DECIMAL.sub(self._pt_decimal, text)
        text = _PT_GROUPED_INT.sub(lambda m: cardinal_pt(int(m.group(0).replace(".", ""))), text)
        text = _PT_PLAIN_INT.sub(lambda m: cardinal_pt(int(m.group(0))), text)
        return text

    def _pt_currency(self, m: re.Match) -> str:
        whole = int(m.group(1).replace(".", ""))
        cents = int(m.group(2)) if m.group(2) else 0
        result = f"{cardinal_pt(whole)} {'real' if whole == 1 else 'reais'}"
        if cents:
            result += f" e {cardinal_pt(cents)} {'centavo' if cents == 1 else 'centavos'}"
        return result

    def _pt_percent(self, m: re.Match) -> str:
        whole = cardinal_pt(int(m.group(1)))
        if m.group(2):
            whole += f" vírgula {_digits_spoken(m.group(2), _PT_ONES)}"
        return f"{whole} por cento"

    def _pt_temperature(self, m: re.Match) -> str:
        value = cardinal_pt(int(m.group(1)))
        unit = "Celsius" if m.group(2) == "C" else "Fahrenheit"
        return f"{value} graus {unit}"

    def _pt_time(self, m: re.Match) -> str:
        hour, minute = int(m.group(1)), int(m.group(2))
        return f"{cardinal_pt(hour)} horas" if minute == 0 else f"{cardinal_pt(hour)} e {cardinal_pt(minute)}"

    def _pt_decimal(self, m: re.Match) -> str:
        return f"{cardinal_pt(int(m.group(1)))} vírgula {_digits_spoken(m.group(2), _PT_ONES)}"
