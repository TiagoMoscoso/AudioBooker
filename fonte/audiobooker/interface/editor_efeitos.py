"""Editor da cadeia de efeitos: cada efeito vira um bloco com controles gerados a partir do catálogo."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QSlider, QVBoxLayout, QWidget

from ..vozes import efeitos as fx
from . import tema
from .base import botao, icone_botao


class _Controle(QWidget):
    mudou = Signal()

    def __init__(self, chave: str, rotulo: str, mn: float, mx: float, valor: float, passo: float, unidade: str) -> None:
        super().__init__()
        self.chave, self.passo, self.unidade = chave, passo, unidade
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        nome = QLabel(rotulo)
        nome.setObjectName("fraco")
        nome.setMinimumWidth(150)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(round(mn / passo)), int(round(mx / passo)))
        self.slider.setValue(int(round(valor / passo)))
        self.valor = QLabel()
        self.valor.setMinimumWidth(64)
        self.valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider.valueChanged.connect(self._mudou)
        lay.addWidget(nome)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.valor)
        self._atualizar()

    def numero(self) -> float:
        v = self.slider.value() * self.passo
        return round(v, 4)

    def _atualizar(self) -> None:
        v = self.numero()
        txt = f"{v:g}" if self.passo < 1 else f"{int(round(v))}"
        self.valor.setText(f"{txt} {self.unidade}".strip())

    def _mudou(self) -> None:
        self._atualizar()
        self.mudou.emit()


class _Bloco(QFrame):
    mudou = Signal()
    remover = Signal(object)
    mover = Signal(object, int)

    def __init__(self, efeito: dict) -> None:
        super().__init__()
        self.setObjectName("cartao")
        self.tipo = efeito["tipo"]
        info = fx.CATALOGO[self.tipo]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        topo = QHBoxLayout()
        self.ativo = QCheckBox(info["nome"])
        self.ativo.setChecked(efeito.get("ativo", True))
        self.ativo.setStyleSheet("font-weight: 600;")
        self.ativo.stateChanged.connect(lambda _s: self.mudou.emit())
        topo.addWidget(self.ativo, 1)
        b_cima, b_baixo, b_apagar = icone_botao("cima", "Subir"), icone_botao("baixo", "Descer"), icone_botao("apagar", "Remover", "icone")
        b_cima.clicked.connect(lambda: self.mover.emit(self, -1))
        b_baixo.clicked.connect(lambda: self.mover.emit(self, 1))
        b_apagar.clicked.connect(lambda: self.remover.emit(self))
        for b in (b_cima, b_baixo, b_apagar):
            topo.addWidget(b)
        lay.addLayout(topo)
        ajuda = QLabel(info["ajuda"])
        ajuda.setObjectName("fraco")
        ajuda.setWordWrap(True)
        lay.addWidget(ajuda)
        self.controles: list[_Controle] = []
        for chave, rot, mn, mx, pad, passo, un in info["params"]:
            c = _Controle(chave, rot, mn, mx, float(efeito.get(chave, pad)), passo, un)
            c.mudou.connect(self.mudou)
            self.controles.append(c)
            lay.addWidget(c)

    def para_dict(self) -> dict:
        d = {"tipo": self.tipo}
        for c in self.controles:
            d[c.chave] = c.numero()
        if not self.ativo.isChecked():
            d["ativo"] = False
        return d


class EditorEfeitos(QWidget):
    mudou = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._blocos: list[_Bloco] = []
        self._miolo = QVBoxLayout()
        self._miolo.setSpacing(8)
        self._lay.addLayout(self._miolo)
        self.b_add = botao("Adicionar efeito", "mais")
        menu = QMenu(self)
        for tipo, info in fx.CATALOGO.items():
            menu.addAction(info["nome"], lambda t=tipo: self._adicionar(fx.padrao(t)))
        self.b_add.setMenu(menu)
        linha = QHBoxLayout()
        linha.addWidget(self.b_add)
        linha.addStretch(1)
        self._lay.addLayout(linha)

    def definir(self, efeitos: list[dict]) -> None:
        for b in self._blocos:
            b.setParent(None)
            b.deleteLater()
        self._blocos.clear()
        for e in efeitos:
            if e.get("tipo") in fx.CATALOGO:
                self._criar(e)
        self.mudou.emit()

    def efeitos(self) -> list[dict]:
        return [b.para_dict() for b in self._blocos]

    def _criar(self, e: dict) -> None:
        b = _Bloco(e)
        b.mudou.connect(self.mudou)
        b.remover.connect(self._remover)
        b.mover.connect(self._mover)
        self._blocos.append(b)
        self._miolo.addWidget(b)

    def _adicionar(self, e: dict) -> None:
        self._criar(e)
        self.mudou.emit()

    def _remover(self, b: _Bloco) -> None:
        self._blocos.remove(b)
        b.setParent(None)
        b.deleteLater()
        self.mudou.emit()

    def _mover(self, b: _Bloco, delta: int) -> None:
        i = self._blocos.index(b)
        j = i + delta
        if 0 <= j < len(self._blocos):
            dados = self.efeitos()
            dados[i], dados[j] = dados[j], dados[i]
            self.definir(dados)
