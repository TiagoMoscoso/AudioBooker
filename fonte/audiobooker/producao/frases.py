"""Estúdio de frases: gera frases curtas com qualquer voz (inclusive clonada), guarda os takes e exporta."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import caminhos
from ..audio import exportar, masterizacao
from ..motores.gerenciador import Gerenciador
from ..texto import trechos as _trechos
from ..texto.direcoes import Direcao
from ..texto.pronuncias import Dicionario
from ..vozes.modelo import Voz
from .gerador import Gerador, preparar_fala

SR = 24000


@dataclass
class Take:
    id: str
    voz_id: str
    voz_nome: str
    texto: str
    arquivo: str
    duracao: float
    criado: float
    favorito: bool = False
    nota: str = ""


class EstudioFrases:
    def __init__(self, ger: Gerenciador, gerador: Gerador | None = None) -> None:
        self.ger = ger
        self.gerador = gerador or Gerador(ger)
        self._idx = caminhos.FRASES / "takes.json"

    # ---- geração
    def gerar(self, voz: Voz, texto: str, idioma: str | None = None, normalizar: bool = True,
              progresso=None, direcao: Direcao | None = None, avisos: list[str] | None = None) -> np.ndarray:
        """Frase (ou algumas) → áudio pronto, com dicionário, números, intonação e efeitos. Textos longos são divididos.
        `direcao`: intonação geral; a marcação no texto ([estilo triste]…) vence por trecho. `avisos` recebe o que o motor ignorou."""
        idioma = idioma or voz.idioma
        dic = Dicionario(idioma)
        partes = _trechos.dividir(texto, dic.abreviacoes(), alvo=240 if voz.motor == "chatterbox" else 300, limite=420,
                                  usar_contexto=False, base=direcao)
        def aviso(m: str) -> None:
            if avisos is not None and m not in avisos:
                avisos.append(m)

        saida: list[tuple[np.ndarray, float]] = []
        for t in partes:
            if t.pausa > 0:
                saida.append((np.zeros(0, dtype=np.float32), t.pausa))
                continue
            txt, ipa = preparar_fala(t.texto, dic, idioma, voz.motor == "kokoro")
            if not re.search(r"\w", txt):
                continue
            audio = self.gerador.sintetizar(voz, txt, ipa, idioma, aviso, progresso, t.direcao)
            saida.append((audio, 0.35 if saida else 0.0))
        from ..audio import montagem

        x = montagem.juntar(saida)
        if normalizar and len(x):
            x = masterizacao.masterizar(x, "off", lufs=-18.0 if len(x) > SR else None, pico=-1.5)
            pico = float(np.max(np.abs(x)))
            if pico > 0:
                x = x * min(1.0, 0.89 / pico) if pico > 0.89 else x
        if len(x):  # respiro: a frase não começa nem termina colada na borda do arquivo (players cortam a primeira sílaba)
            x = np.concatenate([np.zeros(int(SR * 0.12), dtype=np.float32), x, np.zeros(int(SR * 0.2), dtype=np.float32)])
        return x

    # ---- takes salvos
    def _ler(self) -> list[Take]:
        try:
            return [Take(**d) for d in json.loads(self._idx.read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            return []

    def _gravar(self, takes: list[Take]) -> None:
        self._idx.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._idx.with_suffix(".tmp")
        tmp.write_text(json.dumps([t.__dict__ for t in takes], indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._idx)

    def takes(self) -> list[Take]:
        return sorted(self._ler(), key=lambda t: t.criado, reverse=True)

    def guardar(self, voz: Voz, texto: str, audio: np.ndarray) -> Take:
        caminhos.garantir()
        agora = time.time()
        id_ = time.strftime("%Y%m%d-%H%M%S", time.localtime(agora)) + f"-{int(agora * 1000) % 1000:03d}"
        arq = caminhos.FRASES / caminhos.nome_seguro(voz.id) / f"{id_}-{caminhos.nome_seguro(texto, 40)}.wav"
        dur = exportar.gravar_wav(audio, arq)
        t = Take(id_, voz.id, voz.nome, texto, str(arq), dur, agora)
        self._gravar([t] + self._ler())
        return t

    def marcar(self, id_: str, favorito: bool) -> None:
        todos = self._ler()
        for t in todos:
            if t.id == id_:
                t.favorito = favorito
        self._gravar(todos)

    def apagar(self, id_: str) -> None:
        todos = self._ler()
        for t in todos:
            if t.id == id_:
                Path(t.arquivo).unlink(missing_ok=True)
        self._gravar([t for t in todos if t.id != id_])

    def exportar(self, take: Take, destino: Path, formato: str = "wav") -> Path:
        destino = Path(destino)
        if formato == "wav":
            import shutil

            alvo = destino.with_suffix(".wav")
            shutil.copyfile(take.arquivo, alvo)
            return alvo
        return exportar.exportar_faixa(Path(take.arquivo), destino, formato, take.texto[:60], take.voz_nome, "Frases", 1, 1)
