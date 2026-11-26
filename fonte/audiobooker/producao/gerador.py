"""Gera o audiobook: texto -> trechos -> voz (com cache) -> efeitos -> pausas -> masterização -> arquivos."""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .. import caminhos
from ..audio import exportar, masterizacao, montagem
from ..configuracao import Configuracao
from ..motores.base import MotorIndisponivel
from ..motores.gerenciador import Gerenciador
from ..texto import elenco as _elenco
from ..texto import numeros, trechos as _trechos
from ..texto.direcoes import Direcao
from ..texto.limpeza import QUEBRA_CENA
from . import entrega as _entrega
from ..texto.pronuncias import Dicionario
from ..vozes.biblioteca import BibliotecaVozes
from ..vozes.modelo import Voz
from . import cache
from .projeto import Projeto

Evento = dict
Progresso = Callable[[Evento], None]
SR = 24000


class Cancelado(Exception):
    pass


@dataclass
class Resultado:
    pasta: Path
    arquivos: list[Path] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    duracao: float = 0.0
    segundos_trabalho: float = 0.0


def preparar_fala(texto: str, dic: Dicionario, idioma: str, usa_ipa: bool) -> tuple[str, dict[str, str]]:
    """Dicionário + números por extenso. Devolve o texto final e o mapa IPA só das palavras presentes."""
    texto = texto.replace(QUEBRA_CENA, " ")
    texto = dic.aplicar(texto, usa_ipa)
    texto = numeros.por_extenso(texto, idioma)
    texto = re.sub(r"\s+", " ", texto).strip()
    ipa = {}
    if usa_ipa:
        minusculo = texto.lower()
        ipa = {p: f for p, f in dic.mapa_ipa().items() if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", minusculo)}
    return texto, ipa


def fala_suspeita(texto: str, audio: np.ndarray) -> bool:
    if len(audio) < SR * 0.12:
        return len(texto.strip(" .!?…,;:\"'“”‘’()-—")) > 0
    return len(texto) > 25 and (len(audio) / SR) < len(texto) / 45.0


class Gerador:
    def __init__(self, ger: Gerenciador, bib: BibliotecaVozes | None = None, cfg: Configuracao | None = None) -> None:
        self.ger = ger
        self.bib = bib or BibliotecaVozes()
        self.cfg = cfg or ger.cfg

    # ---- vozes do projeto -------------------------------------------------------------------------------
    def vozes(self, proj: Projeto) -> dict[str, Voz]:
        out: dict[str, Voz] = {}
        padrao = proj.elenco.get("narrador") or self.cfg.voz_padrao
        # voz salva de um motor que não está mais instalado (ex.: Kokoro apagado): cai para a voz padrão do Chatterbox
        out["narrador"] = self.bib.obter(padrao) or self.bib.obter_ou_erro("chatterbox-padrao")
        for papel, vid in proj.elenco.items():
            if papel != "narrador" and vid:
                v = self.bib.obter(vid)
                if v:
                    out[papel] = v
        return out

    def _alvo(self, voz: Voz, proj: Projeto) -> tuple[int, int]:
        if proj.opcoes.alvo_trecho:
            return proj.opcoes.alvo_trecho, int(proj.opcoes.alvo_trecho * 1.5)
        return (240, 340) if voz.motor == "chatterbox" else (300, 420)

    # ---- um trecho --------------------------------------------------------------------------------------
    def sintetizar(self, voz: Voz, texto: str, ipa: dict[str, str], idioma: str, aviso: Callable[[str], None] | None = None,
                   progresso_motor: Callable[[str], None] | None = None, direcao: Direcao | None = None) -> np.ndarray:
        """`direcao`: intonação do trecho. O que o motor da voz executa vai como parâmetro (entra no cache);
        velocidade/tom/volume são aplicados ao áudio já em cache; o resto é IGNORADO e avisado (nunca imitado)."""
        res = _entrega.resolver(direcao or Direcao(), texto, self.ger.motor(voz.motor).capacidades(voz), f"o motor {voz.motor}")
        if aviso:
            for a in res.avisos:
                aviso(a)
        texto = res.texto
        extra = (repr(sorted(ipa.items())) if voz.motor == "kokoro" else "") + (res.chave() if res.entrega else "")
        c = cache.chave(texto, voz.assinatura_seca(), idioma, extra)
        seco = cache.ler(c)
        if seco is None:
            seco = None
            ultimo = None
            for tentativa in range(3):
                try:
                    v = voz
                    if tentativa and voz.motor == "chatterbox":
                        v = voz.copia(parametros={**voz.parametros, "temperatura": min(1.2, float(voz.parametros.get("temperatura", 0.8)) + 0.12 * tentativa)})
                    t = texto if tentativa < 1 else re.sub(r"[\"“”‘’()\[\]]", "", texto)
                    seco = self.ger.seco(v, t, ipa or None, progresso_motor, res.entrega or None)
                    seco = montagem.cortar_bordas(seco)
                    if not fala_suspeita(texto, seco):
                        break
                    ultimo = "áudio curto demais para o texto"
                except MotorIndisponivel:
                    raise
                except Exception as e:  # noqa: BLE001
                    ultimo = str(e)[:120]
                    seco = None
            if seco is None or len(seco) == 0:
                if aviso:
                    aviso(f"Trecho sem áudio ({ultimo}): “{texto[:50]}…”")
                return np.zeros(0, dtype=np.float32)
            if ultimo and aviso and fala_suspeita(texto, seco):
                aviso(f"Trecho possivelmente cortado: “{texto[:50]}…”")
            cache.gravar(c, seco)
        return self.ger.com_efeitos(voz, _entrega.aplicar_pos(seco, res.pos))

    # ---- capítulo ---------------------------------------------------------------------------------------
    def _trechos_do_capitulo(self, proj: Projeto, cap, vozes: dict[str, Voz], dic: Dicionario):
        op = proj.opcoes
        separar = op.separar_falas and len(vozes) > 1
        alvo, limite = self._alvo(vozes["narrador"], proj)
        lista = _trechos.dividir(cap.texto, dic.abreviacoes(), alvo, limite, separar_falas=separar,
                                 usar_contexto=op.contexto_automatico)
        if op.anunciar_capitulos and cap.titulo.strip():
            titulo = cap.titulo.strip()
            lista.insert(0, _trechos.Trecho(titulo if re.search(r"[.!?:]$", titulo) else titulo + ".", "capitulo", "narrador"))
            if len(lista) > 1:
                lista[1] = _trechos.Trecho(lista[1].texto, "titulo", lista[1].papel, lista[1].pausa, lista[1].direcao)
        return lista

    def _pausa(self, antes: str, op) -> float:
        c = self.cfg
        return {"frase": c.pausa_frase, "paragrafo": c.pausa_paragrafo, "cena": c.pausa_cena,
                "titulo": c.pausa_capitulo_inicio, "capitulo": 0.0}.get(antes, c.pausa_frase)

    def gerar(self, proj: Projeto, ids: list[str] | None = None, progresso: Progresso | None = None,
              cancelar: threading.Event | None = None, exportar_saida: bool = True) -> Resultado:
        cancelar = cancelar or threading.Event()
        emitir = progresso or (lambda e: None)
        t0 = time.time()
        res = Resultado(pasta=self.cfg.pasta_biblioteca / caminhos.nome_seguro(proj.titulo, 60))
        vozes = self.vozes(proj)
        dic = Dicionario(proj.idioma, proj.id)
        selecionados = [c for c in proj.capitulos if c.incluir and (ids is None or c.id in ids)]
        if not selecionados:
            raise ValueError("Nenhum capítulo selecionado.")

        planos = {c.id: self._trechos_do_capitulo(proj, c, vozes, dic) for c in selecionados}
        pendentes = [c for c in selecionados if proj.prontos.get(c.id, {}).get("hash") != proj.hash_capitulo(c)
                     or not (proj.pasta_saida / f"{c.id}.wav").exists()]
        total = sum(len(planos[c.id]) for c in pendentes) or 1
        feito = 0
        chars_feitos, seg_feitos = 0, 0.0

        def aviso(msg: str) -> None:
            if msg in res.avisos:
                return  # a mesma direção ignorada aparece uma vez só
            res.avisos.append(msg)
            emitir({"tipo": "aviso", "mensagem": msg})

        emitir({"tipo": "inicio", "capitulos": len(selecionados), "pendentes": len(pendentes), "trechos": total,
                "dispositivo": self.ger.descrever()})
        for ci, cap in enumerate(pendentes, 1):
            if cancelar.is_set():
                raise Cancelado()
            partes: list[tuple[np.ndarray, float]] = []
            lista = planos[cap.id]
            emitir({"tipo": "capitulo", "id": cap.id, "titulo": cap.titulo, "indice": ci, "de": len(pendentes)})
            for ti, t in enumerate(lista):
                if cancelar.is_set():
                    raise Cancelado()
                inicio = time.time()
                if t.pausa > 0:
                    partes.append((np.zeros(0, dtype=np.float32), t.pausa))
                else:
                    voz = vozes.get(t.papel) or vozes.get(_elenco.FALA) or vozes["narrador"]
                    if t.papel not in vozes and t.papel not in (_elenco.NARRADOR, _elenco.FALA):
                        voz = vozes.get(_elenco.FALA) or vozes["narrador"]
                    txt, ipa = preparar_fala(t.texto, dic, proj.idioma, voz.motor == "kokoro")
                    if re.search(r"\w", txt):
                        audio = self.sintetizar(voz, txt, ipa, proj.idioma, aviso,
                                                lambda m: emitir({"tipo": "motor", "mensagem": m}), t.direcao)
                        partes.append((audio, self._pausa(t.antes, proj.opcoes) if partes else 0.0))
                        chars_feitos += len(txt)
                        seg_feitos += time.time() - inicio
                feito += 1
                restante = (total - feito) * (seg_feitos / max(1, feito)) if feito > 1 else 0.0
                emitir({"tipo": "trecho", "capitulo": cap.id, "feito": feito, "total": total, "eta": restante,
                        "texto": t.texto[:80], "cap_feito": ti + 1, "cap_total": len(lista)})
            cru = montagem.juntar(partes)
            final = masterizacao.masterizar(cru, proj.opcoes.perfil_master, self.cfg.alvo_loudness if proj.opcoes.perfil_master == "audiobook" else None)
            dur = exportar.gravar_wav(final, proj.pasta_saida / f"{cap.id}.wav")
            rel = masterizacao.medir(final)
            proj.prontos[cap.id] = {"hash": proj.hash_capitulo(cap), "duracao": dur, "lufs": round(rel.lufs, 1),
                                    "rms": round(rel.rms_db, 1), "pico": round(rel.pico_db, 1), "ruido": round(rel.piso_ruido_db, 1),
                                    "acx": rel.avisos_acx()}
            proj.salvar()
            emitir({"tipo": "capitulo_pronto", "id": cap.id, "duracao": dur, "lufs": rel.lufs})

        if exportar_saida:
            res.arquivos = self._exportar(proj, selecionados, res, emitir)
        res.duracao = sum(proj.prontos.get(c.id, {}).get("duracao", 0.0) for c in selecionados)
        res.segundos_trabalho = time.time() - t0
        emitir({"tipo": "fim", "duracao": res.duracao, "segundos": res.segundos_trabalho, "arquivos": [str(a) for a in res.arquivos]})
        return res

    # ---- saída ------------------------------------------------------------------------------------------
    def _exportar(self, proj: Projeto, caps, res: Resultado, emitir: Progresso) -> list[Path]:
        op = proj.opcoes
        pasta = res.pasta
        pasta.mkdir(parents=True, exist_ok=True)
        faixas = [exportar.FaixaPronta(c.titulo, proj.pasta_saida / f"{c.id}.wav", proj.prontos[c.id]["duracao"])
                  for c in caps if c.id in proj.prontos and (proj.pasta_saida / f"{c.id}.wav").exists()]
        saidas: list[Path] = []
        slug = caminhos.nome_seguro(proj.titulo, 60)
        emitir({"tipo": "exportando"})
        if op.formato == "m4b":
            saidas.append(exportar.exportar_m4b(faixas, pasta / f"{slug}.m4b", proj.titulo, proj.autor or "Desconhecido", proj.capa()))
        else:
            for i, (c, f) in enumerate(zip([c for c in caps if c.id in proj.prontos], faixas), 1):
                saidas.append(exportar.exportar_faixa(f.arquivo_wav, pasta / f"{i:02d}-{caminhos.nome_seguro(c.titulo, 50)}",
                                                      op.formato, c.titulo, proj.autor or "Desconhecido", proj.titulo, i, len(faixas),
                                                      acx=op.perfil_master == "acx"))
        if op.formato == "m4b" and op.por_capitulo:
            for i, (c, f) in enumerate(zip([c for c in caps if c.id in proj.prontos], faixas), 1):
                saidas.append(exportar.exportar_faixa(f.arquivo_wav, pasta / "capitulos" / f"{i:02d}-{caminhos.nome_seguro(c.titulo, 50)}",
                                                      "mp3", c.titulo, proj.autor or "Desconhecido", proj.titulo, i, len(faixas)))
        meta = {"titulo": proj.titulo, "autor": proj.autor, "idioma": proj.idioma,
                "capitulos": [{"titulo": c.titulo, **proj.prontos.get(c.id, {})} for c in caps],
                "elenco": {k: v for k, v in proj.elenco.items() if v}}
        (pasta / "audiobook.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return saidas

    # ---- prévia -----------------------------------------------------------------------------------------
    def ouvir_texto(self, proj: Projeto, texto: str, max_chars: int = 900) -> tuple[np.ndarray, list[str]]:
        """Fala um pedaço de roteiro (com @Papel e marcação) com o elenco do projeto: a revisão manual ouve a linha antes de salvar."""
        vozes = self.vozes(proj)
        dic = Dicionario(proj.idioma, proj.id)
        avisos: list[str] = []
        lista = _trechos.dividir(texto, dic.abreviacoes(), *self._alvo(vozes["narrador"], proj), separar_falas=True,
                                 usar_contexto=proj.opcoes.contexto_automatico)
        partes, usados = [], 0
        for t in lista:
            if t.pausa > 0:
                partes.append((np.zeros(0, dtype=np.float32), t.pausa))
                continue
            if usados >= max_chars:
                break
            v = vozes.get(t.papel) or vozes.get(_elenco.FALA) or vozes["narrador"]
            txt, ipa = preparar_fala(t.texto, dic, proj.idioma, v.motor == "kokoro")
            if re.search(r"\w", txt):
                a = self.sintetizar(v, txt, ipa, proj.idioma, lambda m: avisos.append(m) if m not in avisos else None, None, t.direcao)
                partes.append((a, self._pausa(t.antes, proj.opcoes) if partes else 0.0))
                usados += len(txt)
        return masterizacao.masterizar(montagem.juntar(partes), proj.opcoes.perfil_master), avisos

    def previa(self, proj: Projeto, cap_id: str, voz: Voz | None = None, max_chars: int = 700) -> np.ndarray:
        cap = next(c for c in proj.capitulos if c.id == cap_id)
        vozes = self.vozes(proj)
        if voz is not None:
            vozes["narrador"] = voz
        dic = Dicionario(proj.idioma, proj.id)
        texto = cap.texto[: max_chars * 3]
        lista = self._trechos_do_capitulo(proj, cap, vozes, dic)
        partes, usados = [], 0
        for t in lista:
            if t.pausa > 0 or usados >= max_chars:
                continue
            v = vozes.get(t.papel) or vozes["narrador"]
            txt, ipa = preparar_fala(t.texto, dic, proj.idioma, v.motor == "kokoro")
            if re.search(r"\w", txt):
                partes.append((self.sintetizar(v, txt, ipa, proj.idioma, direcao=t.direcao), self._pausa(t.antes, proj.opcoes) if partes else 0.0))
                usados += len(txt)
        return masterizacao.masterizar(montagem.juntar(partes), proj.opcoes.perfil_master)
