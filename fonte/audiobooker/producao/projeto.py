"""Projeto de audiobook: capítulos revisados, elenco, opções e estado. Fica em %LOCALAPPDATA%\\AUDIOBOOKER\\projetos."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import caminhos
from ..documentos.capitulos import Capitulo
from ..documentos.modelo import Documento


@dataclass
class Opcoes:
    formato: str = "m4b"             # m4b | mp3 | flac | wav | m4a
    perfil_master: str = "audiobook"
    anunciar_capitulos: bool = True
    separar_falas: bool = False       # usa vozes diferentes para falas e personagens
    contexto_automatico: bool = True  # sugere o estilo das falas pelo entorno ("she whispered")
    alvo_trecho: int = 0             # 0 = automático por motor
    pausa_frase: float = 0.28
    pausa_paragrafo: float = 0.85
    pausa_cena: float = 1.8
    pausa_capitulo: float = 1.2       # depois do título anunciado
    unico_arquivo: bool = True        # também gera o arquivo único (m4b)
    por_capitulo: bool = False        # também gera um arquivo por capítulo


@dataclass
class Projeto:
    id: str
    titulo: str
    autor: str = ""
    idioma: str = "en"
    origem: str = ""
    capitulos: list[Capitulo] = field(default_factory=list)
    elenco: dict = field(default_factory=lambda: {"narrador": ""})
    opcoes: Opcoes = field(default_factory=Opcoes)
    prontos: dict = field(default_factory=dict)   # id_capitulo -> {"hash": ..., "duracao": ..., "lufs": ...}
    criado: float = field(default_factory=time.time)
    tem_capa: bool = False

    # ---- caminhos
    @property
    def pasta(self) -> Path:
        return caminhos.PROJETOS / self.id

    @property
    def pasta_saida(self) -> Path:
        return self.pasta / "capitulos"

    # ---- persistência
    def salvar(self) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        (self.pasta / "texto").mkdir(exist_ok=True)
        for c in self.capitulos:
            (self.pasta / "texto" / f"{c.id}.txt").write_text(c.texto, encoding="utf-8")
        dados = {
            "id": self.id, "titulo": self.titulo, "autor": self.autor, "idioma": self.idioma, "origem": self.origem,
            "capitulos": [{"id": c.id, "titulo": c.titulo, "incluir": c.incluir, "nota": c.nota} for c in self.capitulos],
            "elenco": self.elenco, "opcoes": self.opcoes.__dict__, "prontos": self.prontos, "criado": self.criado,
            "tem_capa": self.tem_capa,
        }
        tmp = self.pasta / "projeto.json.tmp"
        tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.pasta / "projeto.json")

    @staticmethod
    def carregar(id_: str) -> "Projeto":
        pasta = caminhos.PROJETOS / id_
        d = json.loads((pasta / "projeto.json").read_text(encoding="utf-8"))
        caps = []
        for c in d["capitulos"]:
            texto = (pasta / "texto" / f"{c['id']}.txt").read_text(encoding="utf-8")
            caps.append(Capitulo(c["id"], c["titulo"], texto, c.get("incluir", True), c.get("nota", "")))
        op = Opcoes()
        for k, v in d.get("opcoes", {}).items():
            if hasattr(op, k):
                setattr(op, k, v)
        return Projeto(d["id"], d["titulo"], d.get("autor", ""), d.get("idioma", "en"), d.get("origem", ""), caps,
                       d.get("elenco", {"narrador": ""}), op, d.get("prontos", {}), d.get("criado", time.time()), d.get("tem_capa", False))

    @staticmethod
    def criar(doc: Documento, capitulos: list[Capitulo], idioma: str) -> "Projeto":
        caminhos.garantir()
        base = caminhos.nome_seguro(doc.titulo, 50)
        id_, n = base, 2
        while (caminhos.PROJETOS / id_).exists():
            id_ = f"{base}-{n}"
            n += 1
        p = Projeto(id_, doc.titulo, doc.autor, idioma, str(doc.origem or ""), capitulos, tem_capa=bool(doc.capa))
        p.salvar()
        if doc.capa:
            (p.pasta / "capa.bin").write_bytes(doc.capa)
        return p

    def capa(self) -> bytes | None:
        arq = self.pasta / "capa.bin"
        return arq.read_bytes() if arq.exists() else None

    def apagar(self) -> None:
        shutil.rmtree(self.pasta, ignore_errors=True)

    # ---- estado
    def hash_capitulo(self, c: Capitulo) -> str:
        corpo = json.dumps([c.texto, c.titulo, self.elenco, self.opcoes.__dict__, self.idioma], sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(corpo.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def listar() -> list["Projeto"]:
        saida = []
        for pasta in sorted(caminhos.PROJETOS.glob("*/projeto.json")):
            try:
                saida.append(Projeto.carregar(pasta.parent.name))
            except (OSError, ValueError, KeyError):
                continue
        return saida
