"""Janela principal: barra lateral com as cinco áreas + mensagens na barra de estado."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import NOME, VERSAO, dispositivos
from . import tema
from .base import Contexto
from .tela_config import TelaConfig
from .tela_dicionario import TelaDicionario
from .tela_frases import TelaFrases
from .tela_livros import TelaLivros
from .tela_vozes import TelaVozes


class Janela(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.ctx = Contexto()
        self.ctx.avisar = self.mensagem
        self.setWindowTitle(NOME)
        self.setWindowIcon(tema.icone("frases", tema.DESTAQUE, 64))
        self.resize(1280, 800)
        self.setMinimumSize(1040, 680)

        raiz = QWidget()
        raiz.setObjectName("raiz")
        self.setCentralWidget(raiz)
        lay = QHBoxLayout(raiz)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(210)
        ll = QVBoxLayout(lateral)
        ll.setContentsMargins(0, 18, 0, 12)
        ll.setSpacing(2)
        marca = QLabel(NOME)
        marca.setStyleSheet(f"font-size: 14pt; font-weight: 600; color: {tema.DESTAQUE}; padding: 4px 16px 14px 16px;")
        ll.addWidget(marca)

        self.pilha = QStackedWidget()
        self.t_frases = TelaFrases(self.ctx)
        self.t_livros = TelaLivros(self.ctx)
        self.t_vozes = TelaVozes(self.ctx)
        self.t_dic = TelaDicionario(self.ctx)
        self.t_config = TelaConfig(self.ctx)
        self.t_livros.irParaDicionario.connect(self._ir_dicionario)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        for i, (glifo, nome, tela) in enumerate((("frases", "Frases", self.t_frases), ("livros", "Livros", self.t_livros),
                                                 ("vozes", "Vozes", self.t_vozes), ("dicionario", "Pronúncias", self.t_dic),
                                                 ("config", "Configurações", self.t_config))):
            b = QPushButton(nome)
            b.setIcon(tema.icone(glifo, tema.FRACO))
            b.setCheckable(True)
            b.setProperty("variante", "nav")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.toggled.connect(lambda marcado, bt=b, g=glifo: bt.setIcon(tema.icone(g, tema.DESTAQUE if marcado else tema.FRACO)))
            self._grupo.addButton(b, i)
            ll.addWidget(b)
            self.pilha.addWidget(tela)
            if i == 3:
                ll.addStretch(1)
        self._grupo.idClicked.connect(self._trocar)
        ll.addWidget(QLabel(f"v{VERSAO}", objectName="fraco", alignment=Qt.AlignmentFlag.AlignCenter))
        lay.addWidget(lateral)
        lay.addWidget(self.pilha, 1)
        self._grupo.button(0).setChecked(True)

        self.msg = QLabel("")
        self.disp = QLabel(dispositivos.detectar().resumo())
        sb = self.statusBar()
        sb.addWidget(self.msg, 1)
        sb.addPermanentWidget(self.disp)
        self._limpa = QTimer(self)
        self._limpa.setSingleShot(True)
        self._limpa.timeout.connect(lambda: self.msg.setText(""))

    def _trocar(self, i: int) -> None:
        self.pilha.setCurrentIndex(i)
        if self.pilha.currentWidget() is self.t_config:
            self.t_config.atualizar_estado()
        if self.pilha.currentWidget() is self.t_dic:
            self.t_dic.recarregar_escopos()

    def _ir_dicionario(self, id_projeto: str) -> None:
        self._grupo.button(3).setChecked(True)
        self.pilha.setCurrentWidget(self.t_dic)
        self.t_dic.recarregar_escopos(id_projeto)

    def closeEvent(self, ev) -> None:
        """Fecha sem deixar geração pendurada: cancela e espera o trecho atual terminar."""
        from .base import Tarefa

        self.t_livros._cancelar.set()
        for t in self.findChildren(Tarefa):
            if t.ativa:
                t._th.quit()
                t._th.wait(15000)
        from .base import PASTA_PREVIAS, Player, limpar_previas

        base_previas = lambda: PASTA_PREVIAS  # noqa: E731
        for p in self.findChildren(Player):  # solta os arquivos de prévia e apaga a pasta temporária
            p.liberar()
        import time

        from PySide6.QtWidgets import QApplication

        for _ in range(10):  # o Windows solta o arquivo de áudio alguns instantes depois do player parar
            QApplication.processEvents()
            time.sleep(0.05)
            limpar_previas()
            if not any(base_previas().glob("previa_*.wav")):
                break
        super().closeEvent(ev)

    def mensagem(self, texto: str, tipo: str = "info") -> None:
        cor = {"ok": tema.OK, "erro": tema.ERRO, "aviso": tema.AVISO}.get(tipo, tema.FRACO)
        self.msg.setStyleSheet(f"color: {cor};")
        self.msg.setText(texto)
        self._limpa.start(7000)
