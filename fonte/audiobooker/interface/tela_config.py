"""Configurações: dispositivos (CPU/GPU), modelos, saída e cache."""
from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget, QFrame)

from .. import caminhos, dispositivos
from ..producao import cache
from .base import Combo, Cartao, Contexto, Tarefa, botao, rotulo


class TelaConfig(QWidget):
    def __init__(self, ctx: Contexto) -> None:
        super().__init__()
        self.ctx = ctx
        self._tarefa: Tarefa | None = None
        corpo = QVBoxLayout(self)
        corpo.setContentsMargins(0, 0, 0, 0)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        corpo.addWidget(rolagem)
        miolo = QWidget()
        rolagem.setWidget(miolo)
        raiz = QVBoxLayout(miolo)
        raiz.setContentsMargins(28, 24, 28, 24)
        raiz.setSpacing(14)
        raiz.addWidget(rotulo("Configurações", "titulo"))

        # ---- dispositivos
        info = dispositivos.detectar()
        c = Cartao("Processador e placa de vídeo")
        c.lay.addWidget(rotulo(info.resumo(), "subtitulo"))
        f = QFormLayout()
        self.dev_k = Combo()
        for cod, nome in (("auto", "Automático (GPU se funcionar, senão CPU)"), ("cpu", "Só CPU"), ("dml", "GPU via DirectML (AMD/Intel/NVIDIA)"),
                          ("cuda", "GPU via CUDA (NVIDIA)")):
            self.dev_k.addItem(nome, cod)
        self.dev_c = Combo()
        for cod, nome in (("auto", "Automático (CUDA se houver, senão CPU)"), ("cpu", "Só CPU")):
            self.dev_c.addItem(nome, cod)
        self.threads = QSpinBox()
        self.threads.setRange(0, 64)
        self.threads.setSpecialValueText("Todos os núcleos")
        f.addRow("Kokoro", self.dev_k)
        f.addRow("Chatterbox", self.dev_c)
        f.addRow("Threads de CPU", self.threads)
        c.lay.addLayout(f)
        c.lay.addWidget(rotulo("O Kokoro testa a GPU de verdade ao carregar e volta para a CPU sozinho se ela falhar (acontece com algumas placas AMD antigas)."
                               "O Chatterbox só usa GPU com CUDA (NVIDIA). Mudanças valem na próxima vez que o motor carregar.", "fraco"))
        raiz.addWidget(c)

        # ---- modelos
        cm = Cartao("Modelos de voz")
        self.estado_k = rotulo("", "fraco")
        self.estado_c = rotulo("", "fraco")
        self.b_baixar_k = botao("Baixar Kokoro (≈350 MB)", "importar")
        self.b_baixar_c = botao("Baixar Chatterbox Turbo (≈2 GB)", "importar")
        self.b_baixar_k.clicked.connect(lambda: self._baixar("kokoro"))
        self.b_baixar_c.clicked.connect(lambda: self._baixar("chatterbox"))
        for lbl, b in ((self.estado_k, self.b_baixar_k), (self.estado_c, self.b_baixar_c)):
            lh = QHBoxLayout()
            lh.addWidget(lbl, 1)
            lh.addWidget(b)
            cm.lay.addLayout(lh)
        self.prog = rotulo("", "fraco")
        cm.lay.addWidget(self.prog)
        raiz.addWidget(cm)

        # ---- saída
        cs = Cartao("Saída e masterização")
        fs = QFormLayout()
        self.pasta = QLineEdit()
        self.pasta.setPlaceholderText(str(caminhos.BIBLIOTECA))
        b = botao("Escolher…", "pasta")
        b.clicked.connect(self._escolher_pasta)
        lp = QHBoxLayout()
        lp.addWidget(self.pasta, 1)
        lp.addWidget(b)
        fs.addRow("Pasta dos audiobooks", lp)
        self.lufs = QDoubleSpinBox()
        self.lufs.setRange(-30, -12)
        self.lufs.setSuffix(" LUFS")
        fs.addRow("Volume alvo", self.lufs)
        self.p_frase, self.p_par, self.p_cena = (self._seg() for _ in range(3))
        fs.addRow("Pausa entre frases", self.p_frase)
        fs.addRow("Pausa entre parágrafos", self.p_par)
        fs.addRow("Pausa em quebra de cena", self.p_cena)
        cs.lay.addLayout(fs)
        raiz.addWidget(cs)

        # ---- cache
        cc = Cartao("Cache de trechos")
        self.cache_rot = rotulo("", "fraco")
        b_lim = botao("Limpar cache", "apagar", "perigo")
        b_lim.clicked.connect(self._limpar_cache)
        b_pasta = botao("Abrir pasta de dados", "pasta")
        b_pasta.clicked.connect(lambda: subprocess.Popen(["explorer", str(caminhos.LOCAL)]))
        lc = QHBoxLayout()
        lc.addWidget(self.cache_rot, 1)
        lc.addWidget(b_pasta)
        lc.addWidget(b_lim)
        cc.lay.addLayout(lc)
        cc.lay.addWidget(rotulo("Trechos já gerados ficam guardados: refazer um livro com a mesma voz é quase instantâneo, e efeitos novos não obrigam a gerar de novo.", "fraco"))
        raiz.addWidget(cc)
        raiz.addStretch(1)
        self._carregar()
        for w in (self.dev_k, self.dev_c):
            w.currentIndexChanged.connect(self._salvar)
        for w in (self.threads, self.lufs, self.p_frase, self.p_par, self.p_cena):
            w.valueChanged.connect(self._salvar)
        self.pasta.editingFinished.connect(self._salvar)

    def _seg(self) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(0.0, 6.0)
        s.setSingleStep(0.05)
        s.setSuffix(" s")
        return s

    def _carregar(self) -> None:
        c = self.ctx.cfg
        for w in (self.dev_k, self.dev_c, self.threads, self.lufs, self.p_frase, self.p_par, self.p_cena):
            w.blockSignals(True)
        self.dev_k.setCurrentIndex(max(0, self.dev_k.findData(c.dispositivo_kokoro)))
        self.dev_c.setCurrentIndex(max(0, self.dev_c.findData(c.dispositivo_chatterbox)))
        self.threads.setValue(c.threads)
        self.pasta.setText(c.pasta_saida)
        self.lufs.setValue(c.alvo_loudness)
        self.p_frase.setValue(c.pausa_frase)
        self.p_par.setValue(c.pausa_paragrafo)
        self.p_cena.setValue(c.pausa_cena)
        for w in (self.dev_k, self.dev_c, self.threads, self.lufs, self.p_frase, self.p_par, self.p_cena):
            w.blockSignals(False)
        self.atualizar_estado()

    def atualizar_estado(self) -> None:
        for lbl, b, nome in ((self.estado_k, self.b_baixar_k, "kokoro"), (self.estado_c, self.b_baixar_c, "chatterbox")):
            ok, msg = self.ctx.ger.motor(nome).estado()
            m = self.ctx.ger.motor(nome)
            lbl.setText(f"{m.rotulo}\n{msg}")
            b.setVisible(not ok or nome == "chatterbox")
        self.cache_rot.setText(f"Cache: {cache.tamanho_mb():.0f} MB")

    def _salvar(self) -> None:
        c = self.ctx.cfg
        c.dispositivo_kokoro = self.dev_k.currentData()
        c.dispositivo_chatterbox = self.dev_c.currentData()
        c.threads = self.threads.value()
        c.pasta_saida = self.pasta.text().strip()
        c.alvo_loudness = self.lufs.value()
        c.pausa_frase, c.pausa_paragrafo, c.pausa_cena = self.p_frase.value(), self.p_par.value(), self.p_cena.value()
        c.salvar()

    def _escolher_pasta(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Pasta dos audiobooks", self.pasta.text() or str(caminhos.BIBLIOTECA))
        if d:
            self.pasta.setText(d)
            self._salvar()

    def _limpar_cache(self) -> None:
        cache.limpar()
        self.atualizar_estado()

    def _baixar(self, nome: str) -> None:
        self.b_baixar_k.setEnabled(False)
        self.b_baixar_c.setEnabled(False)
        motor = self.ctx.ger.motor(nome)
        self._tarefa = Tarefa(lambda andar: motor.baixar(andar), True, self)
        self._tarefa.andamento.connect(lambda m: self.prog.setText(str(m)))

        def fim(_r=None):
            self.b_baixar_k.setEnabled(True)
            self.b_baixar_c.setEnabled(True)
            self.prog.setText("Pronto.")
            self.atualizar_estado()

        self._tarefa.terminou.connect(fim)
        self._tarefa.falhou.connect(lambda m: (self.b_baixar_k.setEnabled(True), self.b_baixar_c.setEnabled(True), self.prog.setText("Falhou: " + m.splitlines()[0])))
        self._tarefa.iniciar()
