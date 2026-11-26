"""Intonação por contexto: lê o entorno de uma fala ("she whispered softly", "gritou furioso") e sugere um estilo.

É só uma SUGESTÃO para a revisão manual do roteiro: se o motor não executa o estilo (ex.: sussurro sem modelo com instrução de
entrega), ele é ignorado e listado, nunca imitado.
"""
from __future__ import annotations

import re

_VERBOS = {
    "sussurro": r"whisper\w*|murmur\w*|mutter\w*|breath\w*|hiss\w*|sussurr\w*|cochich\w*|murmur\w*",
    "grito": r"shout\w*|yell\w*|scream\w*|roar\w*|bellow\w*|bark\w*|cri(?:ed|es) out|exclaim\w*|gritou|berrou|urrou|bradou|vociferou",
    "triste": r"sigh\w*|sob\w*|wept|weep\w*|moan\w*|mourn\w*|whimper\w*|suspir\w*|chorou|lamentou|gemeu",
    "animado": r"laugh\w*|giggl\w*|chuckl\w*|cheer\w*|beam\w*|riu|gargalhou|sorriu|exultou",
    "raiva": r"growl\w*|snarl\w*|snap\w*|spat|fum\w*|rosnou|esbravej\w*|resmung\w*",
}
_ADVERBIOS = {
    "calmo": r"soft(?:ly)?|quiet(?:ly)?|gentl[ey]\w*|calm(?:ly)?|slow(?:ly)?|baixinho|suavemente|calmamente|devagar|serenamente",
    "triste": r"sad(?:ly)?|mournful(?:ly)?|bitter(?:ly)?|tristemente|amargamente|melancolicamente",
    "raiva": r"angr(?:y|ily)|furious(?:ly)?|sharp(?:ly)?|cold(?:ly)?|irritad\w+|furiosamente|rispidamente|friamente",
    "animado": r"excited(?:ly)?|eager(?:ly)?|cheerful(?:ly)?|happ(?:y|ily)|bright(?:ly)?|animadamente|alegremente|empolgad\w+",
    "grito": r"loud(?:ly)?|fierce(?:ly)?|alto|ferozmente",
    "misterioso": r"mysterious(?:ly)?|ominous(?:ly)?|misteriosamente|sinistramente",
    "dramatico": r"dramatic(?:ally)?|solemn(?:ly)?|dramaticamente|solenemente",
}
_RE_VERBOS = [(e, re.compile(rf"\b(?:{p})\b", re.IGNORECASE)) for e, p in _VERBOS.items()]
_RE_ADV = [(e, re.compile(rf"\b(?:{p})\b", re.IGNORECASE)) for e, p in _ADVERBIOS.items()]


def estilo_de(depois: str, antes: str = "") -> str:
    """Estilo sugerido para uma fala, olhando a oração de atribuição que a segue (ou, na falta, a que a precede)."""
    for i, janela in enumerate((depois[:90], antes[-70:])):
        if not janela.strip():
            continue
        # só a oração de atribuição: a que segue a fala (até a pontuação forte) ou a última que a precede
        partes = re.split(r"[.!?…]\s", janela.strip())
        trecho = partes[0] if i == 0 else partes[-1]
        for estilo, rx in _RE_VERBOS:
            if rx.search(trecho):
                return estilo
        for estilo, rx in _RE_ADV:
            if rx.search(trecho):
                return estilo
    return ""
