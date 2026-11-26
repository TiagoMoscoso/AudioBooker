"""Resolve uma Direcao para o motor atual: o que ele executa vai como parâmetro; velocidade, tom e volume são pós-processamento
real; o que o motor não suporta é IGNORADO e vira aviso (nada de imitação silenciosa)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import numpy as np

from ..texto.direcoes import ESTILOS, Direcao

SR = 24000
_TAGS_SOM = re.compile(r"\s*\[(?:laugh|chuckle|cough|sigh|gasp|groan|sniff|shush|clear throat)\]\s*", re.IGNORECASE)


@dataclass
class Resolvido:
    texto: str
    entrega: dict = field(default_factory=dict)   # vai para o motor (emoção, CFG, instrução)
    pos: dict = field(default_factory=dict)       # velocidade, tom, volume: aplicados depois, sem gerar de novo
    avisos: list[str] = field(default_factory=list)

    def chave(self) -> str:
        return json.dumps(self.entrega, sort_keys=True)


def resolver(d: Direcao, texto: str, caps: frozenset[str], rotulo: str = "o motor atual") -> Resolvido:
    r = Resolvido(texto=texto)
    ef = d
    if d.estilo and d.estilo in ESTILOS and d.estilo != "neutro":
        spec = ESTILOS[d.estilo]
        faltam = set(spec["exige"]) - set(caps)
        if faltam:
            r.avisos.append(f"estilo “{spec['nome']}” ignorado: {rotulo} não tem {_nomes(faltam)}")
        else:
            base = Direcao(emocao=spec["params"].get("emocao"), velocidade=spec["params"].get("velocidade"),
                           tom=spec["params"].get("tom"), volume=spec["params"].get("volume"), instrucao=spec.get("instrucao", ""))
            ef = base.mesclar(Direcao(**{k: v for k, v in d.__dict__.items() if k != "estilo"}))
    elif d.estilo and d.estilo not in ESTILOS:
        r.avisos.append(f"estilo desconhecido: “{d.estilo}”")
    if ef.emocao is not None:
        if "emocao" in caps:
            r.entrega["emocao"] = ef.emocao
        else:
            r.avisos.append(f"emoção ignorada: {rotulo} não controla emoção")
    if ef.cfg is not None:
        if "cfg" in caps:
            r.entrega["cfg"] = ef.cfg
        else:
            r.avisos.append(f"CFG ignorado: {rotulo} não tem CFG")
    if ef.instrucao:
        if "instrucao" in caps:
            r.entrega["instrucao"] = ef.instrucao
        else:
            r.avisos.append(f"instrução de entrega ignorada: {rotulo} não entende instruções em texto")
    if ef.enfase:
        if "palavra" in caps:
            r.entrega["enfase"] = True
        else:
            r.avisos.append(f"ênfase em palavra ignorada: {rotulo} não controla entonação por palavra")
    if _TAGS_SOM.search(texto) and "tags" not in caps:
        r.texto = re.sub(r"\s{2,}", " ", _TAGS_SOM.sub(" ", texto)).strip()
        r.avisos.append(f"tags de som ignoradas: {rotulo} não faz sons como [laugh]")
    if ef.velocidade is not None and abs(ef.velocidade - 1.0) > 0.01:
        r.pos["velocidade"] = ef.velocidade
    if ef.tom is not None and abs(ef.tom) > 0.05:
        r.pos["tom"] = ef.tom
    if ef.volume is not None and abs(ef.volume) > 0.05:
        r.pos["volume"] = ef.volume
    return r


def _nomes(faltam: set[str]) -> str:
    from ..motores.base import CAPACIDADES

    return ", ".join(CAPACIDADES.get(f, f).lower() for f in sorted(faltam))


def aplicar_pos(audio: np.ndarray, pos: dict, sr: int = SR) -> np.ndarray:
    """Velocidade e tom (Rubber Band, timbre preservado) e volume. Mudanças pequenas soam bem; acima de ±3 semitons há artefatos."""
    if not pos or len(audio) == 0:
        return audio
    import pedalboard as pb

    x = np.asarray(audio, dtype=np.float32)
    vel, tom = float(pos.get("velocidade", 1.0)), float(pos.get("tom", 0.0))
    if abs(vel - 1.0) > 0.01 or abs(tom) > 0.05:
        x = np.squeeze(pb.time_stretch(x, sr, stretch_factor=vel, pitch_shift_in_semitones=tom)).astype(np.float32)
    if "volume" in pos:
        x = x * (10 ** (float(pos["volume"]) / 20))
    pico = float(np.max(np.abs(x))) if len(x) else 0.0
    return (x * (0.98 / pico)).astype(np.float32) if pico > 0.98 else x
