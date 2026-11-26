"""Autoteste do programa (rápido) e teste de inteligibilidade das vozes (usa Whisper, opcional).

  python -m audiobooker autoteste          verifica texto, leitura de livros, efeitos, geração, retomada e exportação
  python -m audiobooker testar-vozes [id…] mede quanto de cada voz um reconhecedor de fala entende (WER); efeitos que
                                           destroem a fala aparecem com erro alto (precisa: uv pip install faster-whisper)
"""
from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path

import numpy as np

from . import caminhos


def _ok(t): print(f"   ok  {t}", flush=True)
def _x(t): print(f"   x   {t}", flush=True)


def autoteste() -> int:
    import soundfile as sf

    from .audio import masterizacao
    from .documentos import capitulos, leitor
    from .motores.gerenciador import Gerenciador
    from .producao.gerador import Gerador
    from .producao.projeto import Projeto
    from .texto import elenco, limpeza, numeros, trechos
    from .texto.pronuncias import Dicionario
    from .vozes import efeitos as fx
    from .vozes.biblioteca import BibliotecaVozes

    falhas = 0

    def checar(nome: str, cond: bool, detalhe: str = "") -> None:
        nonlocal falhas
        (_ok if cond else _x)(nome + ("" if cond or not detalhe else f"  → {detalhe}"))
        falhas += 0 if cond else 1

    print("== Texto")
    checar("números em inglês", "nineteen eighty-four" in numeros.por_extenso("In 1984", "en"))
    checar("números em português", "quinze de março" in numeros.por_extenso("15/03/1998", "pt"))
    checar("moeda", "reais" in numeros.por_extenso("R$ 10,00", "pt"))
    checar("limpeza de aspas quebradas", "“Hi”" in limpeza.limpar("�Hi�"))
    checar("palavra partida", "proposition" in limpeza.limpar("the proposi tion", "en"))
    d = Dicionario("en")
    checar("abreviações", "Doctor" in d.aplicar("Dr. Who", False))
    tr = trechos.dividir("Dr. Smith went home. He slept.\n\n“Hello,” said Anna.", d.abreviacoes(), separar_falas=True)
    checar("trechos sem cortar abreviação", tr[0].texto.startswith("Dr. Smith went home."), repr(tr[0].texto))
    checar("falas e personagens", any(t.papel == "Anna" for t in tr), str([t.papel for t in tr]))
    checar("pausa explícita", any(t.pausa == 2 for t in trechos.dividir("A. [pausa 2s] B.", d.abreviacoes())))

    print("== Documentos")
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "livro.md"
        md.write_text("# Capítulo 1\n\n" + "Era uma vez um livro de teste. " * 30 + "\n\n# Capítulo 2\n\n" + "Outra história curta e boa. " * 30, encoding="utf-8")
        doc = leitor.ler(md)
        caps = capitulos.detectar(doc, 6000, "pt")
        checar("markdown em dois capítulos", len(caps) == 2, str([c.titulo for c in caps]))
        txt = Path(tmp) / "curto.txt"
        txt.write_text("Texto simples. " * 40, encoding="utf-8")
        checar("txt", leitor.ler(txt).palavras > 50)

    print("== Voz e efeitos")
    b = BibliotecaVozes()
    checar("vozes de fábrica", len(b.fabrica()) >= 6, str(len(b.fabrica())))
    checar("presets sobre o Chatterbox", all(v.motor == "chatterbox" for v in b.fabrica() if "personagem" in v.tags))

    print("== Intonação, contexto e roteiro")
    from .motores.base import Motor
    from .producao import entrega
    from .texto import contexto, direcoes

    pecas = direcoes.interpretar("A [estilo triste]sad[/estilo] [ênfase]word[/ênfase] [pausa 1s] [tag laugh] end.")
    checar("marcação lida", any(p.direcao.estilo == "triste" for p in pecas) and any(p.pausa == 1 for p in pecas) and any(p.direcao.enfase for p in pecas))
    checar("colchete comum fica no texto", "[1]" in direcoes.limpar_marcacao("Ver nota [1] abaixo."))
    checar("contexto: whispered", contexto.estilo_de(", she whispered softly.") == "sussurro")
    checar("contexto: gritou", contexto.estilo_de(" gritou ele.") == "grito")
    rot = elenco.gerar_roteiro("“Run!” shouted Boris.\n\nCalm night.")
    checar("roteiro com papéis e estilos", "@Boris: [estilo grito]" in rot and "@narrador: Calm night." in rot, rot)
    checar("roteiro relido", any(t.papel == "Boris" and t.direcao.estilo == "grito" for t in trechos.dividir(rot, d.abreviacoes())))
    fraco = frozenset()
    forte = frozenset({"emocao", "instrucao", "tags", "palavra"})
    r0 = entrega.resolver(direcoes.Direcao(estilo="sussurro", velocidade=0.9), "hi [laugh]", fraco)
    checar("sem instrução: sussurro e tag IGNORADOS e avisados", not r0.entrega and len(r0.avisos) == 2 and "[laugh]" not in r0.texto, str(r0.avisos))
    checar("velocidade vale em qualquer motor", r0.pos.get("velocidade") == 0.9)
    r1 = entrega.resolver(direcoes.Direcao(estilo="sussurro"), "hi", forte)
    checar("com instrução: sussurro executado", "instrucao" in r1.entrega and not r1.avisos)
    checar("capacidades do Chatterbox", {"emocao", "cfg", "clonagem"} <= set(Gerenciador().motor("chatterbox").capacidades()))
    x = np.sin(2 * np.pi * 150 * np.arange(24000) / 24000).astype(np.float32) * 0.3
    for tipo in fx.CATALOGO:
        y = fx.aplicar(x, 24000, [fx.padrao(tipo)])
        checar(f"efeito {tipo}", len(y) >= len(x) and np.isfinite(y).all() and np.abs(y).max() <= 1.0)
    cru = (np.random.default_rng(1).standard_normal(24000 * 5) * 0.2).astype(np.float32)
    m = masterizacao.masterizar(cru, "audiobook")
    rel = masterizacao.medir(m)
    checar("volume -19 LUFS e pico <= -3 dB", abs(rel.lufs + 19) < 0.7 and rel.pico_db <= -2.9, f"{rel.lufs:.1f} LUFS, pico {rel.pico_db:.1f}")

    print("== Geração (Chatterbox)")
    pronto, motivo = Gerenciador().motor("chatterbox").estado()
    if not pronto:    # instalação sem o Chatterbox (-SemChatterbox): o resto do autoteste já passou
        print(f"   !   pulado: {motivo}", flush=True)
        print("== " + ("tudo certo, exceto a geração (pulada)" if falhas == 0 else f"{falhas} falha(s)"))
        return 0 if falhas == 0 else 1
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "mini.md"
        md.write_text("# Um\n\nThe first chapter is short. It has two sentences, and a few more words to pass the size check.\n\n# Dois\n\n“Hello,” said Anna. The second chapter ends here, with another sentence to keep it company.", encoding="utf-8")
        doc = leitor.ler(md)
        caps = capitulos.detectar(doc, 6000, "en")
        for c in caps:
            c.incluir = True
        proj = Projeto.criar(doc, caps, "en")
        try:
            g = Gerenciador()
            g.cfg.pasta_saida = str(Path(tmp) / "saida")
            gerador = Gerador(g, b)
            proj.elenco["narrador"] = "chatterbox-padrao"
            proj.elenco["Anna"] = "radio-militar"
            proj.opcoes.separar_falas = True
            proj.opcoes.formato = "m4b"
            proj.salvar()
            t0 = time.time()
            r1 = gerador.gerar(proj)
            t1 = time.time() - t0
            checar("gera M4B", bool(r1.arquivos) and r1.arquivos[0].exists() and r1.arquivos[0].stat().st_size > 5000)
            t0 = time.time()
            gerador.gerar(proj)
            checar("segunda geração aproveita o que já está pronto", time.time() - t0 < max(3.0, t1 * 0.3), f"{time.time() - t0:.1f}s vs {t1:.1f}s")
            from .audio import ffmpeg

            sai = ffmpeg.rodar(["-i", str(r1.arquivos[0]), "-f", "ffmetadata", "-"]).stdout
            checar("capítulos no M4B", sai.count("[CHAPTER]") == 2, f"{sai.count('[CHAPTER]')}")
        finally:
            proj.apagar()
    print("== " + ("tudo certo" if falhas == 0 else f"{falhas} falha(s)"))
    return 0 if falhas == 0 else 1


_FRASES = ["For the Emperor, we hold the line and we do not retreat.", "The enemy approaches from the north, so prepare your weapons.",
           "Report to the command post at oh six hundred hours."]


def _wer(ref: str, hyp: str) -> float:
    norm = lambda s: re.sub(r"[^a-z ]", "", s.lower()).split()  # noqa: E731
    r, h = norm(ref), norm(hyp)
    d = np.zeros((len(r) + 1, len(h) + 1), int)
    d[:, 0], d[0, :] = range(len(r) + 1), range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[-1, -1] / max(1, len(r))


def testar_vozes(ids: list[str]) -> int:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        _x("Falta o reconhecedor: rode  uv pip install --python <venv>\\Scripts\\python.exe faster-whisper")
        return 1
    from .motores.gerenciador import Gerenciador
    from .vozes.biblioteca import BibliotecaVozes

    b, g = BibliotecaVozes(), Gerenciador()
    wm = WhisperModel("base.en", device="cpu", compute_type="int8")
    alvo = ids or [v.id for v in b.fabrica() if "personagem" in v.tags and v.idioma == "en"]
    print("== Inteligibilidade (erro de palavras; ~10% é o piso do teste; acima de 40% a voz está ruim)")
    ruins = 0
    for vid in alvo:
        v = b.obter_ou_erro(vid)
        if v.motor != "kokoro" and not v.referencia:
            pass
        erros = []
        for t in _FRASES:
            a = g.falar(v, t)
            seg, _ = wm.transcribe(np.asarray(a, dtype=np.float32), language="en", beam_size=1)
            erros.append(_wer(t, " ".join(s.text for s in seg)))
        e = float(np.mean(erros)) * 100
        (_ok if e < 40 else _x)(f"{vid:28s} erro {e:5.1f}%")
        ruins += e >= 40
    return 0 if ruins == 0 else 1
