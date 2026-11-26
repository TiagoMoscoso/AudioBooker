"""Uma voz = motor + base (voz interna, mistura ou áudio de referência) + parâmetros + cadeia de efeitos."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import caminhos


@dataclass
class Voz:
    id: str
    nome: str
    motor: str = "kokoro"                 # kokoro | chatterbox
    idioma: str = "en"                    # en | pt | ...
    descricao: str = ""
    base: dict = field(default_factory=dict)        # kokoro: {"am_michael": 0.7, "bm_george": 0.3}
    referencia: str = ""                  # chatterbox: arquivo em vozes\referencias (ou caminho absoluto)
    velocidade: float = 1.0
    parametros: dict = field(default_factory=dict)  # chatterbox: exagero, cfg, temperatura
    efeitos: list = field(default_factory=list)     # [{"tipo": "tom", "semitons": -4}, ...]
    tags: list = field(default_factory=list)
    sistema: bool = False                 # vozes de fábrica não são editadas, só duplicadas
    criada_em: float = field(default_factory=time.time)

    # ---- persistência
    def para_dict(self) -> dict:
        return {
            "id": self.id, "nome": self.nome, "motor": self.motor, "idioma": self.idioma,
            "descricao": self.descricao, "base": self.base, "referencia": self.referencia,
            "velocidade": self.velocidade, "parametros": self.parametros, "efeitos": self.efeitos,
            "tags": self.tags, "criada_em": self.criada_em,
        }

    @staticmethod
    def de_dict(d: dict) -> "Voz":
        return Voz(
            id=d["id"], nome=d.get("nome", d["id"]), motor=d.get("motor", "kokoro"), idioma=d.get("idioma", "en"),
            descricao=d.get("descricao", ""), base=dict(d.get("base", {})), referencia=d.get("referencia", ""),
            velocidade=float(d.get("velocidade", 1.0)), parametros=dict(d.get("parametros", {})),
            efeitos=list(d.get("efeitos", [])), tags=list(d.get("tags", [])), criada_em=d.get("criada_em", time.time()),
        )

    def copia(self, **mudancas) -> "Voz":
        d = self.para_dict()
        d.update(mudancas)
        v = Voz.de_dict(d)
        v.sistema = False
        return v

    # ---- referência de áudio
    def caminho_referencia(self) -> Path | None:
        if not self.referencia:
            return None
        p = Path(self.referencia)
        return p if p.is_absolute() else caminhos.REFERENCIAS / p

    # ---- assinaturas (chaves de cache)
    def assinatura_seca(self) -> str:
        """Tudo que muda o áudio que o motor produz (sem efeitos)."""
        ref = self.caminho_referencia()
        ref_sig = ""
        if ref and ref.exists():
            st = ref.stat()
            ref_sig = f"{ref.name}:{st.st_size}:{int(st.st_mtime)}"
        corpo = json.dumps(
            {"m": self.motor, "i": self.idioma, "b": sorted(self.base.items()), "r": ref_sig,
             "v": round(self.velocidade, 3), "p": sorted(self.parametros.items())},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha1(corpo.encode("utf-8")).hexdigest()[:16]

    def assinatura_efeitos(self) -> str:
        return hashlib.sha1(json.dumps(self.efeitos, sort_keys=True).encode("utf-8")).hexdigest()[:12]
