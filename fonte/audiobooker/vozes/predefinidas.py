"""Vozes de fábrica: as vozes do Kokoro (inglês e português), as vozes externas já baixadas (Piper) e poucos presets de efeito.

Os presets são só "receitas" em cima de uma voz-base e de uma cadeia de efeitos; duplique um e mude à vontade. Ficaram só
os que soaram bem em teste de audição (exterminador, robô clássico, IA de nave) e os dois de rádio militar/telefone antigo; o resto das vozes vem de modelos
baixados ou de clonagem.
"""
from __future__ import annotations

from .modelo import Voz

_IDIOMAS = {"a": ("en", "EUA"), "b": ("en", "Reino Unido"), "p": ("pt", "Brasil")}
_GENERO = {"f": "feminina", "m": "masculina"}
IDIOMAS_ACEITOS = ("a", "b", "p")  # prefixos das vozes do Kokoro: a/b = inglês (EUA/Reino Unido), p = português do Brasil


def id_kokoro(nome_interno: str) -> str:
    return "kokoro-" + nome_interno.replace("_", "-")


def vozes_kokoro(nomes_internos: list[str]) -> list[Voz]:
    saida = []
    for n in nomes_internos:
        if n[0] not in IDIOMAS_ACEITOS:  # só inglês (a, b) e português (p)
            continue
        pref, resto = n.split("_", 1)
        idioma, regiao = _IDIOMAS[pref[0]]
        genero = _GENERO.get(pref[1], "")
        saida.append(Voz(id=id_kokoro(n), nome=f"{resto.capitalize()} ({regiao}, {genero})", motor="kokoro", idioma=idioma,
                         base={n: 1.0}, descricao=f"Voz interna do Kokoro: {n}", tags=["kokoro", regiao.lower(), genero], sistema=True))
    return saida


def _e(tipo: str, **p) -> dict:
    return {"tipo": tipo, **p}


def personagens() -> list[Voz]:
    # Receitas em cima da voz padrão do Chatterbox (motor padrão). `base` fica vazio: para outra timbragem, duplique o preset e
    # escolha um áudio de referência (clonagem). A emoção baixa deixa a fala mais monótona, boa para robôs e rádio.
    def v(id_, nome, base, desc, efeitos, vel=1.0, tags=(), exagero=0.3):
        return Voz(id=id_, nome=nome, motor="chatterbox", idioma="en", descricao=desc, base={}, velocidade=vel,
                   parametros={"exagero": exagero, "cfg": 0.5, "temperatura": 0.8},
                   efeitos=efeitos, tags=["personagem", *tags], sistema=True)

    return [
        v("robo-classico", "Robô clássico", {"am_adam": 1.0}, "Metálico e monótono, estilo robô de ficção antiga.",
          [_e("equalizador", graves=-2, medios=3, agudos=2), _e("robo", frequencia=50, mistura=0.85, metal=0.4),
           _e("bitcrush", bits=11, reducao=2), _e("compressor", limiar=-20, razao=4)], 0.95, tags=("robô",)),
        v("dalek", "Exterminador (dalek)", {"am_onyx": 1.0}, "Grave, staccato, modulado e ameaçador.",
          [_e("tom", semitons=-2), _e("robo", frequencia=30, mistura=1.0, metal=0.5), _e("distorcao", ganho=6),
           _e("reverb", sala=0.15, amortecimento=0.6, mistura=0.1)], 0.9, tags=("robô", "vilão")),
        v("ia-de-nave", "IA de nave", {"af_nova": 0.7, "af_heart": 0.3}, "Calma, limpa, levemente dupla, com ambiente de cabine.",
          [_e("coro", taxa=0.35, profundidade=0.3, mistura=0.3), _e("reverb", sala=0.35, amortecimento=0.4, mistura=0.15),
           _e("equalizador", graves=1, medios=0, agudos=2)], 0.97, tags=("robô", "ficção")),
        v("radio-militar", "Rádio militar", {"am_michael": 1.0}, "Comunicação por rádio, curta e seca.",
          [_e("filtro", passa_alta=350, passa_baixa=3200), _e("distorcao", ganho=5), _e("ruido", nivel=-34),
           _e("compressor", limiar=-24, razao=6)], 1.05, tags=("rádio",)),
        v("telefone-antigo", "Telefone antigo", {"af_sarah": 1.0}, "Voz estreita e abafada, de ligação antiga.",
          [_e("filtro", passa_alta=450, passa_baixa=2800), _e("bitcrush", bits=12, reducao=3), _e("ruido", nivel=-40)], 1.0, tags=("rádio",)),
    ]


def vozes_piper(chaves: list[str]) -> list[Voz]:
    """Vozes externas já baixadas (Vozes → Baixar vozes). Chave: en_GB-alan-medium."""
    saida = []
    for chave in chaves:
        try:
            lingua, nome, qualidade = chave.split("-", 2)
        except ValueError:
            continue
        familia = lingua.split("_")[0]
        if familia not in ("en", "pt"):
            continue
        regiao = {"en_US": "EUA", "en_GB": "Reino Unido", "pt_BR": "Brasil", "pt_PT": "Portugal"}.get(lingua, lingua)
        saida.append(Voz(id="piper-" + chave.replace("_", "-"), nome=f"{nome.replace('_', ' ').title()} ({regiao}, {qualidade})", motor="piper",
                         idioma=familia, base={chave: 1.0}, descricao=f"Voz externa do Piper: {chave}", tags=["piper", "externa", regiao.lower()],
                         sistema=True))
    return saida


def todas(nomes_kokoro: list[str], chaves_piper: list[str] | None = None) -> list[Voz]:
    return vozes_kokoro(nomes_kokoro) + personagens() + [chatterbox_padrao()] + vozes_piper(chaves_piper or [])


def chatterbox_padrao() -> Voz:
    return Voz(id="chatterbox-padrao", nome="Chatterbox (voz padrão)", motor="chatterbox", idioma="en",
               descricao="Voz base do Chatterbox, sem referência. Para clonar, duplique e escolha um áudio.",
               parametros={"exagero": 0.5, "cfg": 0.5, "temperatura": 0.8}, tags=["chatterbox"], sistema=True)
