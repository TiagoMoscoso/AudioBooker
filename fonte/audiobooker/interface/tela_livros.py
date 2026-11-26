"""Livros: importar, revisar capítulos, montar o elenco e gerar o audiobook inteiro (com retomada)."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QScrollArea, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import caminhos
from ..audio.masterizacao import PERFIS
from ..documentos import capitulos as cap_mod
from ..documentos import leitor
from ..documentos.modelo import ErroDocumento
from ..producao.gerador import Cancelado
from ..producao.projeto import Projeto
from ..texto import elenco as _elenco
from . import tema
from .base import Combo, Cartao, Contexto, Player, Tarefa, botao, icone_botao, rotulo
from .seletor_voz import SeletorVoz

PALAVRAS_POR_MIN = 150


def _hms(seg: float) -> str:
    s = int(seg)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class TelaLivros(QWidget):
    irParaDicionario = Signal(str)  # id do projeto

    def __init__(self, ctx: Contexto) -> None:
        super().__init__()
        self.ctx = ctx
        self.proj: Projeto | None = None
        self._tarefa: Tarefa | None = None
        self._cancelar = threading.Event()
        self._rodando = False
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        self.pilha = QStackedWidget()
        raiz.addWidget(self.pilha)
        self.pilha.addWidget(self._tela_inicio())
        self.pilha.addWidget(self._tela_projeto())
        self.recarregar_lista()

    # =============================================================================== início
    def _tela_inicio(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        lay.addWidget(rotulo("Livros", "titulo"))
        lay.addWidget(rotulo("Transforme um livro inteiro em audiobook, com voz de fábrica, mistura, clonada ou com efeitos.", "subtitulo"))
        c = Cartao("Novo audiobook")
        c.lay.addWidget(rotulo("EPUB, PDF (com texto), DOCX, MOBI/AZW, TXT ou Markdown. Tudo é processado neste computador.", "fraco"))
        b = botao("Abrir livro…", "abrir", "primario")
        b.clicked.connect(self._abrir_livro)
        lb = QHBoxLayout()
        lb.addWidget(b)
        lb.addStretch(1)
        c.lay.addLayout(lb)
        self.erro_inicio = rotulo("", "erro")
        c.lay.addWidget(self.erro_inicio)
        lay.addWidget(c)
        lay.addWidget(rotulo("Projetos em andamento", "secao"))
        self.lista_proj = QListWidget()
        self.lista_proj.itemDoubleClicked.connect(self._abrir_projeto)
        lay.addWidget(self.lista_proj, 1)
        lb2 = QHBoxLayout()
        b_abrir = botao("Abrir projeto", "abrir")
        b_abrir.clicked.connect(lambda: self._abrir_projeto(self.lista_proj.currentItem()))
        b_apagar = botao("Apagar projeto", "apagar", "perigo")
        b_apagar.clicked.connect(self._apagar_projeto)
        lb2.addWidget(b_abrir)
        lb2.addWidget(b_apagar)
        lb2.addStretch(1)
        lay.addLayout(lb2)
        return w

    def recarregar_lista(self) -> None:
        self.lista_proj.clear()
        for p in Projeto.listar():
            incl = [c for c in p.capitulos if c.incluir]
            prontos = sum(1 for c in incl if p.prontos.get(c.id, {}).get("hash") == p.hash_capitulo(c))
            it = QListWidgetItem(f"{p.titulo}\n{p.autor or 'autor desconhecido'}  ·  {prontos}/{len(incl)} capítulos prontos")
            it.setData(Qt.ItemDataRole.UserRole, p.id)
            self.lista_proj.addItem(it)

    def _apagar_projeto(self) -> None:
        it = self.lista_proj.currentItem()
        if it:
            Projeto.carregar(it.data(Qt.ItemDataRole.UserRole)).apagar()
            self.recarregar_lista()

    # =============================================================================== projeto
    def _tela_projeto(self) -> QWidget:
        w = QWidget()
        raiz = QVBoxLayout(w)
        raiz.setContentsMargins(28, 20, 28, 20)
        raiz.setSpacing(12)
        topo = QHBoxLayout()
        self.b_voltar = icone_botao("cima", "Voltar à lista")
        self.b_voltar.setIcon(tema.icone("cancelar"))
        self.b_voltar.clicked.connect(self._voltar)
        self.titulo = rotulo("", "titulo")
        self.info = rotulo("", "subtitulo")
        cab = QVBoxLayout()
        cab.addWidget(self.titulo)
        cab.addWidget(self.info)
        topo.addLayout(cab, 1)
        topo.addWidget(self.b_voltar, 0, Qt.AlignmentFlag.AlignTop)
        raiz.addLayout(topo)

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        # ---- capítulos
        cc = Cartao("Capítulos")
        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["", "Título", "Palavras", "Estado"])
        h = self.tabela.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.itemChanged.connect(self._editou_item)
        cc.lay.addWidget(self.tabela, 1)
        bt = QHBoxLayout()
        b_todos, b_nenhum = botao("Marcar todos"), botao("Desmarcar todos")
        b_todos.clicked.connect(lambda: self._marcar_todos(True))
        b_nenhum.clicked.connect(lambda: self._marcar_todos(False))
        self.b_juntar = botao("Juntar com o anterior", "", "", "Une o capítulo selecionado ao de cima")
        self.b_juntar.clicked.connect(self._juntar)
        self.b_previa = botao("Ouvir prévia", "tocar", "", "Gera só o começo do capítulo selecionado para testar a voz")
        self.b_previa.clicked.connect(self._previa)
        self.b_roteiro = botao("Roteiro…", "", "", "Revisão manual: quem fala cada parágrafo, estilo e marcação de intonação")
        self.b_roteiro.clicked.connect(self._roteiro)
        for b in (b_todos, b_nenhum, self.b_juntar, self.b_previa, self.b_roteiro):
            bt.addWidget(b)
        bt.addStretch(1)
        cc.lay.addLayout(bt)
        self.player = Player()
        cc.lay.addWidget(self.player)
        self.estado_previa = rotulo("", "fraco")
        cc.lay.addWidget(self.estado_previa)
        corpo.addWidget(cc, 3)

        # ---- ajustes
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setMinimumWidth(400)
        rolagem.setMaximumWidth(460)
        miolo = QWidget()
        rolagem.setWidget(miolo)
        ml = QVBoxLayout(miolo)
        ml.setContentsMargins(0, 0, 8, 0)
        ml.setSpacing(12)

        cv = Cartao("Voz e elenco")
        f = QFormLayout()
        self.narrador = SeletorVoz(self.ctx)
        self.falas = SeletorVoz(self.ctx, True, "(narrador lê as falas)")
        f.addRow("Narrador", self.narrador)
        f.addRow("Falas", self.falas)
        cv.lay.addLayout(f)
        self.separar = QCheckBox("Vozes diferentes para personagens")
        self.separar.setToolTip("Separa narração e diálogo e dá uma voz para cada personagem detectado.")
        self.separar.toggled.connect(self._alternou_separar)
        cv.lay.addWidget(self.separar)
        self.contexto = QCheckBox("Sugerir estilo pelo contexto (“she whispered…”)")
        self.contexto.setChecked(True)
        self.contexto.setToolTip("Lê o verbo e o advérbio ao redor de cada fala e sugere o estilo. Só vale o que o modelo executa; "
                                 "o resto é ignorado e listado. Revise em Roteiro….")
        cv.lay.addWidget(self.contexto)
        self.painel_personagens = QWidget()
        pl = QVBoxLayout(self.painel_personagens)
        pl.setContentsMargins(0, 0, 0, 0)
        self.b_detectar = botao("Detectar personagens", "atualizar")
        self.b_detectar.clicked.connect(self._detectar)
        b_novo = botao("Adicionar personagem…", "mais")
        b_novo.clicked.connect(self._add_personagem_manual)
        pl.addWidget(self.b_detectar)
        pl.addWidget(b_novo)
        self.tab_pers = QTableWidget(0, 2)
        self.tab_pers.setHorizontalHeaderLabels(["Personagem (falas)", "Voz"])
        self.tab_pers.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tab_pers.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tab_pers.verticalHeader().setVisible(False)
        self.tab_pers.setMaximumHeight(210)
        pl.addWidget(self.tab_pers)
        self.painel_personagens.setVisible(False)
        cv.lay.addWidget(self.painel_personagens)
        ml.addWidget(cv)

        cs = Cartao("Saída")
        fs = QFormLayout()
        self.formato = Combo()
        for cod, nome in (("m4b", "M4B — um arquivo com capítulos e capa"), ("mp3", "MP3 — um arquivo por capítulo"),
                          ("m4a", "M4A — um arquivo por capítulo"), ("flac", "FLAC — sem perdas"), ("wav", "WAV")):
            self.formato.addItem(nome, cod)
        self.perfil = Combo()
        for cod, p in PERFIS.items():
            self.perfil.addItem(p["nome"], cod)
        fs.addRow("Formato", self.formato)
        fs.addRow("Masterização", self.perfil)
        cs.lay.addLayout(fs)
        self.anunciar = QCheckBox("Falar o título de cada capítulo")
        self.anunciar.setChecked(True)
        self.por_cap = QCheckBox("Também gerar um MP3 por capítulo (com o M4B)")
        cs.lay.addWidget(self.anunciar)
        cs.lay.addWidget(self.por_cap)
        ml.addWidget(cs)

        cd = Cartao("Pronúncia")
        cd.lay.addWidget(rotulo("Nomes, siglas e termos estrangeiros costumam sair errados. Veja o que o livro tem de difícil e ensine a pronúncia.", "fraco"))
        lb = QHBoxLayout()
        b_dic = botao("Dicionário do livro", "dicionario")
        b_dic.clicked.connect(lambda: self.proj and self.irParaDicionario.emit(self.proj.id))
        lb.addWidget(b_dic)
        lb.addStretch(1)
        cd.lay.addLayout(lb)
        ml.addWidget(cd)
        ml.addStretch(1)
        corpo.addWidget(rolagem, 2)
        raiz.addLayout(corpo, 1)

        # ---- geração
        cg = Cartao()
        lg = QHBoxLayout()
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.progresso_rot = rotulo("Pronto para gerar.", "fraco")
        self.b_gerar = botao("Gerar audiobook", "gerar", "primario")
        self.b_gerar.clicked.connect(self._gerar)
        self.b_cancelar = botao("Cancelar", "cancelar", "perigo")
        self.b_cancelar.clicked.connect(self._cancelar_geracao)
        self.b_cancelar.setVisible(False)
        self.b_pasta = botao("Abrir pasta", "pasta")
        self.b_pasta.clicked.connect(self._abrir_pasta)
        self.b_pasta.setVisible(False)
        lg.addWidget(self.barra, 1)
        lg.addWidget(self.b_pasta)
        lg.addWidget(self.b_cancelar)
        lg.addWidget(self.b_gerar)
        cg.lay.addLayout(lg)
        cg.lay.addWidget(self.progresso_rot)
        self.avisos = QPlainTextEdit()
        self.avisos.setReadOnly(True)
        self.avisos.setMaximumHeight(70)
        self.avisos.setVisible(False)
        cg.lay.addWidget(self.avisos)
        raiz.addWidget(cg)
        return w

    # =============================================================================== abrir
    def _abrir_livro(self, caminho: str | None = None) -> None:
        if not caminho:
            caminho, _ = QFileDialog.getOpenFileName(self, "Abrir livro", str(Path.home() / "Downloads"),
                                                     "Livros (*.epub *.pdf *.docx *.mobi *.azw *.azw3 *.txt *.md *.markdown);;Todos (*)")
        if not caminho:
            return
        self.erro_inicio.setText("Lendo o livro…")

        def trabalho():
            doc = leitor.ler(Path(caminho))
            idioma = (doc.idioma[:2] or "en") if (doc.idioma[:2] in ("en", "pt", "es", "fr", "it")) else "en"
            caps = cap_mod.detectar(doc, 6000, idioma)
            return Projeto.criar(doc, caps, idioma)

        self._tarefa = Tarefa(trabalho, False, self)
        self._tarefa.terminou.connect(self._projeto_criado)
        self._tarefa.falhou.connect(lambda m: self.erro_inicio.setText(m.split("\n")[0]))
        self._tarefa.iniciar()

    def _projeto_criado(self, proj: Projeto) -> None:
        self.erro_inicio.setText("")
        self._carregar_projeto(proj)

    def _abrir_projeto(self, item) -> None:
        if item:
            self._carregar_projeto(Projeto.carregar(item.data(Qt.ItemDataRole.UserRole)))

    def _carregar_projeto(self, proj: Projeto) -> None:
        self.proj = proj
        self.titulo.setText(proj.titulo)
        total = sum(c.palavras for c in proj.capitulos if c.incluir)
        self.info.setText(f"{proj.autor or 'autor desconhecido'}  ·  {total:,} palavras  ·  ≈ {_hms(total / PALAVRAS_POR_MIN * 60)} de áudio".replace(",", "."))
        self.narrador.definir(proj.elenco.get("narrador") or self.ctx.cfg.voz_padrao)
        self.falas.definir(proj.elenco.get("fala", ""))
        self.separar.setChecked(proj.opcoes.separar_falas)
        self.contexto.setChecked(proj.opcoes.contexto_automatico)
        self.formato.setCurrentIndex(max(0, self.formato.findData(proj.opcoes.formato)))
        self.perfil.setCurrentIndex(max(0, self.perfil.findData(proj.opcoes.perfil_master)))
        self.anunciar.setChecked(proj.opcoes.anunciar_capitulos)
        self.por_cap.setChecked(proj.opcoes.por_capitulo)
        self._preencher_tabela()
        self._preencher_personagens()
        self.barra.setValue(0)
        self.progresso_rot.setText("Pronto para gerar.")
        self.avisos.clear()
        self.avisos.setVisible(False)
        self.b_pasta.setVisible(False)
        self.pilha.setCurrentIndex(1)

    def _voltar(self) -> None:
        if self._rodando:
            return
        self.recarregar_lista()
        self.pilha.setCurrentIndex(0)

    # =============================================================================== capítulos
    def _preencher_tabela(self) -> None:
        assert self.proj
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self.proj.capitulos))
        for i, c in enumerate(self.proj.capitulos):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk.setCheckState(Qt.CheckState.Checked if c.incluir else Qt.CheckState.Unchecked)
            titulo = QTableWidgetItem(c.titulo)
            titulo.setToolTip(c.nota or "Duplo clique para renomear")
            palavras = QTableWidgetItem(f"{c.palavras:,}".replace(",", "."))
            palavras.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            palavras.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            pronto = self.proj.prontos.get(c.id, {}).get("hash") == self.proj.hash_capitulo(c)
            est = QTableWidgetItem("pronto" if pronto else "")
            est.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            est.setForeground(Qt.GlobalColor.green if pronto else Qt.GlobalColor.gray)
            if pronto:
                m = self.proj.prontos[c.id]
                acx = m.get("acx") or []
                est.setToolTip(f"{_hms(m.get('duracao', 0))}  ·  {m.get('lufs', 0)} LUFS  ·  pico {m.get('pico', 0)} dB  ·  ruído {m.get('ruido', 0)} dB\n"
                               + ("Conforme ACX." if not acx else "Fora do ACX: " + "; ".join(acx)))
            for j, it in enumerate((chk, titulo, palavras, est)):
                self.tabela.setItem(i, j, it)
        self.tabela.blockSignals(False)

    def _editou_item(self, item: QTableWidgetItem) -> None:
        if not self.proj:
            return
        c = self.proj.capitulos[item.row()]
        if item.column() == 0:
            c.incluir = item.checkState() == Qt.CheckState.Checked
        elif item.column() == 1:
            c.titulo = item.text().strip() or c.titulo

    def _marcar_todos(self, valor: bool) -> None:
        if not self.proj:
            return
        for c in self.proj.capitulos:
            c.incluir = valor
        self._preencher_tabela()

    def _juntar(self) -> None:
        if not self.proj:
            return
        i = self.tabela.currentRow()
        if i <= 0:
            return
        ant, atual = self.proj.capitulos[i - 1], self.proj.capitulos[i]
        ant.texto = ant.texto + "\n\n" + atual.texto
        del self.proj.capitulos[i]
        self._preencher_tabela()

    def _roteiro(self) -> None:
        if not self.proj:
            return
        i = self.tabela.currentRow()
        if i < 0:
            self.estado_previa.setText("Selecione um capítulo.")
            return
        self._aplicar_ajustes()
        from .dialogo_roteiro import DialogoRoteiro

        d = DialogoRoteiro(self.ctx, self.proj, self.proj.capitulos[i], self._aplicar_ajustes, self)
        if d.exec():
            self._aplicar_ajustes()  # salva o texto do capítulo (o hash muda: só este capítulo é gerado de novo)
            self.ctx.avisar("Roteiro salvo no capítulo.", "ok")

    def _add_personagem_manual(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        nome, ok = QInputDialog.getText(self, "Novo personagem", "Nome (como aparece em @Nome: no roteiro):")
        nome = nome.strip()
        if ok and nome:
            self._add_personagem(nome, 0)

    def _previa(self) -> None:
        if not self.proj:
            return
        i = self.tabela.currentRow()
        if i < 0:
            self.estado_previa.setText("Selecione um capítulo.")
            return
        self._aplicar_ajustes()
        cap = self.proj.capitulos[i]
        voz = self.narrador.voz()
        ok, msg = self.ctx.ger.motor(voz.motor).estado()
        if not ok:
            self.estado_previa.setText(msg)
            return
        self.b_previa.setEnabled(False)
        self.estado_previa.setText("Gerando prévia…")
        proj = self.proj

        def trabalho(andar):
            return self.ctx.gerador.previa(proj, cap.id, voz)

        self._tarefa = Tarefa(trabalho, True, self)
        self._tarefa.terminou.connect(lambda x: (self.b_previa.setEnabled(True), self.estado_previa.setText(""), self.player.carregar_array(x, 24000, True)))
        self._tarefa.falhou.connect(lambda m: (self.b_previa.setEnabled(True), self.estado_previa.setText("Não deu certo: " + m.splitlines()[0])))
        self._tarefa.iniciar()

    # =============================================================================== elenco
    def _alternou_separar(self, v: bool) -> None:
        self.painel_personagens.setVisible(v)

    def _preencher_personagens(self) -> None:
        assert self.proj
        self.tab_pers.setRowCount(0)
        for papel, vid in self.proj.elenco.items():
            if papel not in ("narrador", "fala"):
                self._add_personagem(papel, 0, vid)

    def _add_personagem(self, nome: str, falas: int, vid: str = "") -> None:
        r = self.tab_pers.rowCount()
        self.tab_pers.insertRow(r)
        it = QTableWidgetItem(f"{nome}" + (f"  ({falas})" if falas else ""))
        it.setData(Qt.ItemDataRole.UserRole, nome)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.tab_pers.setItem(r, 0, it)
        sel = SeletorVoz(self.ctx, True, "(voz de falas)")
        sel.setMinimumWidth(120)
        if vid:
            sel.definir(vid)
        self.tab_pers.setCellWidget(r, 1, sel)

    def _detectar(self) -> None:
        if not self.proj:
            return
        paragrafos = [p for c in self.proj.capitulos if c.incluir for p in c.texto.split("\n\n")]
        self.b_detectar.setEnabled(False)
        self.b_detectar.setText("Detectando…")
        self._tarefa = Tarefa(lambda: _elenco.descobrir_falantes(paragrafos), False, self)

        def pronto(cont):
            self.b_detectar.setEnabled(True)
            self.b_detectar.setText("Detectar personagens")
            self.tab_pers.setRowCount(0)
            for nome, n in cont.most_common(12):
                if nome != _elenco.FALA and n >= 2:
                    self._add_personagem(nome, n, self.proj.elenco.get(nome, ""))

        self._tarefa.terminou.connect(pronto)
        self._tarefa.iniciar()

    # =============================================================================== gerar
    def _aplicar_ajustes(self) -> None:
        p = self.proj
        assert p
        p.elenco = {"narrador": self.narrador.id_atual()}
        if self.falas.id_atual():
            p.elenco["fala"] = self.falas.id_atual()
        for r in range(self.tab_pers.rowCount()):
            nome = self.tab_pers.item(r, 0).data(Qt.ItemDataRole.UserRole)
            vid = self.tab_pers.cellWidget(r, 1).id_atual()
            if vid:
                p.elenco[nome] = vid
        p.opcoes.formato = self.formato.currentData()
        p.opcoes.perfil_master = self.perfil.currentData()
        p.opcoes.anunciar_capitulos = self.anunciar.isChecked()
        p.opcoes.por_capitulo = self.por_cap.isChecked()
        p.opcoes.separar_falas = self.separar.isChecked()
        p.opcoes.contexto_automatico = self.contexto.isChecked()
        p.salvar()

    def _gerar(self) -> None:
        if not self.proj or self._rodando:
            return
        self._aplicar_ajustes()
        voz = self.narrador.voz()
        ok, msg = self.ctx.ger.motor(voz.motor).estado()
        if not ok:
            self.progresso_rot.setText(msg)
            return
        if not any(c.incluir for c in self.proj.capitulos):
            self.progresso_rot.setText("Marque pelo menos um capítulo.")
            return
        self._rodando = True
        self._cancelar.clear()
        self.b_gerar.setVisible(False)
        self.b_cancelar.setVisible(True)
        self.b_pasta.setVisible(False)
        self.avisos.clear()
        self.avisos.setVisible(False)
        proj = self.proj

        def trabalho(andar):
            return self.ctx.gerador.gerar(proj, None, andar, self._cancelar)

        self._tarefa = Tarefa(trabalho, True, self)
        self._tarefa.andamento.connect(self._evento)
        self._tarefa.terminou.connect(self._terminou)
        self._tarefa.falhou.connect(self._falhou)
        self._tarefa.iniciar()

    def _evento(self, e: dict) -> None:
        t = e["tipo"]
        if t == "inicio":
            self.progresso_rot.setText(f"{e['pendentes']} capítulo(s) a gerar · {e['trechos']} trechos")
        elif t == "capitulo":
            self.progresso_rot.setText(f"Capítulo {e['indice']}/{e['de']}: {e['titulo']}")
        elif t == "trecho":
            self.barra.setValue(int(e["feito"] * 1000 / max(1, e["total"])))
            eta = f"  ·  faltam ≈ {_hms(e['eta'])}" if e["eta"] > 5 else ""
            self.progresso_rot.setText(f"{e['feito']}/{e['total']} trechos{eta}  ·  {e['texto']}")
        elif t == "capitulo_pronto":
            self._preencher_tabela()
        elif t == "aviso":
            self.avisos.setVisible(True)
            self.avisos.appendPlainText(e["mensagem"])
        elif t == "motor":
            self.progresso_rot.setText(e["mensagem"])
        elif t == "exportando":
            self.progresso_rot.setText("Exportando arquivos…")

    def _terminou(self, res) -> None:
        self._rodando = False
        self.b_gerar.setVisible(True)
        self.b_cancelar.setVisible(False)
        self.barra.setValue(1000)
        self._resultado = res
        self.progresso_rot.setText(f"Pronto: {_hms(res.duracao)} de áudio em {_hms(res.segundos_trabalho)}  ·  {res.pasta}")
        self.b_pasta.setVisible(True)
        self._preencher_tabela()
        self.ctx.avisar("Audiobook gerado.", "ok")

    def _falhou(self, msg: str) -> None:
        self._rodando = False
        self.b_gerar.setVisible(True)
        self.b_cancelar.setVisible(False)
        if "Cancelado" in msg.split("\n")[0] or "Cancelado" in msg:
            self.progresso_rot.setText("Cancelado. O que já foi gerado fica guardado: gerar de novo continua de onde parou.")
        else:
            self.progresso_rot.setText("Não deu certo: " + msg.split("\n")[0])
            self.avisos.setVisible(True)
            self.avisos.setPlainText(msg)

    def _cancelar_geracao(self) -> None:
        self._cancelar.set()
        self.progresso_rot.setText("Cancelando…")

    def _abrir_pasta(self) -> None:
        res = getattr(self, "_resultado", None)
        if res:
            subprocess.Popen(["explorer", str(res.pasta)])
