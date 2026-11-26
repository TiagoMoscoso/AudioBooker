"""Direção de entrega (intonação): estilos, controles por trecho e por palavra, e a marcação no texto.

Marcação no texto (aceita sem acento também):
  [estilo triste]...[/estilo]      um estilo da lista (calmo, animado, triste, raiva, dramático, misterioso, sussurro, grito)
  [emoção 0.8]...[/emoção]         intensidade emocional do motor (0 a 2)
  [velocidade 0.9]...[/velocidade] ritmo (multiplicador)
  [tom -2]...[/tom]                tom em semitons
  [volume -6]...[/volume]          volume em dB
  [instrução: fale devagar]...[/instrução]   instrução em texto, para modelos que a entendem
  [ênfase]palavra[/ênfase]         destaca uma palavra (motores com controle por palavra)
  [tag laugh]                      som no meio da fala (motores com tags)
  [pausa 1s]                       silêncio
  [/]                              fecha o último aberto

O que o motor atual não consegue fazer é IGNORADO e listado ao final: nada é aproximado em silêncio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from ..motores.base import CAPACIDADES  # noqa: F401  (nomes das capacidades)


@dataclass(frozen=True)
class Direcao:
    estilo: str = ""
    emocao: float | None = None       # 0..2
    cfg: float | None = None          # 0..1
    velocidade: float | None = None   # multiplicador
    tom: float | None = None          # semitons
    volume: float | None = None       # dB
    instrucao: str = ""
    enfase: bool = False

    def vazia(self) -> bool:
        return self == Direcao()

    def mesclar(self, outra: "Direcao") -> "Direcao":
        """`outra` vence onde estiver preenchida."""
        d = self
        for campo in ("estilo", "emocao", "cfg", "velocidade", "tom", "volume", "instrucao"):
            v = getattr(outra, campo)
            if v not in (None, ""):
                d = replace(d, **{campo: v})
        return replace(d, enfase=d.enfase or outra.enfase)

    def para_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", False)}

    @staticmethod
    def de_dict(d: dict | None) -> "Direcao":
        if not d:
            return Direcao()
        return Direcao(**{k: v for k, v in d.items() if k in Direcao.__dataclass_fields__})


# estilos: parâmetros que valem em qualquer motor (velocidade/tom/volume são pós-processamento real) e os que dependem de
# capacidade do motor. `exige`: sem essas capacidades o estilo INTEIRO é ignorado (sem aproximação).
ESTILOS: dict[str, dict] = {
    "neutro": {"nome": "Neutro", "params": {}, "exige": set(), "ajuda": "Sem direção."},
    "calmo": {"nome": "Calmo", "params": {"emocao": 0.3, "velocidade": 0.93}, "exige": set(), "ajuda": "Baixa a intensidade e desacelera."},
    "animado": {"nome": "Animado", "params": {"emocao": 0.8, "velocidade": 1.06}, "exige": set(), "ajuda": "Mais energia e ritmo."},
    "triste": {"nome": "Triste", "params": {"emocao": 0.25, "velocidade": 0.88, "tom": -1.0}, "exige": set(), "ajuda": "Lento, baixo e contido."},
    "raiva": {"nome": "Raiva", "params": {"emocao": 1.0, "velocidade": 1.04, "volume": 2.0}, "exige": set(), "ajuda": "Intensidade máxima, um pouco mais alto."},
    "dramatico": {"nome": "Dramático", "params": {"emocao": 0.9, "velocidade": 0.92}, "exige": set(), "ajuda": "Intenso e pausado."},
    "misterioso": {"nome": "Misterioso", "params": {"emocao": 0.45, "velocidade": 0.9, "volume": -2.0}, "exige": set(), "ajuda": "Contido e lento."},
    "sussurro": {"nome": "Sussurro", "params": {}, "exige": {"instrucao"}, "instrucao": "Speak in a soft whisper, barely audible.",
                 "ajuda": "Só em modelos que aceitam instrução de entrega (voz sem tom, só ar)."},
    "grito": {"nome": "Grito", "params": {}, "exige": {"instrucao"}, "instrucao": "Shout at the top of your voice.",
              "ajuda": "Só em modelos que aceitam instrução de entrega."},
}

_ALIAS = {"estilo": "estilo", "emocao": "emocao", "emoção": "emocao", "velocidade": "velocidade", "tom": "tom", "volume": "volume",
          "instrucao": "instrucao", "instrução": "instrucao", "enfase": "enfase", "ênfase": "enfase", "tag": "tag",
          "pausa": "pausa", "pause": "pausa"}
_TAG = re.compile(r"\[(/?)\s*(estilo|emo[cç][aã]o|velocidade|tom|volume|instru[cç][aã]o|[eê]nfase|tag|pausa|pause)?\s*[:\s]?\s*([^\]\[]*)\]",
                  re.IGNORECASE)


def _sem_acento(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", s.strip().lower()) if not unicodedata.combining(c))


@dataclass
class Trecho:
    texto: str
    direcao: Direcao = field(default_factory=Direcao)
    pausa: float = 0.0          # > 0: silêncio


def _aplicar(stack: list[tuple[str, Direcao]]) -> Direcao:
    d = Direcao()
    for _n, x in stack:
        d = d.mesclar(x)
    return d


def _numero(valor: str, padrao: float | None = None) -> float | None:
    try:
        return float(valor.strip().replace(",", "."))
    except ValueError:
        return padrao


def interpretar(texto: str, base: Direcao | None = None) -> list[Trecho]:
    """Texto com marcação -> trechos com a direção de cada um. Marcação desconhecida fica como texto."""
    base = base or Direcao()
    pilha: list[tuple[str, Direcao]] = []
    saida: list[Trecho] = []
    pos = 0

    def texto_ate(fim: int) -> None:
        pedaco = texto[pos:fim]
        if pedaco.strip():
            saida.append(Trecho(pedaco, base.mesclar(_aplicar(pilha))))

    for m in _TAG.finditer(texto):
        fechando, nome_cru, valor = m.group(1), (m.group(2) or "").lower(), m.group(3).strip()
        if not nome_cru and not fechando:
            continue  # colchetes comuns ([1], [sic]) ficam no texto
        nome = _ALIAS.get(nome_cru, nome_cru)
        if fechando and not nome and valor:
            continue
        texto_ate(m.start())
        pos = m.end()
        if fechando:
            if pilha and (not nome or pilha[-1][0] == nome):
                pilha.pop()
            elif nome:
                for i in range(len(pilha) - 1, -1, -1):
                    if pilha[i][0] == nome:
                        del pilha[i]
                        break
            continue
        if nome == "pausa":
            v = _numero(re.sub(r"(ms|s)$", "", valor), 0.0) or 0.0
            saida.append(Trecho("", pausa=v / 1000.0 if valor.endswith("ms") else v))
        elif nome == "tag":
            saida.append(Trecho(f" [{valor}] ", base.mesclar(_aplicar(pilha))))  # fica no texto; o motor sem tags a remove e avisa
        elif nome == "estilo":
            pilha.append(("estilo", Direcao(estilo=_sem_acento(valor))))
        elif nome == "emocao":
            pilha.append(("emocao", Direcao(emocao=_numero(valor))))
        elif nome == "velocidade":
            pilha.append(("velocidade", Direcao(velocidade=_numero(valor))))
        elif nome == "tom":
            pilha.append(("tom", Direcao(tom=_numero(valor))))
        elif nome == "volume":
            pilha.append(("volume", Direcao(volume=_numero(valor))))
        elif nome == "instrucao":
            pilha.append(("instrucao", Direcao(instrucao=valor)))
        elif nome == "enfase":
            pilha.append(("enfase", Direcao(enfase=True)))
    texto_ate(len(texto))
    return _fundir_iguais(saida)


def _fundir_iguais(trechos: list[Trecho]) -> list[Trecho]:
    """Junta vizinhos com a mesma direção (menos emendas na fala)."""
    saida: list[Trecho] = []
    for t in trechos:
        if saida and not t.pausa and not saida[-1].pausa and saida[-1].direcao == t.direcao:
            saida[-1] = Trecho(saida[-1].texto + t.texto, t.direcao)
        else:
            saida.append(t)
    return saida


def tem_marcacao(texto: str) -> bool:
    return any((m.group(2) or "") for m in _TAG.finditer(texto))


def limpar_marcacao(texto: str) -> str:
    """Texto puro, sem marcas (para contar palavras, caches ou exportar)."""
    return "".join(t.texto for t in interpretar(texto) if not t.pausa)
