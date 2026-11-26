"""Laboratório de vozes: crie, misture, clone, aplique efeitos, teste e salve presets."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QScrollArea,
                               QSlider, QStackedWidget, QVBoxLayout, QWidget)

from ..vozes import referencia
from ..vozes.modelo import Voz
from . import tema
from .base import Combo, Cartao, Contexto, Player, Tarefa, botao, icone_botao, rotulo
from .editor_efeitos import EditorEfeitos

_FRASE_TESTE = {"en": "The quick brown fox jumps over the lazy dog. How does this voice sound to you?",
                "pt": "A rápida raposa marrom pula sobre o cão preguiçoso. Como esta voz soa para você?"}
_IDIOMAS = [("en", "Inglês"), ("pt", "Português (BR)")]


class _LinhaMistura(QWidget):
    def __init__(self, nomes: list[str], nome: str, peso: float, ao_mudar, ao_remover) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = Combo()
        self.combo.addItems(nomes)
        self.combo.setCurrentText(nome)
        self.combo.setMinimumWidth(150)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(int(round(peso * 100)))
        self.rotulo = QLabel(f"{self.slider.value()}%")
        self.rotulo.setMinimumWidth(40)
        self.slider.valueChanged.connect(lambda v: (self.rotulo.setText(f"{v}%"), ao_mudar()))
        self.combo.currentIndexChanged.connect(lambda _i: ao_mudar())
        b = icone_botao("apagar", "Remover voz da mistura", "icone")
        b.clicked.connect(lambda: ao_remover(self))
        lay.addWidget(self.combo)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.rotulo)
        lay.addWidget(b)


class _DialogoImportar(QDialog):
    def __init__(self, pai: QWidget, nome: str) -> None:
        super().__init__(pai)
        self.setWindowTitle("Importar voz externa")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(rotulo("Escolha um áudio com a voz (gravação, trecho de entrevista, narração). O programa corta o silêncio, "
                             "normaliza o volume e avisa se a amostra é curta, ruidosa ou estourada.", "subtitulo"))
        form = QFormLayout()
        self.arquivo = QLineEdit()
        self.arquivo.setPlaceholderText("Arquivo de áudio ou vídeo…")
        b = botao("Procurar…", "abrir")
        b.clicked.connect(self._procurar)
        linha = QHBoxLayout()
        linha.addWidget(self.arquivo, 1)
        linha.addWidget(b)
        form.addRow("Arquivo", linha)
        self.nome = QLineEdit(nome)
        form.addRow("Nome da voz", self.nome)
        self.ini = QDoubleSpinBox()
        self.ini.setSuffix(" s")
        self.ini.setMaximum(36000)
        self.fim = QDoubleSpinBox()
        self.fim.setSuffix(" s  (0 = até o fim)")
        self.fim.setMaximum(36000)
        form.addRow("Começar em", self.ini)
        form.addRow("Terminar em", self.fim)
        self.ruido = QCheckBox("Reduzir ruído de fundo")
        form.addRow("", self.ruido)
        lay.addLayout(form)
        lay.addWidget(rotulo("Dica: 6 a 20 segundos de fala limpa, de uma pessoa só, sem música, dão o melhor resultado.", "fraco"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Importar")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _procurar(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Áudio da voz", str(Path.home() / "Downloads"),
                                           "Áudio e vídeo (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.mp4 *.mkv *.webm);;Todos (*)")
        if f:
            self.arquivo.setText(f)
            if not self.nome.text().strip():
                self.nome.setText(Path(f).stem)


class TelaVozes(QWidget):
    def __init__(self, ctx: Contexto) -> None:
        super().__init__()
        self.ctx = ctx
        self._voz: Voz | None = None
        self._sujo = False
        self._carregando = False
        self._tarefa: Tarefa | None = None
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # ---- lista
        lateral = QWidget()
        lateral.setFixedWidth(300)
        ll = QVBoxLayout(lateral)
        ll.setContentsMargins(24, 24, 12, 24)
        ll.addWidget(rotulo("Vozes", "titulo"))
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar voz, tag, idioma…")
        self.busca.textChanged.connect(self._preencher)
        ll.addWidget(self.busca)
        self.lista = QListWidget()
        self.lista.currentItemChanged.connect(self._escolheu)
        ll.addWidget(self.lista, 1)
        bl = QHBoxLayout()
        self.b_nova = botao("Nova", "mais")
        self.b_dup = icone_botao("copiar", "Duplicar")
        self.b_imp = icone_botao("importar", "Importar preset (.zip)")
        self.b_exp = icone_botao("exportar", "Exportar preset (.zip)")
        self.b_del = icone_botao("apagar", "Apagar voz", "icone")
        self.b_nova.clicked.connect(self._nova)
        self.b_dup.clicked.connect(self._duplicar)
        self.b_imp.clicked.connect(self._importar_preset)
        self.b_exp.clicked.connect(self._exportar_preset)
        self.b_del.clicked.connect(self._apagar)
        for b in (self.b_nova, self.b_dup, self.b_imp, self.b_exp, self.b_del):
            bl.addWidget(b)
        ll.addLayout(bl)
        self.b_baixar = botao("Baixar vozes externas…", "importar", "", "Catálogo do Piper: dezenas de vozes em inglês e português")
        self.b_baixar.clicked.connect(self._baixar_vozes)
        ll.addWidget(self.b_baixar)
        raiz.addWidget(lateral)

        # ---- editor
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        conteudo = QWidget()
        rolagem.setWidget(conteudo)
        ed = QVBoxLayout(conteudo)
        ed.setContentsMargins(12, 24, 28, 24)
        ed.setSpacing(14)
        self.aviso_fabrica = rotulo("", "aviso")
        ed.addWidget(self.aviso_fabrica)

        c = Cartao("Identidade")
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.nome = QLineEdit()
        self.descricao = QLineEdit()
        self.idioma = Combo()
        for cod, nm in _IDIOMAS:
            self.idioma.addItem(nm, cod)
        self.motor = Combo()
        self.motor.addItem("Kokoro — vozes internas e mistura (rápido)", "kokoro")
        self.motor.addItem("Chatterbox — clonar voz de um áudio", "chatterbox")
        self.motor.addItem("Piper — voz externa baixada", "piper")
        f.addRow("Nome", self.nome)
        f.addRow("Descrição", self.descricao)
        f.addRow("Idioma", self.idioma)
        f.addRow("Motor", self.motor)
        c.lay.addLayout(f)
        ed.addWidget(c)

        self.pilha = QStackedWidget()
        self.pilha.addWidget(self._painel_kokoro())
        self.pilha.addWidget(self._painel_chatterbox())
        self.pilha.addWidget(self._painel_piper())
        ed.addWidget(self.pilha)

        ce = Cartao("Efeitos (robô, capacete, rascante, rádio…)")
        ce.lay.addWidget(rotulo("Rodam depois da voz, então mudar um efeito não exige gerar de novo. A ordem importa: de cima para baixo.", "fraco"))
        self.efeitos = EditorEfeitos()
        ce.lay.addWidget(self.efeitos)
        ed.addWidget(ce)

        ct = Cartao("Testar")
        self.frase = QPlainTextEdit()
        self.frase.setFixedHeight(70)
        ct.lay.addWidget(self.frase)
        lt = QHBoxLayout()
        self.b_testar = botao("Ouvir", "tocar", "primario")
        self.b_testar.clicked.connect(self._testar)
        self.estado = rotulo("", "fraco")
        lt.addWidget(self.b_testar)
        lt.addWidget(self.estado, 1)
        ct.lay.addLayout(lt)
        self.player = Player()
        ct.lay.addWidget(self.player)
        ed.addWidget(ct)

        rodape = QHBoxLayout()
        self.b_salvar = botao("Salvar voz", "salvar", "primario")
        self.b_salvar.clicked.connect(self._salvar)
        rodape.addStretch(1)
        rodape.addWidget(self.b_salvar)
        ed.addLayout(rodape)
        ed.addStretch(1)
        raiz.addWidget(rolagem, 1)

        self.motor.currentIndexChanged.connect(self._trocou_motor)
        for w in (self.nome, self.descricao):
            w.textChanged.connect(self._marcar)
        self.efeitos.mudou.connect(self._marcar)
        ctx.ao_mudar_vozes.append(self._preencher)
        self._preencher()

    # ---- painéis por motor
    def _painel_kokoro(self) -> QWidget:
        c = Cartao("Base — vozes internas do Kokoro")
        c.lay.addWidget(rotulo("Misture quantas vozes quiser: os pesos criam uma voz nova (ex.: 70% masculina grave + 30% britânica).", "fraco"))
        self.mistura = QVBoxLayout()
        self.mistura.setSpacing(6)
        c.lay.addLayout(self.mistura)
        self._linhas: list[_LinhaMistura] = []
        self.b_add_mistura = botao("Adicionar voz à mistura", "mais")
        self.b_add_mistura.clicked.connect(lambda: self._add_linha("af_heart", 0.5))
        lm = QHBoxLayout()
        lm.addWidget(self.b_add_mistura)
        lm.addStretch(1)
        c.lay.addLayout(lm)
        c.lay.addWidget(linha_fina())
        self.vel, self.vel_rot = self._deslizante(c, "Velocidade da fala", 50, 150, 100)
        return c

    def _painel_chatterbox(self) -> QWidget:
        c = Cartao("Base — voz clonada (Chatterbox)")
        c.lay.addWidget(rotulo("Importe um áudio da voz que quer reproduzir. Funciona com voz externa: gravação própria, entrevista, "
                               "narrador de referência…", "fraco"))
        lr = QHBoxLayout()
        self.ref_rot = QLabel("Nenhuma referência")
        self.b_ref = botao("Importar áudio…", "importar")
        self.b_ref.clicked.connect(self._importar_ref)
        self.b_ref_ouvir = icone_botao("tocar", "Ouvir a referência")
        self.b_ref_ouvir.clicked.connect(self._ouvir_ref)
        lr.addWidget(self.ref_rot, 1)
        lr.addWidget(self.b_ref_ouvir)
        lr.addWidget(self.b_ref)
        c.lay.addLayout(lr)
        self.ref_avisos = rotulo("", "aviso")
        c.lay.addWidget(self.ref_avisos)
        self.variante = Combo()
        self.variante.addItem("Automática (Turbo em inglês, Multilíngue nos demais)", "")
        self.variante.addItem("Turbo — inglês, rápido, aceita [laugh] [chuckle] [cough]", "turbo")
        self.variante.addItem("Original — inglês, controle de emoção", "original")
        self.variante.addItem("Multilíngue — 23 idiomas, inclui português", "multilingue")
        fv = QFormLayout()
        fv.addRow("Variante", self.variante)
        c.lay.addLayout(fv)
        self.exagero, self.exagero_rot = self._deslizante(c, "Emoção / exagero", 0, 200, 50, escala=100, so_original=True)
        self.cfg, self.cfg_rot = self._deslizante(c, "Fidelidade ao texto (CFG)", 0, 100, 50, escala=100, so_original=True)
        self.temp, self.temp_rot = self._deslizante(c, "Variação (temperatura)", 10, 150, 80, escala=100)
        self.vel_cb, self.vel_cb_rot = self._deslizante(c, "Velocidade da fala", 70, 130, 100)
        c.lay.addWidget(rotulo("Na variante Turbo, emoção e CFG são ignorados. Placas AMD usam a CPU (Chatterbox exige CUDA da NVIDIA para GPU).", "fraco"))
        return c

    def _painel_piper(self) -> QWidget:
        c = Cartao("Base — voz externa (Piper)")
        c.lay.addWidget(rotulo("Vozes baixadas do catálogo do Piper: timbres e sotaques diferentes das do Kokoro, rápidas na CPU. "
                               "Efeitos e velocidade valem como nas outras.", "fraco"))
        self.piper_voz = Combo()
        self.piper_voz.currentIndexChanged.connect(lambda _i: self._marcar())
        f = QFormLayout()
        f.addRow("Voz baixada", self.piper_voz)
        c.lay.addLayout(f)
        self.vel_pp, self.vel_pp_rot = self._deslizante(c, "Velocidade da fala", 60, 140, 100)
        return c

    def _recarregar_piper(self, escolhida: str = "") -> None:
        from ..vozes import catalogo_externo

        self.piper_voz.blockSignals(True)
        self.piper_voz.clear()
        for chave in catalogo_externo.instaladas():
            self.piper_voz.addItem(chave, chave)
        i = self.piper_voz.findData(escolhida)
        self.piper_voz.setCurrentIndex(i if i >= 0 else 0)
        self.piper_voz.blockSignals(False)

    def _baixar_vozes(self) -> None:
        from .dialogo_vozes_externas import DialogoVozesExternas

        DialogoVozesExternas(self, self.ctx).exec()
        self.ctx.vozes_mudaram()

    def _deslizante(self, cartao: Cartao, nome: str, mn: int, mx: int, padrao: int, escala: int = 100, so_original: bool = False):
        lay = QHBoxLayout()
        r = QLabel(nome)
        r.setObjectName("fraco")
        r.setMinimumWidth(190)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(mn, mx)
        s.setValue(padrao)
        val = QLabel()
        val.setMinimumWidth(52)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fmt = (lambda v: f"{v / escala:.2f}") if nome.startswith(("Emoção", "Fidel", "Varia")) else (lambda v: f"{v / 100:.2f}x")
        s.valueChanged.connect(lambda v: (val.setText(fmt(v)), self._marcar()))
        val.setText(fmt(padrao))
        lay.addWidget(r)
        lay.addWidget(s, 1)
        lay.addWidget(val)
        cartao.lay.addLayout(lay)
        return s, val

    # ---- mistura
    def _nomes_internos(self) -> list[str]:
        from ..vozes.biblioteca import nomes_kokoro_instalados

        return nomes_kokoro_instalados()

    def _add_linha(self, nome: str, peso: float) -> None:
        linha = _LinhaMistura(self._nomes_internos(), nome, peso, self._marcar, self._remover_linha)
        self._linhas.append(linha)
        self.mistura.addWidget(linha)
        self._marcar()

    def _remover_linha(self, linha: _LinhaMistura) -> None:
        if len(self._linhas) <= 1:
            return
        self._linhas.remove(linha)
        linha.setParent(None)
        linha.deleteLater()
        self._marcar()

    # ---- lista
    def _preencher(self) -> None:
        sel = self._voz.id if self._voz else None
        filtro = self.busca.text().lower().strip()
        self.lista.blockSignals(True)
        self.lista.clear()

        def adicionar(cabecalho: str, vozes: list[Voz]) -> None:
            vozes = [v for v in vozes if not filtro or filtro in (v.nome + v.id + " ".join(v.tags) + v.idioma + v.motor).lower()]
            if not vozes:
                return
            h = QListWidgetItem(cabecalho.upper())
            h.setFlags(Qt.ItemFlag.NoItemFlags)
            h.setForeground(Qt.GlobalColor.gray)
            self.lista.addItem(h)
            for v in vozes:
                it = QListWidgetItem(("☁ " if v.motor == "chatterbox" else "") + v.nome)
                it.setData(Qt.ItemDataRole.UserRole, v.id)
                it.setToolTip(v.descricao)
                self.lista.addItem(it)

        b = self.ctx.bib
        adicionar("Minhas vozes", b.minhas())
        fab = b.fabrica()
        adicionar("Personagens", [v for v in fab if "personagem" in v.tags])
        adicionar("Chatterbox", [v for v in fab if v.motor == "chatterbox"])
        adicionar("Vozes externas (Piper)", [v for v in fab if v.motor == "piper"])
        adicionar("Vozes do Kokoro", [v for v in fab if v.motor == "kokoro" and "personagem" not in v.tags])
        self.lista.blockSignals(False)
        alvo = sel or (self.ctx.cfg.voz_padrao)
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == alvo:
                self.lista.setCurrentRow(i)
                return
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.ItemDataRole.UserRole):
                self.lista.setCurrentRow(i)
                return

    def _escolheu(self, atual, _antes) -> None:
        if not atual:
            return
        id_ = atual.data(Qt.ItemDataRole.UserRole)
        if not id_:
            return
        v = self.ctx.bib.obter(id_)
        if v:
            self._mostrar(v)

    # ---- mostrar / ler
    def _mostrar(self, v: Voz) -> None:
        self._carregando = True
        self._voz = v
        self.nome.setText(v.nome)
        self.descricao.setText(v.descricao)
        self.idioma.setCurrentIndex(max(0, self.idioma.findData(v.idioma)))
        indice = {"kokoro": 0, "chatterbox": 1, "piper": 2}.get(v.motor, 0)
        self.motor.setCurrentIndex(indice)
        self.pilha.setCurrentIndex(indice)
        self._recarregar_piper(next(iter(v.base), "") if v.motor == "piper" else "")
        self.vel_pp.setValue(int(round(v.velocidade * 100)))
        for ln in list(self._linhas):
            ln.setParent(None)
            ln.deleteLater()
        self._linhas.clear()
        base = v.base or {"af_heart": 1.0}
        for nome, peso in base.items():
            self._add_linha(nome, float(peso))
        self.vel.setValue(int(round(v.velocidade * 100)))
        self.vel_cb.setValue(int(round(v.velocidade * 100)))
        p = v.parametros or {}
        self.exagero.setValue(int(round(float(p.get("exagero", 0.5)) * 100)))
        self.cfg.setValue(int(round(float(p.get("cfg", 0.5)) * 100)))
        self.temp.setValue(int(round(float(p.get("temperatura", 0.8)) * 100)))
        self.variante.setCurrentIndex(max(0, self.variante.findData(p.get("variante", ""))))
        self._ref = v.referencia
        self._mostrar_ref()
        self.efeitos.definir(v.efeitos)
        self.frase.setPlainText(_FRASE_TESTE.get(v.idioma, _FRASE_TESTE["en"]))
        self.aviso_fabrica.setText("Voz de fábrica: ao salvar, vira uma cópia sua (a original não muda)." if v.sistema else "")
        self.aviso_fabrica.setVisible(v.sistema)
        self.b_del.setEnabled(not v.sistema)
        self._carregando = False
        self._sujo = False

    def _mostrar_ref(self) -> None:
        ref = Path(self._ref) if self._ref else None
        from .. import caminhos

        existe = bool(ref and (ref if ref.is_absolute() else caminhos.REFERENCIAS / ref).exists())
        self.ref_rot.setText(self._ref if existe else "Nenhuma referência — usa a voz padrão do Chatterbox")
        self.b_ref_ouvir.setEnabled(existe)

    def _ler(self) -> Voz:
        base_v = self._voz
        motor = self.motor.currentData()
        base = {}
        if motor == "kokoro":
            for ln in self._linhas:
                n = ln.combo.currentText()
                base[n] = base.get(n, 0.0) + ln.slider.value() / 100.0
            if sum(base.values()) <= 0:
                base = {k: 1.0 for k in base}
        if motor == "piper" and self.piper_voz.currentData():
            base = {self.piper_voz.currentData(): 1.0}
        params = {}
        if motor == "chatterbox":
            params = {"exagero": self.exagero.value() / 100, "cfg": self.cfg.value() / 100, "temperatura": self.temp.value() / 100,
                      "variante": self.variante.currentData()}
        return Voz(id=base_v.id if base_v else "", nome=self.nome.text().strip() or "Voz sem nome", motor=motor,
                   idioma=self.idioma.currentData(), descricao=self.descricao.text().strip(), base=base,
                   referencia=getattr(self, "_ref", "") if motor == "chatterbox" else "",
                   velocidade=({"kokoro": self.vel, "chatterbox": self.vel_cb, "piper": self.vel_pp}[motor].value()) / 100.0,
                   parametros=params, efeitos=self.efeitos.efeitos(), tags=(base_v.tags if base_v else []),
                   sistema=False)

    def _marcar(self, *_a) -> None:
        if not self._carregando:
            self._sujo = True

    def _trocou_motor(self) -> None:
        self.pilha.setCurrentIndex({"kokoro": 0, "chatterbox": 1, "piper": 2}.get(self.motor.currentData(), 0))
        if self.motor.currentData() == "piper" and self.piper_voz.count() == 0:
            self._recarregar_piper()
        self._marcar()

    # ---- ações
    def _salvar(self) -> None:
        v = self._ler()
        if self._voz and not self._voz.sistema and self._voz.id:
            v.id = self._voz.id            # editando uma voz minha: sobrescreve
        else:
            v.id = self.ctx.bib.id_livre(v.nome)  # voz de fábrica ou nova: vira cópia
        salva = self.ctx.bib.salvar(v)
        self._voz = salva
        self.ctx.vozes_mudaram()
        self._sujo = False
        self.ctx.avisar(f"Voz “{salva.nome}” salva.", "ok")

    def _nova(self) -> None:
        v = Voz(id="", nome="Nova voz", motor="kokoro", idioma="en", base={"af_heart": 1.0})
        v.sistema = False
        self._voz = None
        self._mostrar(v)
        self._voz = None
        self.aviso_fabrica.setVisible(False)
        self.nome.selectAll()
        self.nome.setFocus()

    def _duplicar(self) -> None:
        if self._voz:
            v = self._ler()
            v.nome = v.nome + " (cópia)"
            salva = self.ctx.bib.salvar(Voz.de_dict({**v.para_dict(), "id": self.ctx.bib.id_livre(v.nome)}))
            self._voz = salva
            self.ctx.vozes_mudaram()

    def _apagar(self) -> None:
        if self._voz and not self._voz.sistema:
            self.ctx.bib.apagar(self._voz.id)
            self._voz = None
            self.ctx.vozes_mudaram()

    def _importar_preset(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Importar voz", str(Path.home() / "Downloads"), "Preset de voz (*.zip)")
        if f:
            try:
                v = self.ctx.bib.importar(Path(f))
                self._voz = v
                self.ctx.vozes_mudaram()
                self.ctx.avisar(f"Voz “{v.nome}” importada.", "ok")
            except Exception as e:  # noqa: BLE001
                self.ctx.avisar(f"Não consegui importar: {e}", "erro")

    def _exportar_preset(self) -> None:
        if not self._voz:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Exportar voz", str(Path.home() / "Downloads" / f"{self._voz.id}.zip"), "Preset de voz (*.zip)")
        if f:
            self.ctx.bib.exportar(self._voz.id, Path(f))
            self.ctx.avisar("Voz exportada (preset + áudio de referência).", "ok")

    def _importar_ref(self) -> None:
        d = _DialogoImportar(self, self.nome.text())
        if d.exec() != QDialog.DialogCode.Accepted or not d.arquivo.text().strip():
            return
        nome = d.nome.text().strip() or "voz"
        try:
            rel = referencia.importar(Path(d.arquivo.text()), nome, d.ini.value(), d.fim.value() or None, d.ruido.isChecked())
        except Exception as e:  # noqa: BLE001
            self.ctx.avisar(f"Não consegui ler o áudio: {e}", "erro")
            return
        self._ref = rel.arquivo.name
        self._mostrar_ref()
        self.ref_avisos.setText("  ·  ".join(rel.avisos) if rel.avisos else f"Referência boa ({rel.duracao:.1f} s).")
        self.ref_avisos.setObjectName("aviso" if rel.avisos else "ok")
        self.ref_avisos.setStyleSheet(f"color: {tema.AVISO if rel.avisos else tema.OK};")
        if not self.nome.text().strip() or self.nome.text() == "Nova voz":
            self.nome.setText(nome)
        self._marcar()

    def _ouvir_ref(self) -> None:
        v = self._ler()
        ref = v.caminho_referencia()
        if ref and ref.exists():
            self.player.carregar_arquivo(ref, True)

    def _testar(self) -> None:
        v = self._ler()
        texto = self.frase.toPlainText().strip()
        if not texto:
            return
        ok, msg = self.ctx.ger.motor(v.motor).estado()
        if not ok:
            self.estado.setText(msg)
            return
        self.b_testar.setEnabled(False)
        self.estado.setText("Gerando…")

        def trabalho(andar):
            return self.ctx.estudio.gerar(v, texto, progresso=andar)

        self._tarefa = Tarefa(trabalho, True, self)
        self._tarefa.andamento.connect(lambda m: self.estado.setText(str(m)))

        def pronto(x):
            self.b_testar.setEnabled(True)
            m = self.ctx.ger.motor(v.motor)
            self.estado.setText(f"{len(x) / 24000:.1f} s · {m.dispositivo.upper()}" + (f"  ·  {m.nota_dispositivo}" if m.nota_dispositivo else ""))
            self.player.carregar_array(x, 24000, True)

        def falha(msg):
            self.b_testar.setEnabled(True)
            self.estado.setText("Não deu certo: " + msg.splitlines()[0])

        self._tarefa.terminou.connect(pronto)
        self._tarefa.falhou.connect(falha)
        self._tarefa.iniciar()


def linha_fina() -> QWidget:
    from .base import linha

    return linha()
