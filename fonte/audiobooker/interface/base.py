"""Peças reaproveitadas pelas telas: contexto, tarefas em segundo plano, player, botões e cartões."""
from __future__ import annotations

import tempfile
import traceback
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf
from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from .. import caminhos
from ..configuracao import Configuracao
from ..motores.gerenciador import Gerenciador
from ..producao.frases import EstudioFrases
from ..producao.gerador import Gerador
from ..vozes.biblioteca import BibliotecaVozes
from . import tema


PASTA_PREVIAS = caminhos.LOCAL / "previas"   # áudios temporários dos botões "Ouvir"; apagados ao abrir e ao fechar o programa
RESPIRO_S = 0.3


def limpar_previas() -> int:
    """Apaga as prévias que sobraram (programa fechado à força, por exemplo). Devolve quantas apagou."""
    n = 0
    if PASTA_PREVIAS.exists():
        for f in PASTA_PREVIAS.glob("previa_*.wav"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


class Contexto:
    """Serviços compartilhados por todas as telas."""

    def __init__(self) -> None:
        self.cfg = Configuracao.carregar()
        self.ger = Gerenciador(self.cfg)
        self.bib = BibliotecaVozes()
        self.gerador = Gerador(self.ger, self.bib, self.cfg)
        self.estudio = EstudioFrases(self.ger, self.gerador)
        self.avisar: Callable[[str, str], None] = lambda texto, tipo="info": None  # a janela principal troca isto
        self.ao_mudar_vozes: list[Callable[[], None]] = []

    def vozes_mudaram(self) -> None:
        self.bib = BibliotecaVozes()
        self.gerador.bib = self.bib
        for f in self.ao_mudar_vozes:
            f()


# ---- tarefas em segundo plano -------------------------------------------------------------------------------
class _Trabalhador(QObject):
    terminou = Signal(object)
    falhou = Signal(str)
    andamento = Signal(object)

    def __init__(self, funcao: Callable, com_progresso: bool) -> None:
        super().__init__()
        self._f = funcao
        self._p = com_progresso

    def rodar(self) -> None:
        try:
            r = self._f(self.andamento.emit) if self._p else self._f()
            self.terminou.emit(r)
        except Exception as e:  # noqa: BLE001
            self.falhou.emit(f"{e}\n\n{traceback.format_exc()}")


class Tarefa(QObject):
    """Roda `funcao` fora da interface. Sinais: andamento(obj), terminou(obj), falhou(str)."""

    terminou = Signal(object)
    falhou = Signal(str)
    andamento = Signal(object)

    def __init__(self, funcao: Callable, com_progresso: bool = False, pai: QObject | None = None) -> None:
        super().__init__(pai)
        self._th = QThread()
        self._w = _Trabalhador(funcao, com_progresso)
        self._w.moveToThread(self._th)
        self._th.started.connect(self._w.rodar)
        self._w.terminou.connect(self._fim_ok)
        self._w.falhou.connect(self._fim_erro)
        self._w.andamento.connect(self.andamento)
        self.ativa = False

    def iniciar(self) -> None:
        self.ativa = True
        self._th.start()

    def _encerrar(self) -> None:
        self.ativa = False
        self._th.quit()

    def _fim_ok(self, r) -> None:
        self._encerrar()
        self.terminou.emit(r)

    def _fim_erro(self, msg) -> None:
        self._encerrar()
        self.falhou.emit(msg)


# ---- player -------------------------------------------------------------------------------------------------
class Player(QWidget):
    """Toca um arquivo ou um array numpy. Botão único tocar/pausar, barra de posição e tempo."""

    def __init__(self, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self._audio = QAudioOutput()
        self._media = QMediaPlayer()
        self._media.setAudioOutput(self._audio)
        self._tmp: Path | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.botao = icone_botao("tocar", "Tocar / pausar")
        self.botao.clicked.connect(self.alternar)
        self.barra = QSlider(Qt.Orientation.Horizontal)
        self.barra.setRange(0, 1000)
        self.barra.sliderMoved.connect(lambda v: self._media.setPosition(int(self._media.duration() * v / 1000)))
        self.tempo = QLabel("0:00 / 0:00")
        self.tempo.setObjectName("fraco")
        lay.addWidget(self.botao)
        lay.addWidget(self.barra, 1)
        lay.addWidget(self.tempo)
        self._media.positionChanged.connect(self._posicao)
        self._media.durationChanged.connect(lambda _d: self._posicao(self._media.position()))
        self._media.playbackStateChanged.connect(self._estado)
        self.setEnabled(False)

    def _soltar_antiga(self) -> None:
        """Libera o arquivo de prévia anterior (o Windows não deixa apagar arquivo aberto pelo player)."""
        self._media.stop()
        self._media.setSource(QUrl())
        if self._tmp is not None:
            try:
                self._tmp.unlink(missing_ok=True)
            except OSError:  # o backend de mídia solta o arquivo com atraso: limpar_previas() apaga na próxima
                pass
            self._tmp = None

    def carregar_arquivo(self, caminho: str | Path, tocar: bool = False) -> None:
        """Toca um arquivo. Acrescenta um respiro no começo (cópia temporária): a placa de som leva uns
        100–200 ms para acordar e, sem ele, a primeira palavra sai abafada."""
        self._soltar_antiga()
        try:
            x, sr = sf.read(str(caminho), dtype="float32")
            self._tocar_com_respiro(x, sr, tocar)
        except Exception:  # noqa: BLE001 - formato que o soundfile não lê (mp3...): toca direto
            self._media.setSource(QUrl.fromLocalFile(str(caminho)))
            self.setEnabled(True)
            if tocar:
                self._media.play()

    def carregar_array(self, x: np.ndarray, sr: int = 24000, tocar: bool = True) -> None:
        self._soltar_antiga()
        self._tocar_com_respiro(x, sr, tocar)

    def _tocar_com_respiro(self, x: np.ndarray, sr: int, tocar: bool) -> None:
        respiro = np.zeros((int(sr * RESPIRO_S),) + x.shape[1:], dtype=np.float32)
        PASTA_PREVIAS.mkdir(parents=True, exist_ok=True)
        arq = PASTA_PREVIAS / f"previa_{id(self) % 100000}_{int(np.random.rand() * 1e6)}.wav"
        sf.write(str(arq), np.concatenate([respiro, np.asarray(x, dtype=np.float32), respiro[: len(respiro) // 2]]), sr, subtype="PCM_16")
        self._tmp = arq
        self._media.setSource(QUrl.fromLocalFile(str(arq)))
        self.setEnabled(True)
        if tocar:
            self._media.play()

    def liberar(self) -> None:
        self._soltar_antiga()

    def alternar(self) -> None:
        if self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._media.pause()
        else:
            if self._media.position() >= max(0, self._media.duration() - 50):
                self._media.setPosition(0)
            self._media.play()

    def parar(self) -> None:
        self._media.stop()

    def _estado(self, _e) -> None:
        tocando = self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.botao.setIcon(tema.icone("pausar" if tocando else "tocar"))

    def _posicao(self, pos: int) -> None:
        dur = max(1, self._media.duration())
        if not self.barra.isSliderDown():
            self.barra.setValue(int(pos * 1000 / dur))
        self.tempo.setText(f"{_mmss(pos)} / {_mmss(self._media.duration())}")


def _mmss(ms: int) -> str:
    s = max(0, int(ms / 1000))
    return f"{s // 60}:{s % 60:02d}"


# ---- pequenos componentes -----------------------------------------------------------------------------------
def icone_botao(glifo: str, dica: str = "", variante: str = "icone") -> QPushButton:
    b = QPushButton()
    b.setIcon(tema.icone(glifo))
    b.setToolTip(dica)
    b.setProperty("variante", variante)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def botao(texto: str, glifo: str = "", variante: str = "", dica: str = "") -> QPushButton:
    b = QPushButton(texto)
    if glifo:
        cor = tema.FUNDO if variante == "primario" else tema.TEXTO
        b.setIcon(tema.icone(glifo, cor))
    if variante:
        b.setProperty("variante", variante)
    if dica:
        b.setToolTip(dica)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def rotulo(texto: str, nome: str = "") -> QLabel:
    r = QLabel(texto)
    if nome:
        r.setObjectName(nome)
    r.setWordWrap(True)
    return r


class Cartao(QFrame):
    def __init__(self, titulo: str = "", pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setObjectName("cartao")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 14, 16, 16)
        self.lay.setSpacing(10)
        if titulo:
            t = QLabel(titulo)
            t.setObjectName("secao")
            self.lay.addWidget(t)


def linha() -> QFrame:
    f = QFrame()
    f.setObjectName("linha")
    f.setFrameShape(QFrame.Shape.NoFrame)
    return f


def depois(ms: int, f: Callable) -> None:
    QTimer.singleShot(ms, f)


class Combo(QComboBox):
    """Caixa de seleção que não força a janela a alargar por causa de um item comprido."""

    def __init__(self, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(18)
