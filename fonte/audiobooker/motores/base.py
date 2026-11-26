"""Contrato dos motores de voz. Cada motor devolve áudio mono float32 a 24 kHz, sem efeitos."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

import numpy as np

from ..vozes.modelo import Voz

Progresso = Callable[[str], None]
SR = 24000


class MotorIndisponivel(RuntimeError):
    """O motor não está instalado/baixado; a mensagem diz o que fazer."""


# O que um motor pode fazer. A interface mostra todos os controles; os que o motor atual não tem ficam avisados
# (nada é "aproximado" em silêncio): trocar por um modelo mais forte liga os controles sem mexer no resto.
CAPACIDADES = {
    "emocao": "Intensidade emocional da fala (exagero)",
    "cfg": "Fidelidade ao texto (CFG)",
    "tags": "Tags de som no texto ([laugh], [sigh]...)",
    "clonagem": "Clonar uma voz a partir de um áudio",
    "fonemas": "Pronúncia por IPA",
    "instrucao": "Instrução de entrega em texto (sussurrar, gritar, tom triste...)",
    "palavra": "Controle de entonação por palavra",
    "descricao_de_voz": "Criar voz a partir de uma descrição",
    "multilingue": "Vários idiomas",
}


class Motor(ABC):
    nome = ""
    rotulo = ""
    sr = SR

    def __init__(self) -> None:
        self.dispositivo = "cpu"
        self.nota_dispositivo = ""

    def capacidades(self, voz: Voz | None = None) -> frozenset[str]:
        """Subconjunto de CAPACIDADES que este motor (e esta voz) realmente executa."""
        return frozenset()

    @abstractmethod
    def estado(self) -> tuple[bool, str]:
        """(pronto, mensagem). Pronto = modelo baixado e bibliotecas instaladas."""

    @abstractmethod
    def baixar(self, progresso: Progresso | None = None) -> None: ...

    @abstractmethod
    def carregar(self, preferencia: str, threads: int, progresso: Progresso | None = None) -> None: ...

    @abstractmethod
    def descarregar(self) -> None: ...

    @abstractmethod
    def sintetizar(self, texto: str, voz: Voz, pronuncias: dict[str, str] | None = None,
                   entrega: dict | None = None) -> np.ndarray:
        """`pronuncias`: palavra(minúscula) -> IPA, só para motores com "fonemas".
        `entrega`: {"emocao": 0-2, "cfg": 0-1, "instrucao": "texto"}; cada motor usa só o que suporta."""

    @property
    @abstractmethod
    def carregado(self) -> bool: ...
