"""Painel de intonação: direção geral + barra para marcar trechos e palavras no texto.

Mostra sempre o que o motor da voz escolhida executa e o que ele IGNORA (nada é imitado em silêncio).
"""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton,
                               QWidget)

from ..motores.base import CAPACIDADES, Motor
from ..texto.direcoes import ESTILOS, Direcao
from .base import Cartao, botao, rotulo


def _spin(minimo: float, maximo: float, passo: float, sufixo: str, auto: str = "auto") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(minimo, maximo)
    s.setSingleStep(passo)
    s.setDecimals(2)
    s.setSuffix(sufixo)
    s.setMinimumHeight(32)
    s.setSpecialValueText(auto)   # valor mínimo = "auto" (não define)
    s.setValue(minimo)
    return s


class PainelIntonacao(Cartao):
    """`texto`: o editor onde a marcação é inserida. `direcao()` devolve a intonação geral."""

    def __init__(self, texto: QPlainTextEdit, so_marcacao: bool = False) -> None:
        super().__init__("Intonação" if not so_marcacao else "")
        self.texto = texto
        self._motor: Motor | None = None
        self._voz = None

        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        self.estilo = QComboBox()
        self.estilo.addItem("sem estilo", "")
        for k, e in ESTILOS.items():
            if k != "neutro":
                self.estilo.addItem(e["nome"], k)
        self.estilo.setToolTip("Estilo geral para toda a frase. Estilos que o motor não executa são ignorados e avisados.")
        self.emocao = _spin(-0.1, 2.0, 0.1, "")
        self.emocao.setToolTip("Intensidade emocional do motor (0 a 2).")
        self.velocidade = _spin(0.40, 1.6, 0.05, "×")
        self.velocidade.setToolTip("Ritmo (Rubber Band, sem mudar o timbre).")
        self.tom = _spin(-6.5, 6.0, 0.5, " st")
        self.tom.setToolTip("Tom em semitons (acima de ±3 pode ter artefatos).")
        self.volume = _spin(-13.0, 6.0, 1.0, " dB")
        for i, (nome, w) in enumerate((("Estilo", self.estilo), ("Emoção", self.emocao), ("Velocidade", self.velocidade),
                                       ("Tom", self.tom), ("Volume", self.volume))):
            g.addWidget(rotulo(nome, "fraco"), i // 3 * 2, i % 3)
            g.addWidget(w, i // 3 * 2 + 1, i % 3)
        if not so_marcacao:
            self.lay.addLayout(g)

        # barra de marcação: age sobre o texto selecionado (ou insere no cursor)
        barra = QHBoxLayout()
        barra.addWidget(rotulo("Marcar seleção", "fraco"))
        self.b_enfase = botao("Ênfase", dica="Destaca a palavra selecionada (só motores com controle por palavra).")
        self.b_enfase.clicked.connect(lambda: self._envolver("ênfase"))
        self.b_estilo = botao("Estilo ▾")
        m = QMenu(self.b_estilo)
        for k, e in ESTILOS.items():
            if k != "neutro":
                m.addAction(e["nome"], lambda k=k: self._envolver(f"estilo {k}", "estilo"))
        self.b_estilo.setMenu(m)
        self.b_outros = botao("Controle ▾")
        m2 = QMenu(self.b_outros)
        for rot, tag, fecha in (("Emoção 0,8", "emoção 0.8", "emoção"), ("Velocidade 0,85×", "velocidade 0.85", "velocidade"),
                                ("Velocidade 1,15×", "velocidade 1.15", "velocidade"), ("Tom −2", "tom -2", "tom"),
                                ("Tom +2", "tom 2", "tom"), ("Volume −6 dB", "volume -6", "volume"),
                                ("Instrução…", "instrução: fale devagar", "instrução")):
            m2.addAction(rot, lambda t=tag, f=fecha: self._envolver(t, f))
        m2.addSeparator()
        m2.addAction("Pausa 1 s", lambda: self._inserir("[pausa 1s]"))
        m2.addAction("Pausa 0,4 s", lambda: self._inserir("[pausa 0.4s]"))
        m2.addAction("Som: risada", lambda: self._inserir("[tag laugh]"))
        m2.addAction("Som: suspiro", lambda: self._inserir("[tag sigh]"))
        self.b_outros.setMenu(m2)
        for b in (self.b_enfase, self.b_estilo, self.b_outros):
            barra.addWidget(b)
        barra.addStretch(1)
        self.lay.addLayout(barra)

        self.suporte = QLabel()
        self.suporte.setWordWrap(True)
        self.suporte.setObjectName("fraco")
        self.lay.addWidget(self.suporte)

    # ---- marcação
    def _envolver(self, abre: str, fecha: str | None = None) -> None:
        fecha = fecha or abre
        c = self.texto.textCursor()
        sel = c.selectedText().replace(" ", "\n")
        c.insertText(f"[{abre}]{sel}[/{fecha}]")
        self.texto.setTextCursor(c)
        self.texto.setFocus()

    def _inserir(self, tag: str) -> None:
        self.texto.textCursor().insertText(tag)
        self.texto.setFocus()

    # ---- estado
    def direcao(self) -> Direcao:
        def v(w: QDoubleSpinBox, neutro: float | None = None):
            return None if w.value() <= w.minimum() else w.value()

        vel = v(self.velocidade)
        return Direcao(estilo=self.estilo.currentData() or "", emocao=v(self.emocao), velocidade=vel, tom=v(self.tom), volume=v(self.volume))

    def definir_motor(self, motor: Motor | None, voz=None) -> None:
        """Atualiza o resumo do que o motor da voz atual executa e o que ignora."""
        self._motor = motor
        if motor is None:
            self.suporte.setText("")
            return
        caps = set(motor.capacidades(voz))
        ok = ["velocidade", "tom", "volume", "pausa"] + [CAPACIDADES[c].lower() for c in ("emocao", "cfg", "tags", "palavra", "instrucao")
                                                          if c in caps]
        nao = [CAPACIDADES[c].lower() for c in ("emocao", "tags", "palavra", "instrucao") if c not in caps]
        txt = "Este motor executa: " + ", ".join(ok) + "."
        if nao:
            txt += "  Ignora (e avisa): " + ", ".join(nao) + "."
        self.suporte.setText(txt)
