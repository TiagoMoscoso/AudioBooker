"""Forma comum de qualquer livro lido: seções, com blocos de título e de texto."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Bloco:
    tipo: str          # titulo | texto
    texto: str
    nivel: int = 1     # só para títulos (1 = principal)


@dataclass
class Secao:
    titulo: str
    blocos: list[Bloco] = field(default_factory=list)

    @property
    def palavras(self) -> int:
        return sum(len(b.texto.split()) for b in self.blocos if b.tipo == "texto")


@dataclass
class Documento:
    titulo: str
    autor: str = ""
    idioma: str = ""
    secoes: list[Secao] = field(default_factory=list)
    capa: bytes | None = None
    formato: str = ""
    origem: Path | None = None

    @property
    def palavras(self) -> int:
        return sum(s.palavras for s in self.secoes)


class ErroDocumento(RuntimeError):
    """Mensagem já pronta para mostrar ao usuário."""
