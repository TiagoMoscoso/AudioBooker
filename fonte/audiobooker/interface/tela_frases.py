"""Estúdio de frases: escolha a voz, escreva a frase, gere takes, compare e guarde."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget)

from . import tema
from .base import Cartao, Contexto, Player, Tarefa, botao, icone_botao, rotulo
from .painel_intonacao import PainelIntonacao
from .seletor_voz import SeletorVoz


class TelaFrases(QWidget):
    def __init__(self, ctx: Contexto) -> None:
        super().__init__()
        self.ctx = ctx
        self._tarefa: Tarefa | None = None
        self._ultimo = None  # (voz, texto, audio)
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 24)
        raiz.setSpacing(20)

        # ---- esquerda: criar
        esq = QVBoxLayout()
        esq.setSpacing(14)
        esq.addWidget(rotulo("Frases", "titulo"))
        esq.addWidget(rotulo("Recrie frases curtas com qualquer voz: as de fábrica, as suas ou uma voz externa clonada.", "subtitulo"))

        c = Cartao()
        linha_voz = QHBoxLayout()
        linha_voz.addWidget(rotulo("Voz", "fraco"))
        self.voz = SeletorVoz(ctx)
        linha_voz.addWidget(self.voz, 1)
        c.lay.addLayout(linha_voz)
        self.texto = QPlainTextEdit()
        self.texto.setPlaceholderText("Escreva a frase aqui…  (marque trechos e palavras com a barra de Intonação; [pausa 1s] = silêncio)")
        self.texto.setMinimumHeight(120)
        self.texto.setMaximumHeight(240)
        c.lay.addWidget(self.texto)
        acoes = QHBoxLayout()
        self.n = QSpinBox()
        self.n.setRange(1, 6)
        self.n.setValue(1)
        self.n.setPrefix("takes: ")
        self.n.setMinimumWidth(110)
        self.n.setToolTip("Vozes clonadas variam a cada geração; gere vários takes e escolha o melhor.")
        self.gerar = botao("Gerar", "gerar", "primario")
        self.gerar.clicked.connect(self._gerar)
        acoes.addWidget(self.n)
        acoes.addStretch(1)
        acoes.addWidget(self.gerar)
        c.lay.addLayout(acoes)
        self.estado = rotulo("", "fraco")
        c.lay.addWidget(self.estado)
        esq.addWidget(c)

        self.intonacao = PainelIntonacao(self.texto)
        esq.addWidget(self.intonacao)
        self.voz.mudou.connect(self._motor_mudou)
        self._motor_mudou()

        self.player = Player()
        pc = Cartao("Resultado")
        pc.lay.addWidget(self.player)
        botoes = QHBoxLayout()
        self.b_guardar = botao("Guardar take", "salvar")
        self.b_guardar.clicked.connect(self._guardar)
        self.b_guardar.setEnabled(False)
        botoes.addWidget(self.b_guardar)
        botoes.addStretch(1)
        pc.lay.addLayout(botoes)
        esq.addWidget(pc)
        esq.addStretch(1)
        raiz.addLayout(esq, 3)

        # ---- direita: takes guardados
        dir_ = QVBoxLayout()
        dir_.setSpacing(10)
        dir_.addWidget(rotulo("Takes guardados", "secao"))
        self.lista = QListWidget()
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lista.itemDoubleClicked.connect(self._tocar_take)
        dir_.addWidget(self.lista, 1)
        barra = QHBoxLayout()
        self.b_tocar = icone_botao("tocar", "Tocar")
        self.b_fav = icone_botao("estrela", "Favorito")
        self.b_exp = icone_botao("exportar", "Exportar…")
        self.b_pasta = icone_botao("pasta", "Mostrar na pasta")
        self.b_apagar = icone_botao("apagar", "Apagar", "icone")
        self.b_tocar.clicked.connect(lambda: self._tocar_take(self.lista.currentItem()))
        self.b_fav.clicked.connect(self._favoritar)
        self.b_exp.clicked.connect(self._exportar)
        self.b_pasta.clicked.connect(self._mostrar)
        self.b_apagar.clicked.connect(self._apagar)
        for b in (self.b_tocar, self.b_fav, self.b_exp, self.b_pasta):
            barra.addWidget(b)
        barra.addStretch(1)
        barra.addWidget(self.b_apagar)
        dir_.addLayout(barra)
        self.player_take = Player()
        dir_.addWidget(self.player_take)
        raiz.addLayout(dir_, 2)
        self.recarregar()

    def _motor_mudou(self) -> None:
        voz = self.voz.voz()
        self.intonacao.definir_motor(self.ctx.ger.motor(voz.motor) if voz else None, voz)

    # ---- ações
    def recarregar(self) -> None:
        self.lista.clear()
        for t in self.ctx.estudio.takes():
            it = QListWidgetItem(("★ " if t.favorito else "") + f"{t.voz_nome}\n{t.texto[:70]}  ·  {t.duracao:.1f} s")
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            self.lista.addItem(it)

    def _take_atual(self):
        it = self.lista.currentItem()
        if not it:
            return None
        id_ = it.data(Qt.ItemDataRole.UserRole)
        return next((t for t in self.ctx.estudio.takes() if t.id == id_), None)

    def _gerar(self) -> None:
        voz = self.voz.voz()
        texto = self.texto.toPlainText().strip()
        if not voz or not texto:
            self.estado.setText("Escolha uma voz e escreva a frase.")
            return
        ok, msg = self.ctx.ger.motor(voz.motor).estado()
        if not ok:
            self.estado.setObjectName("erro")
            self.estado.setStyleSheet("")
            self.estado.setText(msg)
            return
        self.gerar.setEnabled(False)
        self.estado.setText("Gerando…")
        n = self.n.value()
        t0 = time.time()
        direcao = self.intonacao.direcao()
        avisos: list[str] = []

        def trabalho(andar):
            saidas = []
            for i in range(n):
                andar(f"Take {i + 1} de {n}…")
                saidas.append(self.ctx.estudio.gerar(voz, texto, progresso=andar, direcao=direcao, avisos=avisos))
            return saidas

        self._tarefa = Tarefa(trabalho, True, self)
        self._tarefa.andamento.connect(lambda m: self.estado.setText(str(m)))

        def pronto(saidas):
            self.gerar.setEnabled(True)
            dev = self.ctx.ger.motor(voz.motor).dispositivo.upper()
            self.estado.setText(f"Pronto em {time.time() - t0:.1f} s · {dev}")
            nota = self.ctx.ger.motor(voz.motor).nota_dispositivo
            if nota:
                self.estado.setText(self.estado.text() + f"  ·  {nota}")
            if avisos:
                self.estado.setText(self.estado.text() + "\nIgnorado pelo motor: " + "; ".join(avisos))
            # guarda todos os takes automaticamente; o último toca
            for audio in saidas:
                self._ultimo = (voz, texto, audio)
                self.ctx.estudio.guardar(voz, texto, audio)
            self.recarregar()
            self.lista.setCurrentRow(0)
            self.player.carregar_array(saidas[-1], 24000, True)
            self.b_guardar.setEnabled(False)

        self._tarefa.terminou.connect(pronto)
        self._tarefa.falhou.connect(self._falha)
        self._tarefa.iniciar()

    def _falha(self, msg: str) -> None:
        self.gerar.setEnabled(True)
        self.estado.setText("Não deu certo: " + msg.splitlines()[0])
        self.ctx.avisar(msg.splitlines()[0], "erro")

    def _guardar(self) -> None:
        if self._ultimo:
            self.ctx.estudio.guardar(*self._ultimo)
            self.recarregar()

    def _tocar_take(self, item) -> None:
        if not item:
            return
        t = next((t for t in self.ctx.estudio.takes() if t.id == item.data(Qt.ItemDataRole.UserRole)), None)
        if t and Path(t.arquivo).exists():
            self.player_take.carregar_arquivo(t.arquivo, True)

    def _favoritar(self) -> None:
        t = self._take_atual()
        if t:
            self.ctx.estudio.marcar(t.id, not t.favorito)
            self.recarregar()

    def _exportar(self) -> None:
        t = self._take_atual()
        if not t:
            return
        destino, filtro = QFileDialog.getSaveFileName(self, "Exportar frase", str(Path.home() / "Downloads" / Path(t.arquivo).stem),
                                                      "WAV (*.wav);;MP3 (*.mp3);;FLAC (*.flac)")
        if destino:
            fmt = {"WAV": "wav", "MP3": "mp3", "FLAC": "flac"}[filtro.split(" ")[0]]
            try:
                self.ctx.estudio.exportar(t, Path(destino), fmt)
                self.ctx.avisar("Frase exportada.", "ok")
            except Exception as e:  # noqa: BLE001
                self.ctx.avisar(str(e), "erro")

    def _mostrar(self) -> None:
        t = self._take_atual()
        if t:
            import subprocess

            subprocess.Popen(["explorer", "/select,", str(Path(t.arquivo))])

    def _apagar(self) -> None:
        t = self._take_atual()
        if t:
            self.ctx.estudio.apagar(t.id)
            self.recarregar()
