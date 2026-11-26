"""Caixa de seleção de voz (minhas vozes primeiro, depois personagens e vozes de fábrica), com filtro por idioma."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox

from ..vozes.modelo import Voz
from .base import Contexto


class SeletorVoz(QComboBox):
    mudou = Signal()

    def __init__(self, ctx: Contexto, incluir_vazio: bool = False, rotulo_vazio: str = "(mesma do narrador)") -> None:
        super().__init__()
        self.ctx = ctx
        self._vazio = incluir_vazio
        self._rotulo_vazio = rotulo_vazio
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(22)
        self.setMinimumWidth(240)
        self.setMaxVisibleItems(18)
        self.recarregar()
        ctx.ao_mudar_vozes.append(self.recarregar)
        self.currentIndexChanged.connect(lambda _i: self.mudou.emit())

    def recarregar(self) -> None:
        atual = self.id_atual()
        self.blockSignals(True)
        self.clear()
        if self._vazio:
            self.addItem(self._rotulo_vazio, "")
        for v in self.ctx.bib.minhas():
            self.addItem(f"★ {v.nome}", v.id)
        fabrica = self.ctx.bib.fabrica()
        pers = [v for v in fabrica if "personagem" in v.tags]
        outras = [v for v in fabrica if "personagem" not in v.tags]
        for v in pers:
            self.addItem(f"{v.nome}", v.id)
        for v in outras:
            self.addItem(f"{v.nome}", v.id)
        padrao = atual or self.ctx.cfg.voz_padrao
        i = self.findData(padrao)
        self.setCurrentIndex(i if i >= 0 else 0)
        self.blockSignals(False)
        self.mudou.emit()

    def id_atual(self) -> str:
        d = self.currentData()
        return d if d is not None else ""

    def voz(self) -> Voz | None:
        id_ = self.id_atual()
        return self.ctx.bib.obter(id_) if id_ else None

    def definir(self, id_: str) -> None:
        i = self.findData(id_)
        if i >= 0:
            self.setCurrentIndex(i)
