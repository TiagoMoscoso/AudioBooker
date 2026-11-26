"""Linha de comando (para testes, lotes e automação). A interface gráfica usa as mesmas peças.

  python -m audiobooker dispositivos
  python -m audiobooker vozes
  python -m audiobooker baixar kokoro
  python -m audiobooker frase "Texto curto" --voz robo-classico --saida frase.wav
  python -m audiobooker voz-importar amostra.mp3 --nome "Minha voz" [--reduzir-ruido]
  python -m audiobooker livro livro.epub --listar
  python -m audiobooker livro livro.epub --voz chatterbox-padrao --capitulos 4-7 --formato m4b
  python -m audiobooker autoteste
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import VERSAO, caminhos, dispositivos


# ---- saída de console: "== Etapa", "   ok  ", "   !   ", "   x   " ------------------------
def etapa(t: str) -> None:
    print(f"== {t}", flush=True)


def ok(t: str) -> None:
    print(f"   ok  {t}", flush=True)


def aviso(t: str) -> None:
    print(f"   !   {t}", flush=True)


def erro(t: str) -> None:
    print(f"   x   {t}", flush=True)


def info(t: str) -> None:
    print(f"       {t}", flush=True)


def _faixa_ids(texto: str | None, caps) -> list[str] | None:
    if not texto:
        return None
    ids: list[str] = []
    for parte in texto.split(","):
        parte = parte.strip()
        if "-" in parte:
            a, b = parte.split("-", 1)
            ids += [f"c{n:03d}" for n in range(int(a), int(b) + 1)]
        elif parte:
            ids.append(f"c{int(parte):03d}")
    return ids


def _hms(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def cmd_dispositivos(_a) -> int:
    etapa("Dispositivos")
    i = dispositivos.detectar()
    info(i.resumo())
    ok(f"Kokoro: {'CUDA' if i.cuda else 'DirectML (testado ao carregar; cai para CPU se falhar)' if i.dml else 'CPU'}")
    ok(f"Chatterbox: {'CUDA' if i.cuda else 'CPU (sem CUDA nesta máquina)'}")
    return 0


def cmd_vozes(a) -> int:
    from .vozes.biblioteca import BibliotecaVozes

    b = BibliotecaVozes()
    etapa("Vozes")
    for v in b.minhas() + b.fabrica():
        if a.filtro and a.filtro.lower() not in (v.id + v.nome + " ".join(v.tags)).lower():
            continue
        marca = "" if v.sistema else "*"
        info(f"{marca}{v.id:32s} {v.motor:10s} {v.idioma:3s} {v.nome}")
    return 0


def cmd_baixar(a) -> int:
    from .motores.gerenciador import Gerenciador

    g = Gerenciador()
    for nome in ([a.motor] if a.motor else ["kokoro"]):
        etapa(f"Baixando {nome}")
        g.motor(nome).baixar(lambda m: print("       " + m, flush=True))
        ok("concluído")
    return 0


def cmd_frase(a) -> int:
    import soundfile as sf

    from .motores.gerenciador import Gerenciador
    from .producao.frases import EstudioFrases
    from .vozes.biblioteca import BibliotecaVozes

    b = BibliotecaVozes()
    voz = b.obter_ou_erro(a.voz)
    g = Gerenciador()
    est = EstudioFrases(g)
    etapa(f"Frase com “{voz.nome}”")
    t = time.time()
    x = est.gerar(voz, a.texto, a.idioma, progresso=lambda m: info(m))
    saida = Path(a.saida or f"{caminhos.nome_seguro(a.texto, 40)}.wav")
    sf.write(str(saida), x, 24000)
    ok(f"{len(x) / 24000:.1f} s de áudio em {time.time() - t:.1f} s → {saida}")
    info(g.descrever())
    if g.motor(voz.motor).nota_dispositivo:
        aviso(g.motor(voz.motor).nota_dispositivo)
    return 0


def cmd_voz_importar(a) -> int:
    from .vozes import referencia
    from .vozes.biblioteca import BibliotecaVozes
    from .vozes.modelo import Voz

    etapa("Importando voz externa")
    rel = referencia.importar(Path(a.arquivo), a.nome, a.inicio, a.fim, a.reduzir_ruido)
    ok(f"referência preparada: {rel.arquivo.name} ({rel.duracao:.1f} s)")
    for av in rel.avisos:
        aviso(av)
    b = BibliotecaVozes()
    voz = b.salvar(Voz(id=b.id_livre(a.nome), nome=a.nome, motor="chatterbox", idioma=a.idioma, referencia=rel.arquivo.name,
                       parametros={"exagero": 0.5, "cfg": 0.5, "temperatura": 0.8, "variante": a.variante or ""},
                       descricao="Voz clonada a partir de áudio externo", tags=["clonada"]))
    ok(f"voz salva: {voz.id}")
    return 0


def cmd_livro(a) -> int:
    from .documentos import capitulos as cap_mod
    from .documentos import leitor
    from .motores.gerenciador import Gerenciador
    from .producao.gerador import Cancelado, Gerador
    from .producao.projeto import Projeto
    from .vozes.biblioteca import BibliotecaVozes

    etapa("Lendo o livro")
    doc = leitor.ler(Path(a.arquivo))
    idioma = a.idioma or (doc.idioma[:2] if doc.idioma else "en")
    caps = cap_mod.detectar(doc, a.max_palavras, idioma)
    ok(f"{doc.titulo} — {doc.autor or 'autor desconhecido'} · {doc.palavras} palavras · idioma {idioma}")
    for c in caps:
        info(f"{c.id}  {'[x]' if c.incluir else '[ ]'} {c.palavras:6d} palavras  {c.titulo}")
    if a.listar:
        return 0

    b = BibliotecaVozes()
    voz = b.obter_ou_erro(a.voz)
    proj = Projeto.criar(doc, caps, idioma)
    if a.reaproveitar:
        existente = next((p for p in Projeto.listar() if p.titulo == doc.titulo), None)
        if existente:
            proj.apagar()
            proj = existente
    proj.elenco["narrador"] = voz.id
    for par in a.elenco or []:
        nome, _, vid = par.partition("=")
        proj.elenco[nome.strip()] = vid.strip()
    proj.opcoes.formato = a.formato
    proj.opcoes.separar_falas = bool(a.elenco)
    proj.opcoes.anunciar_capitulos = not a.sem_titulos
    proj.opcoes.perfil_master = a.perfil
    proj.salvar()
    ids = _faixa_ids(a.capitulos, caps)

    g = Gerenciador()
    if a.saida:
        g.cfg.pasta_saida = a.saida
    gerador = Gerador(g, b)
    etapa(f"Narrando com “{voz.nome}”")
    ultimo = [0.0]

    def prog(e: dict) -> None:
        t = e["tipo"]
        if t == "inicio":
            info(f"{e['pendentes']} capítulo(s) a gerar, {e['trechos']} trechos")
        elif t == "capitulo":
            info(f"[{e['indice']}/{e['de']}] {e['titulo']}")
        elif t == "trecho" and time.time() - ultimo[0] > 15:
            ultimo[0] = time.time()
            info(f"   {e['feito']}/{e['total']} trechos · falta ≈ {_hms(e['eta'])}")
        elif t == "capitulo_pronto":
            ok(f"capítulo pronto: {_hms(e['duracao'])} · {e['lufs']:.1f} LUFS")
        elif t == "aviso":
            aviso(e["mensagem"])
        elif t == "motor":
            info(e["mensagem"])
        elif t == "exportando":
            info("exportando…")

    try:
        res = gerador.gerar(proj, ids, prog)
    except Cancelado:
        aviso("cancelado")
        return 1
    etapa("Pronto")
    ok(f"{_hms(res.duracao)} de áudio em {_hms(res.segundos_trabalho)}")
    for arq in res.arquivos:
        info(str(arq))
    info(g.descrever())
    return 0


_TEXTO_BENCH = ("The limits of my language mean the limits of my world. Whereof one cannot speak, thereof one must be silent. "
                "What can be said at all can be said clearly, and a name means an object. The object is its meaning.")


def cmd_benchmark(a) -> int:
    """Mede a velocidade de cada motor NESTE computador e estima o tempo de um livro. Rode em cada PC."""
    import json
    import os
    import time

    from .motores.gerenciador import Gerenciador
    from .vozes.biblioteca import BibliotecaVozes

    b = BibliotecaVozes()
    g = Gerenciador()
    pc = os.environ.get("COMPUTERNAME", "pc")
    etapa(f"Benchmark em {pc}")
    info(dispositivos.detectar().resumo())
    palavras = a.palavras
    horas_audio = palavras / 150 / 60
    resultado: dict = {"pc": pc, "resumo": dispositivos.detectar().resumo(), "motores": {}}
    for voz_id, rotulo in (("kokoro-am-michael", "Kokoro"), ("chatterbox-padrao", "Chatterbox")):
        voz = b.obter_ou_erro(voz_id)
        ok_, msg = g.motor(voz.motor).estado()
        if not ok_:
            aviso(f"{rotulo}: {msg}")
            continue
        try:
            g.seco(voz, "Warm up.")  # carrega o modelo e aquece
            tempo, dur = 0.0, 0.0
            for _ in range(a.repeticoes):
                t0 = time.time()
                x = g.seco(voz, _TEXTO_BENCH)
                tempo += time.time() - t0
                dur += len(x) / 24000
        except Exception as e:  # noqa: BLE001
            aviso(f"{rotulo}: não rodou ({str(e)[:100]})")
            continue
        m = g.motor(voz.motor)
        rtf = tempo / dur
        est = rtf * horas_audio
        ok(f"{rotulo} em {m.dispositivo.upper()}: {1 / rtf:.1f}× o tempo real  ·  livro de {palavras:,} palavras (≈{horas_audio:.1f} h de áudio) ≈ {est:.1f} h".replace(",", "."))
        if m.nota_dispositivo:
            aviso(m.nota_dispositivo)
        resultado["motores"][voz.motor] = {"dispositivo": m.dispositivo, "rtf": round(rtf, 3), "horas_livro": round(est, 2)}
    arq = caminhos.LOCAL / f"benchmark-{pc}.json"
    caminhos.garantir()
    arq.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    info(f"salvo em {arq}")
    return 0


def cmd_candidatos(a) -> int:
    from .documentos import capitulos as cap_mod
    from .documentos import leitor
    from .texto.pronuncias import Dicionario, candidatos

    doc = leitor.ler(Path(a.arquivo))
    caps = cap_mod.detectar(doc)
    idioma = a.idioma or (doc.idioma[:2] or "en")
    texto = "\n\n".join(c.texto for c in caps if c.incluir)
    etapa("Termos que podem sair errados")
    for w, n, motivo in candidatos(texto, idioma, {e.palavra for e in Dicionario(idioma).entradas}):
        info(f"{w:28s} {n:4d}x  {motivo}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):      # console do Windows sem UTF-8: troca o caractere em vez de travar
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="audiobooker", description=f"Audiobooker {VERSAO}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dispositivos").set_defaults(f=cmd_dispositivos)
    s = sub.add_parser("vozes"); s.add_argument("filtro", nargs="?"); s.set_defaults(f=cmd_vozes)
    s = sub.add_parser("baixar"); s.add_argument("motor", nargs="?", choices=["kokoro", "chatterbox"]); s.set_defaults(f=cmd_baixar)
    s = sub.add_parser("frase"); s.add_argument("texto"); s.add_argument("--voz", required=True); s.add_argument("--saida"); s.add_argument("--idioma"); s.set_defaults(f=cmd_frase)
    s = sub.add_parser("voz-importar"); s.add_argument("arquivo"); s.add_argument("--nome", required=True)
    s.add_argument("--inicio", type=float, default=0.0); s.add_argument("--fim", type=float); s.add_argument("--reduzir-ruido", action="store_true")
    s.add_argument("--idioma", default="en"); s.add_argument("--variante", choices=["turbo", "original", "multilingue"]); s.set_defaults(f=cmd_voz_importar)
    s = sub.add_parser("livro"); s.add_argument("arquivo"); s.add_argument("--voz", default="chatterbox-padrao")
    s.add_argument("--capitulos"); s.add_argument("--formato", default="m4b", choices=["m4b", "mp3", "flac", "wav", "m4a"])
    s.add_argument("--saida"); s.add_argument("--idioma"); s.add_argument("--listar", action="store_true")
    s.add_argument("--elenco", nargs="*", help="Nome=voz-id (ex.: fala=robo-classico)"); s.add_argument("--sem-titulos", action="store_true")
    s.add_argument("--perfil", default="audiobook", choices=["audiobook", "acx", "podcast", "off"])
    s.add_argument("--max-palavras", type=int, default=6000); s.add_argument("--reaproveitar", action="store_true")
    s.set_defaults(f=cmd_livro)
    s = sub.add_parser("benchmark"); s.add_argument("--palavras", type=int, default=100000); s.add_argument("--repeticoes", type=int, default=2); s.set_defaults(f=cmd_benchmark)
    sub.add_parser("autoteste").set_defaults(f=lambda a: __import__("audiobooker.testes", fromlist=["x"]).autoteste())
    s = sub.add_parser("testar-vozes"); s.add_argument("ids", nargs="*")
    s.set_defaults(f=lambda a: __import__("audiobooker.testes", fromlist=["x"]).testar_vozes(a.ids))
    s = sub.add_parser("candidatos"); s.add_argument("arquivo"); s.add_argument("--idioma"); s.set_defaults(f=cmd_candidatos)
    a = p.parse_args(argv)
    try:
        return a.f(a)
    except KeyboardInterrupt:
        aviso("interrompido")
        return 130
    except Exception as e:  # noqa: BLE001
        erro(str(e))
        if "--depurar" in (argv or sys.argv):
            raise
        return 1
