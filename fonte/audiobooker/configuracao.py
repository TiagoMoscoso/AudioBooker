"""Configuração do programa (por PC)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from . import caminhos


@dataclass
class Configuracao:
    dispositivo_kokoro: str = "auto"      # auto | cpu | dml | cuda
    dispositivo_chatterbox: str = "auto"  # auto | cpu | cuda
    threads: int = 0                      # 0 = todos os núcleos
    pasta_saida: str = ""                 # vazio = biblioteca do programa
    voz_padrao: str = "chatterbox-padrao"
    idioma_padrao: str = "en"
    alvo_loudness: float = -19.0          # LUFS integrado
    pico_maximo: float = -3.0             # dBTP
    formato_padrao: str = "m4b"           # m4b | mp3 | flac | wav
    pausa_paragrafo: float = 0.85
    pausa_frase: float = 0.28
    pausa_cena: float = 1.8
    pausa_capitulo_inicio: float = 1.2
    anunciar_capitulos: bool = True

    @staticmethod
    def carregar() -> "Configuracao":
        cfg = Configuracao()
        try:
            dados = json.loads(caminhos.CONFIGURACAO.read_text(encoding="utf-8"))
            nomes = {f.name for f in fields(Configuracao)}
            for chave, valor in dados.items():
                if chave in nomes:
                    setattr(cfg, chave, valor)
        except (OSError, ValueError):
            pass
        return cfg

    def salvar(self) -> None:
        caminhos.garantir()
        tmp = caminhos.CONFIGURACAO.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(caminhos.CONFIGURACAO)

    @property
    def pasta_biblioteca(self):
        from pathlib import Path

        return Path(self.pasta_saida) if self.pasta_saida else caminhos.BIBLIOTECA
