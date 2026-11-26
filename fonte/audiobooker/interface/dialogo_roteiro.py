"""Revisão manual do roteiro de um capítulo: quem fala cada parágrafo, com que estilo e com que marcação de intonação.

O roteiro é o próprio texto do capítulo no formato `@Papel: texto`, com marcação [estilo triste]…[/estilo], [ênfase]…[/ênfase],
[pausa 1s] etc. A sugestão automática (aspas, "she whispered") serve só de ponto de partida: o que você editar aqui vale.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout

from ..texto import elenco as _elenco
from .base import Contexto, Player, Tarefa, botao, rotulo
from .painel_intonacao import PainelIntonacao


class DialogoRoteiro(QDialog):
    def __init__(self, ctx: Contexto, proj, capitulo, salvar_ajustes, parent=None) -> None:
        super().__init__(parent)
        self.ctx, self.proj, self.cap, self._salvar_ajustes = ctx, proj, capitulo, salvar_ajustes
        self._tarefa: Tarefa | None = None
        self.setWindowTitle(f"Roteiro — {capitulo.titulo}")
        self.resize(900, 700)
        lay = QVBoxLayout(self)
        lay.addWidget(rotulo("Roteiro do capítulo", "titulo"))
        lay.addWidget(rotulo("Cada parágrafo começa com @Papel: (narrador, fala ou o nome do personagem). Edite o texto, troque o papel, "
                             "marque estilos e palavras. Papéis sem voz no elenco usam a voz de falas (ou o narrador).", "subtitulo"))
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(_elenco.gerar_roteiro(capitulo.texto, proj.opcoes.contexto_automatico))
        lay.addWidget(self.editor, 1)
        self.painel = PainelIntonacao(self.editor, so_marcacao=True)
        lay.addWidget(self.painel)
        self.estado = rotulo("", "fraco")
        self.estado.setWordWrap(True)
        lay.addWidget(self.estado)
        self.player = Player()
        lay.addWidget(self.player)
        barra = QHBoxLayout()
        self.b_auto = botao("Refazer sugestão automática", "atualizar", "", "Descarta as edições e gera o roteiro de novo a partir do texto original")
        self.b_ouvir = botao("Ouvir parágrafo", "tocar", "", "Fala o parágrafo onde está o cursor, com o elenco do projeto")
        self.b_salvar = botao("Salvar no capítulo", "salvar", "primario")
        self.b_cancelar = botao("Fechar")
        self.b_auto.clicked.connect(self._refazer)
        self.b_ouvir.clicked.connect(self._ouvir)
        self.b_salvar.clicked.connect(self._salvar)
        self.b_cancelar.clicked.connect(self.reject)
        for b in (self.b_auto, self.b_ouvir):
            barra.addWidget(b)
        barra.addStretch(1)
        barra.addWidget(self.b_cancelar)
        barra.addWidget(self.b_salvar)
        lay.addLayout(barra)
        voz = self.ctx.gerador.vozes(proj)["narrador"]
        self.painel.definir_motor(self.ctx.ger.motor(voz.motor), voz)

    def _refazer(self) -> None:
        self.editor.setPlainText(_elenco.gerar_roteiro(self.cap.texto, self.proj.opcoes.contexto_automatico))

    def _paragrafo_atual(self) -> str:
        c = self.editor.textCursor()
        texto = self.editor.toPlainText()
        pos = c.position()
        ini = texto.rfind("\n\n", 0, pos)
        fim = texto.find("\n\n", pos)
        return texto[(ini + 2 if ini >= 0 else 0):(fim if fim >= 0 else len(texto))].strip()

    def _ouvir(self) -> None:
        par = self._paragrafo_atual()
        if not par:
            return
        self._salvar_ajustes()
        self.b_ouvir.setEnabled(False)
        self.estado.setText("Gerando…")
        self._tarefa = Tarefa(lambda andar: self.ctx.gerador.ouvir_texto(self.proj, par), True, self)

        def pronto(r) -> None:
            audio, avisos = r
            self.b_ouvir.setEnabled(True)
            self.estado.setText(("Ignorado pelo motor: " + "; ".join(avisos)) if avisos else "")
            self.player.carregar_array(audio, 24000, True)

        self._tarefa.terminou.connect(pronto)
        self._tarefa.falhou.connect(lambda m: (self.b_ouvir.setEnabled(True), self.estado.setText("Não deu certo: " + m.splitlines()[0])))
        self._tarefa.iniciar()

    def _salvar(self) -> None:
        self.cap.texto = self.editor.toPlainText().strip()
        self.accept()
