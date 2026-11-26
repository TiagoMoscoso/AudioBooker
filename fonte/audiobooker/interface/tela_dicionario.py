"""Dicionário de pronúncias: global ou por livro, com grafia sonora e IPA, teste de áudio, sugestões e PLS."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit,
                               QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..producao.projeto import Projeto
from ..texto import pronuncias as pron
from ..texto.pronuncias import Entrada
from . import tema
from .base import Combo, Cartao, Contexto, Player, Tarefa, botao, rotulo
from .seletor_voz import SeletorVoz

_TIPOS = [("palavra", "Palavra"), ("abreviacao", "Abreviação"), ("regex", "Padrão (regex)")]
_IDIOMAS = [("*", "Todos"), ("en", "Inglês"), ("pt", "Português")]


class _Sugestoes(QDialog):
    def __init__(self, pai: QWidget, itens: list[tuple[str, int, str]]) -> None:
        super().__init__(pai)
        self.setWindowTitle("Termos que podem sair errados")
        self.setMinimumSize(520, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(rotulo("Siglas, nomes próprios repetidos e palavras estrangeiras ou raras do livro. Marque os que quer ensinar.", "subtitulo"))
        self.lista = QListWidget()
        for w, n, motivo in itens:
            it = QListWidgetItem(f"{w}   ·   {n}×   ·   {motivo}")
            it.setData(Qt.ItemDataRole.UserRole, w)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.lista.addItem(it)
        lay.addWidget(self.lista, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Adicionar ao dicionário")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Fechar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def escolhidas(self) -> list[str]:
        return [self.lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista.count())
                if self.lista.item(i).checkState() == Qt.CheckState.Checked]


class TelaDicionario(QWidget):
    def __init__(self, ctx: Contexto) -> None:
        super().__init__()
        self.ctx = ctx
        self._entradas: list[Entrada] = []
        self._carregando = False
        self._tarefa: Tarefa | None = None
        self._salvar_timer = QTimer(self)
        self._salvar_timer.setSingleShot(True)
        self._salvar_timer.setInterval(500)
        self._salvar_timer.timeout.connect(self._gravar)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 24)
        raiz.setSpacing(14)
        raiz.addWidget(rotulo("Dicionário de pronúncias", "titulo"))
        raiz.addWidget(rotulo("Ensine como ler nomes, siglas e abreviações. Grafia sonora funciona em qualquer voz; o IPA é mais preciso e vale nas vozes Kokoro.", "subtitulo"))

        topo = QHBoxLayout()
        self.escopo = Combo()
        self.escopo.setMinimumWidth(280)
        self.escopo.currentIndexChanged.connect(self._trocou_escopo)
        topo.addWidget(rotulo("Escopo", "fraco"))
        topo.addWidget(self.escopo)
        topo.addStretch(1)
        self.b_sugerir = botao("Sugerir termos do livro", "atualizar")
        self.b_sugerir.clicked.connect(self._sugerir)
        self.b_imp = botao("Importar PLS…", "importar")
        self.b_exp = botao("Exportar PLS…", "exportar")
        self.b_imp.clicked.connect(self._importar)
        self.b_exp.clicked.connect(self._exportar)
        for b in (self.b_sugerir, self.b_imp, self.b_exp):
            topo.addWidget(b)
        raiz.addLayout(topo)

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(["Palavra / padrão", "Grafia sonora", "IPA", "Tipo", "Idioma", "Nota"])
        h = self.tabela.horizontalHeader()
        for i, largura in ((0, 170), (1, 190), (2, 170), (3, 130), (4, 110)):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            self.tabela.setColumnWidth(i, largura)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(40)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.itemChanged.connect(self._mudou)
        raiz.addWidget(self.tabela, 1)

        barra = QHBoxLayout()
        b_add = botao("Adicionar", "mais", "primario")
        b_del = botao("Remover", "apagar", "perigo")
        b_add.clicked.connect(self._adicionar)
        b_del.clicked.connect(self._remover)
        barra.addWidget(b_add)
        barra.addWidget(b_del)
        barra.addStretch(1)
        raiz.addLayout(barra)

        ct = Cartao("Ouvir como fica")
        lt = QHBoxLayout()
        self.voz = SeletorVoz(ctx)
        self.teste = QLineEdit()
        self.teste.setPlaceholderText("Frase de teste (vazio = usa a palavra selecionada)")
        self.b_ouvir = botao("Ouvir", "tocar", "primario")
        self.b_ouvir.clicked.connect(self._ouvir)
        lt.addWidget(self.voz)
        lt.addWidget(self.teste, 1)
        lt.addWidget(self.b_ouvir)
        ct.lay.addLayout(lt)
        self.player = Player()
        ct.lay.addWidget(self.player)
        self.estado = rotulo("", "fraco")
        ct.lay.addWidget(self.estado)
        raiz.addWidget(ct)
        self.recarregar_escopos()

    # ---- escopo
    def recarregar_escopos(self, escolher_projeto: str | None = None) -> None:
        self.escopo.blockSignals(True)
        self.escopo.clear()
        self.escopo.addItem("Global — vale para todos os livros", "")
        for p in Projeto.listar():
            self.escopo.addItem(f"Livro: {p.titulo}", p.id)
        if escolher_projeto:
            i = self.escopo.findData(escolher_projeto)
            if i >= 0:
                self.escopo.setCurrentIndex(i)
        self.escopo.blockSignals(False)
        self._trocou_escopo()

    def _livro_id(self) -> str:
        return self.escopo.currentData() or ""

    def _trocou_escopo(self) -> None:
        self._carregando = True
        id_ = self._livro_id()
        self._entradas = pron.carregar_livro(id_) if id_ else pron.carregar_global()
        self.b_sugerir.setEnabled(bool(id_))
        self.tabela.setRowCount(0)
        for e in self._entradas:
            self._linha(e)
        self._carregando = False

    # ---- tabela
    def _linha(self, e: Entrada) -> None:
        r = self.tabela.rowCount()
        self.tabela.insertRow(r)
        for j, txt in enumerate((e.palavra, e.respelling, e.ipa)):
            self.tabela.setItem(r, j if j < 3 else j, QTableWidgetItem(txt))
        tipo = Combo()
        for cod, nm in _TIPOS:
            tipo.addItem(nm, cod)
        tipo.setCurrentIndex(max(0, tipo.findData(e.tipo)))
        tipo.currentIndexChanged.connect(lambda _i: self._mudou(None))
        idi = Combo()
        for cod, nm in _IDIOMAS:
            idi.addItem(nm, cod)
        idi.setCurrentIndex(max(0, idi.findData(e.idioma)))
        idi.currentIndexChanged.connect(lambda _i: self._mudou(None))
        self.tabela.setCellWidget(r, 3, tipo)
        self.tabela.setCellWidget(r, 4, idi)
        self.tabela.setItem(r, 5, QTableWidgetItem(e.nota))

    def _adicionar(self, palavra: str = "") -> None:
        self._carregando = True
        self._linha(Entrada(palavra if isinstance(palavra, str) else "", idioma="*"))
        self._carregando = False
        self.tabela.setCurrentCell(self.tabela.rowCount() - 1, 0)
        self.tabela.editItem(self.tabela.item(self.tabela.rowCount() - 1, 1 if palavra else 0))

    def _remover(self) -> None:
        r = self.tabela.currentRow()
        if r >= 0:
            self.tabela.removeRow(r)
            self._mudou(None)

    def _ler_tabela(self) -> list[Entrada]:
        saida = []
        for r in range(self.tabela.rowCount()):
            t = lambda c: (self.tabela.item(r, c).text().strip() if self.tabela.item(r, c) else "")  # noqa: E731
            saida.append(Entrada(t(0), t(1), t(2), self.tabela.cellWidget(r, 3).currentData(),
                                 self.tabela.cellWidget(r, 4).currentData(), False, t(5)))
        return saida

    def _mudou(self, _item) -> None:
        if not self._carregando:
            self._salvar_timer.start()

    def _gravar(self) -> None:
        entradas = self._ler_tabela()
        id_ = self._livro_id()
        (pron.salvar_livro(id_, entradas) if id_ else pron.salvar_global(entradas))

    # ---- sugestões / PLS
    def _sugerir(self) -> None:
        id_ = self._livro_id()
        if not id_:
            return
        proj = Projeto.carregar(id_)
        self.b_sugerir.setEnabled(False)
        self.b_sugerir.setText("Procurando…")

        def trabalho():
            texto = "\n\n".join(c.texto for c in proj.capitulos if c.incluir)
            ja = {e.palavra for e in self._ler_tabela()} | {e.palavra for e in pron.Dicionario(proj.idioma, id_).entradas}
            return pron.candidatos(texto, proj.idioma, ja)

        self._tarefa = Tarefa(trabalho, False, self)

        def pronto(itens):
            self.b_sugerir.setEnabled(True)
            self.b_sugerir.setText("Sugerir termos do livro")
            d = _Sugestoes(self, itens)
            if d.exec() == QDialog.DialogCode.Accepted:
                self._carregando = True
                for w in d.escolhidas():
                    self._linha(Entrada(w, idioma=proj.idioma))
                self._carregando = False
                self.estado.setText("Preencha a grafia sonora (ou IPA) dos termos adicionados.")

        self._tarefa.terminou.connect(pronto)
        self._tarefa.iniciar()

    def _importar(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Importar léxico", str(Path.home() / "Downloads"), "Léxico de pronúncia (*.pls *.xml)")
        if f:
            try:
                novas = pron.importar_pls(Path(f))
            except Exception as e:  # noqa: BLE001
                self.ctx.avisar(f"Arquivo inválido: {e}", "erro")
                return
            self._carregando = True
            for e in novas:
                self._linha(e)
            self._carregando = False
            self._mudou(None)
            self.ctx.avisar(f"{len(novas)} entradas importadas.", "ok")

    def _exportar(self) -> None:
        f, _ = QFileDialog.getSaveFileName(self, "Exportar léxico", str(Path.home() / "Downloads" / "pronuncias.pls"), "Léxico de pronúncia (*.pls)")
        if f:
            pron.exportar_pls(self._ler_tabela(), Path(f))
            self.ctx.avisar("Léxico exportado (padrão W3C PLS).", "ok")

    # ---- teste
    def _ouvir(self) -> None:
        voz = self.voz.voz()
        if not voz:
            return
        r = self.tabela.currentRow()
        entradas = self._ler_tabela()
        palavra = entradas[r].palavra if 0 <= r < len(entradas) else ""
        texto = self.teste.text().strip() or (f"{palavra}. {palavra}." if palavra else "")
        if not texto:
            return
        ok, msg = self.ctx.ger.motor(voz.motor).estado()
        if not ok:
            self.estado.setText(msg)
            return
        self._gravar()
        self.b_ouvir.setEnabled(False)
        self.estado.setText("Gerando…")
        proj_id = self._livro_id() or None
        idioma = voz.idioma

        def trabalho(andar):
            from ..producao.gerador import preparar_fala

            dic = pron.Dicionario(idioma, proj_id)
            txt, ipa = preparar_fala(texto, dic, idioma, voz.motor == "kokoro")
            return self.ctx.gerador.sintetizar(voz, txt, ipa, idioma, None, andar)

        self._tarefa = Tarefa(trabalho, True, self)
        self._tarefa.terminou.connect(lambda x: (self.b_ouvir.setEnabled(True), self.estado.setText(""), self.player.carregar_array(x, 24000, True)))
        self._tarefa.falhou.connect(lambda m: (self.b_ouvir.setEnabled(True), self.estado.setText("Não deu certo: " + m.splitlines()[0])))
        self._tarefa.iniciar()
