"""Janela para baixar (ou remover) vozes externas do catálogo do Piper, só inglês e português."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..vozes import catalogo_externo
from .base import Contexto, Tarefa, botao, rotulo

_QUALIDADE = {"high": "alta", "medium": "média", "low": "baixa", "x_low": "mínima"}


class DialogoVozesExternas(QDialog):
    def __init__(self, pai, ctx: Contexto) -> None:
        super().__init__(pai)
        self.ctx = ctx
        self._vozes: list[catalogo_externo.VozExterna] = []
        self._tarefa: Tarefa | None = None
        self.setWindowTitle("Baixar vozes externas")
        self.setMinimumSize(780, 560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(rotulo("Catálogo do Piper (inglês e português). Cada voz tem de 20 a 120 MB, roda na CPU e aparece em "
                             "Vozes → Vozes externas. Qualidade alta/média costuma ser a melhor para narração. "
                             "A licença varia por voz (veja o cartão em huggingface.co/rhasspy/piper-voices).", "subtitulo"))
        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(["Voz", "Idioma", "Região", "Qualidade", "Tamanho", "Estado"])
        h = self.tabela.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 6):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.tabela, 1)
        self.estado = rotulo("Carregando o catálogo…", "fraco")
        lay.addWidget(self.estado)
        bl = QHBoxLayout()
        self.b_baixar = botao("Baixar selecionada", "importar", "primario")
        self.b_remover = botao("Remover", "apagar", "perigo")
        self.b_atualizar = botao("Atualizar lista", "atualizar")
        b_fechar = botao("Fechar")
        self.b_baixar.clicked.connect(self._baixar)
        self.b_remover.clicked.connect(self._remover)
        self.b_atualizar.clicked.connect(lambda: self._carregar(True))
        b_fechar.clicked.connect(self.accept)
        for b in (self.b_baixar, self.b_remover, self.b_atualizar):
            bl.addWidget(b)
        bl.addStretch(1)
        bl.addWidget(b_fechar)
        lay.addLayout(bl)
        self._carregar(False)

    def _carregar(self, forcar: bool) -> None:
        self.estado.setText("Carregando o catálogo…")
        self._tarefa = Tarefa(lambda: catalogo_externo.listar(forcar), False, self)
        self._tarefa.terminou.connect(self._preencher)
        self._tarefa.falhou.connect(lambda m: self.estado.setText("Sem acesso ao catálogo (internet?): " + m.splitlines()[0]))
        self._tarefa.iniciar()

    def _preencher(self, vozes) -> None:
        self._vozes = vozes
        self.tabela.setRowCount(len(vozes))
        for i, v in enumerate(vozes):
            cel = [v.nome.replace("_", " ").title(), "Português" if v.idioma == "pt" else "Inglês", v.regiao,
                   _QUALIDADE.get(v.qualidade, v.qualidade), f"{v.tamanho_mb:.0f} MB", "baixada" if v.instalada else ""]
            for j, t in enumerate(cel):
                it = QTableWidgetItem(t)
                if j == 5 and t:
                    it.setForeground(Qt.GlobalColor.green)
                self.tabela.setItem(i, j, it)
        self.estado.setText(f"{len(vozes)} vozes no catálogo.")

    def _atual(self):
        r = self.tabela.currentRow()
        return self._vozes[r] if 0 <= r < len(self._vozes) else None

    def _baixar(self) -> None:
        v = self._atual()
        if not v or v.instalada:
            return
        self.b_baixar.setEnabled(False)
        self._tarefa = Tarefa(lambda andar: catalogo_externo.baixar(v, andar), True, self)
        self._tarefa.andamento.connect(lambda m: self.estado.setText(str(m)))
        self._tarefa.terminou.connect(lambda _r: (self.b_baixar.setEnabled(True), self._preencher(self._vozes), self.estado.setText(f"{v.chave} baixada.")))
        self._tarefa.falhou.connect(lambda m: (self.b_baixar.setEnabled(True), self.estado.setText("Falhou: " + m.splitlines()[0])))
        self._tarefa.iniciar()

    def _remover(self) -> None:
        v = self._atual()
        if v and v.instalada:
            catalogo_externo.remover(v.chave)
            self._preencher(self._vozes)
