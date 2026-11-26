"""Cadeia de efeitos de voz (robô, capacete, rouquidão, rádio...). Roda depois da síntese, então
mudar um efeito nunca obriga a sintetizar de novo.

Cada efeito é um dicionário {"tipo": ..., <parâmetros>}. O CATALOGO descreve os parâmetros para a interface
montar os controles sozinha.
"""
from __future__ import annotations

import numpy as np

# (chave, rótulo, mínimo, máximo, padrão, passo, unidade)
CATALOGO: dict[str, dict] = {
    "tom": {"nome": "Tom (grave/agudo)", "ajuda": "Sobe ou desce o tom da voz em semitons. Negativo = mais grosso.",
            "params": [("semitons", "Semitons", -24, 12, -3, 0.5, "st"), ("corpo", "Corpo (timbre acompanha)", 0, 1, 0, 0.05, "")]},
    "equalizador": {"nome": "Equalizador", "ajuda": "Realça ou corta graves, médios e agudos.",
                    "params": [("graves", "Graves", -18, 18, 0, 0.5, "dB"), ("medios", "Médios", -18, 18, 0, 0.5, "dB"),
                               ("agudos", "Agudos", -18, 18, 0, 0.5, "dB")]},
    "filtro": {"nome": "Filtro (rádio/telefone)", "ajuda": "Corta o que está abaixo/acima: som de rádio, telefone, interfone.",
               "params": [("passa_alta", "Corta abaixo de", 20, 2000, 300, 10, "Hz"), ("passa_baixa", "Corta acima de", 1500, 20000, 3400, 50, "Hz")]},
    "rouquidao": {"nome": "Rouquidão / rascante", "ajuda": "Voz áspera, de fumante, orc, demônio: saturação, sopro e fritura vocal.",
                  "params": [("quantidade", "Quantidade", 0, 1, 0.5, 0.05, ""), ("aspereza", "Fritura", 20, 200, 60, 5, "Hz")]},
    "camada": {"nome": "Camada (voz dupla em outro tom)", "ajuda": "Soma uma cópia mais grave (−12 = oitava abaixo: monstro, demônio) ou mais aguda (fantasma).",
               "params": [("semitons", "Tom da camada", -24, 12, -12, 1, "st"), ("mistura", "Mistura", 0, 1, 0.4, 0.05, "")]},
    "distorcao": {"nome": "Distorção", "ajuda": "Saturação: de calor leve a voz estourada.",
                  "params": [("ganho", "Intensidade", 0, 40, 8, 0.5, "dB")]},
    "robo": {"nome": "Robô (modulação em anel)", "ajuda": "Som metálico de robô/dalek. Frequência baixa = rouco; alta = sino.",
             "params": [("frequencia", "Frequência", 20, 800, 60, 5, "Hz"), ("mistura", "Mistura", 0, 1, 0.8, 0.05, ""),
                        ("metal", "Ressonância metálica", 0, 0.9, 0.35, 0.05, "")]},
    "bitcrush": {"nome": "Digital degradado", "ajuda": "Reduz resolução e taxa: voz de máquina antiga, rádio digital.",
                 "params": [("bits", "Bits", 4, 16, 10, 1, "bit"), ("reducao", "Redução de taxa", 1, 16, 2, 1, "x")]},
    "coro": {"nome": "Coro / flanger", "ajuda": "Duplica a voz levemente: IA de nave, dupla personalidade.",
             "params": [("taxa", "Velocidade", 0.1, 8, 1.2, 0.1, "Hz"), ("profundidade", "Profundidade", 0, 1, 0.35, 0.05, ""),
                        ("mistura", "Mistura", 0, 1, 0.4, 0.05, "")]},
    "eco": {"nome": "Eco", "ajuda": "Repetição que some aos poucos.",
            "params": [("atraso", "Atraso", 20, 1200, 220, 10, "ms"), ("realimentacao", "Repetições", 0, 0.9, 0.3, 0.05, ""),
                       ("mistura", "Mistura", 0, 1, 0.25, 0.05, "")]},
    "reverb": {"nome": "Reverb (ambiente)", "ajuda": "Tamanho do espaço: capacete (pequeno), catedral (grande).",
               "params": [("sala", "Tamanho", 0, 1, 0.3, 0.05, ""), ("amortecimento", "Absorção", 0, 1, 0.5, 0.05, ""),
                          ("mistura", "Mistura", 0, 1, 0.2, 0.05, "")]},
    "ruido": {"nome": "Estática / chiado", "ajuda": "Ruído de fundo de rádio ou comunicador.",
              "params": [("nivel", "Nível", -70, -15, -45, 1, "dB")]},
    "compressor": {"nome": "Compressor", "ajuda": "Deixa a voz mais constante e encorpada.",
                   "params": [("limiar", "Limiar", -40, 0, -18, 1, "dB"), ("razao", "Razão", 1, 20, 3, 0.5, ":1")]},
    "ganho": {"nome": "Ganho", "ajuda": "Volume final.", "params": [("db", "Ganho", -24, 24, 0, 0.5, "dB")]},
}


def padrao(tipo: str) -> dict:
    d = {"tipo": tipo}
    for chave, _r, _mn, _mx, pad, _p, _u in CATALOGO[tipo]["params"]:
        d[chave] = pad
    return d


def _p(e: dict, chave: str):
    for k, _r, _mn, _mx, pad, _p2, _u in CATALOGO[e["tipo"]]["params"]:
        if k == chave:
            return e.get(chave, pad)
    raise KeyError(chave)


def _ruido_filtrado(n: int, sr: int, freq: float, semente: int = 7) -> np.ndarray:
    from scipy.signal import butter, lfilter

    rng = np.random.default_rng(semente)
    ruido = rng.standard_normal(n).astype(np.float32)
    b, a = butter(2, min(0.45, max(freq, 1.0) / (sr / 2)))
    r = lfilter(b, a, ruido).astype(np.float32)
    pico = float(np.max(np.abs(r))) or 1.0
    return r / pico


def _rouquidao(x: np.ndarray, sr: int, q: float, freq: float) -> np.ndarray:
    """Aspereza natural: saturação em paralelo + sopro que segue o volume da voz + fritura leve.
    (A versão antiga modulava a amplitude com ruído e soava robótica.)"""
    if q <= 0 or len(x) == 0:
        return x
    from scipy.signal import butter, lfilter

    rms = float(np.sqrt(np.mean(x ** 2))) + 1e-9
    drive = 1.0 + 7.0 * q
    sat = np.tanh(x * drive / max(float(np.max(np.abs(x))), 1e-6) * 1.2)
    sat *= rms / (float(np.sqrt(np.mean(sat ** 2))) + 1e-9)
    y = (1.0 - 0.65 * q) * x + 0.65 * q * sat
    # sopro (aspiração) na faixa 1,2-6 kHz, com a mesma envoltória da fala
    rng = np.random.default_rng(5)
    b, a = butter(2, [1200 / (sr / 2), min(0.95, 6000 / (sr / 2))], btype="band")
    ruido = lfilter(b, a, rng.standard_normal(len(x))).astype(np.float32)
    ruido /= float(np.std(ruido)) + 1e-9
    k = max(1, int(sr * 0.02))
    env = np.convolve(np.abs(x), np.ones(k, dtype=np.float32) / k, mode="same")
    y = y + ruido * env * 0.12 * q
    # fritura vocal: queda de amplitude rasa e periódica (freq = aspereza)
    t = np.arange(len(x), dtype=np.float32) / sr
    y = y * (1.0 - 0.10 * q * (0.5 + 0.5 * np.sin(2 * np.pi * freq * t)))
    return y.astype(np.float32)


def _camada(x: np.ndarray, sr: int, semitons: float, mistura: float) -> np.ndarray:
    """Soma uma cópia da voz em outro tom (oitava abaixo = peso/monstro; acima = fantasma)."""
    import pedalboard as pb

    if mistura <= 0 or abs(semitons) < 0.1:
        return x
    c = np.squeeze(pb.time_stretch(x, sr, 1.0, semitons)).astype(np.float32)
    n = min(len(x), len(c))
    return (x[:n] + mistura * c[:n]).astype(np.float32)


def _robo(x: np.ndarray, sr: int, freq: float, mistura: float, metal: float) -> np.ndarray:
    t = np.arange(len(x), dtype=np.float32) / sr
    mod = np.sin(2 * np.pi * freq * t).astype(np.float32)
    y = x * mod
    if metal > 0:  # filtro pente curto = ressonância metálica
        from scipy.signal import lfilter

        atraso = max(2, int(sr * 0.0042))
        a = np.zeros(atraso + 1)
        a[0], a[-1] = 1.0, -metal
        y = lfilter([1.0], a, y).astype(np.float32) * (1.0 - metal * 0.6)
    return ((1 - mistura) * x + mistura * y).astype(np.float32)


def _reduzir_taxa(x: np.ndarray, fator: int) -> np.ndarray:
    if fator <= 1:
        return x
    n = len(x) // fator * fator
    seg = x[:n].reshape(-1, fator)[:, 0]
    return np.repeat(seg, fator)[: len(x)].astype(np.float32)


def aplicar(audio: np.ndarray, sr: int, efeitos: list[dict]) -> np.ndarray:
    """Aplica a cadeia na ordem dada. Retorna float32 mono, no mesmo tamanho (+cauda de eco/reverb)."""
    if not efeitos:
        return audio
    import pedalboard as pb

    x = np.asarray(audio, dtype=np.float32)
    cauda = 0
    for e in efeitos:
        t = e.get("tipo")
        if t not in CATALOGO or e.get("ativo", True) is False:
            continue
        if t == "tom":
            st = float(_p(e, "semitons"))
            if abs(st) > 0.01:
                # time_stretch do Rubber Band com timbre preservado: medido com Whisper, o PitchShift comum
                # deixava a fala ininteligível (erro de 104% em −4 st); este mantém ~15% mesmo em −9 st
                preservado = np.squeeze(pb.time_stretch(x, sr, 1.0, st)).astype(np.float32)
                corpo = float(_p(e, "corpo"))
                if corpo > 0.01:  # parte do timbre acompanha o tom: voz de "corpo maior" (orc, gigante) sem perder a fala
                    acompanha = np.squeeze(pb.time_stretch(x, sr, 1.0, st, preserve_formants=False)).astype(np.float32)
                    n = min(len(preservado), len(acompanha))
                    preservado = (1 - corpo) * preservado[:n] + corpo * acompanha[:n]
                x = preservado
        elif t == "equalizador":
            placa = []
            if abs(_p(e, "graves")) > 0.01:
                placa.append(pb.LowShelfFilter(cutoff_frequency_hz=180, gain_db=float(_p(e, "graves")), q=0.7))
            if abs(_p(e, "medios")) > 0.01:
                placa.append(pb.PeakFilter(cutoff_frequency_hz=1400, gain_db=float(_p(e, "medios")), q=0.8))
            if abs(_p(e, "agudos")) > 0.01:
                placa.append(pb.HighShelfFilter(cutoff_frequency_hz=5500, gain_db=float(_p(e, "agudos")), q=0.7))
            if placa:
                x = pb.Pedalboard(placa)(x, sr)
        elif t == "filtro":
            x = pb.Pedalboard([pb.HighpassFilter(float(_p(e, "passa_alta"))),
                               pb.LowpassFilter(min(float(_p(e, "passa_baixa")), sr / 2 - 100))])(x, sr)
        elif t == "camada":
            x = _camada(x, sr, float(_p(e, "semitons")), float(_p(e, "mistura")))
        elif t == "rouquidao":
            x = _rouquidao(x, sr, float(_p(e, "quantidade")), float(_p(e, "aspereza")))
        elif t == "distorcao":
            x = pb.Pedalboard([pb.Distortion(drive_db=float(_p(e, "ganho"))), pb.Gain(-min(12.0, float(_p(e, "ganho")) * 0.5))])(x, sr)
        elif t == "robo":
            x = _robo(x, sr, float(_p(e, "frequencia")), float(_p(e, "mistura")), float(_p(e, "metal")))
        elif t == "bitcrush":
            x = _reduzir_taxa(x, int(_p(e, "reducao")))
            x = pb.Pedalboard([pb.Bitcrush(bit_depth=float(_p(e, "bits")))])(x, sr)
        elif t == "coro":
            x = pb.Pedalboard([pb.Chorus(rate_hz=float(_p(e, "taxa")), depth=float(_p(e, "profundidade")),
                                         centre_delay_ms=7.0, feedback=0.1, mix=float(_p(e, "mistura")))])(x, sr)
        elif t == "eco":
            at = float(_p(e, "atraso")) / 1000.0
            fb = float(_p(e, "realimentacao"))
            x = np.concatenate([x, np.zeros(int(sr * min(3.0, at * (2 + 4 * fb))), dtype=np.float32)])
            cauda = max(cauda, 0)
            x = pb.Pedalboard([pb.Delay(delay_seconds=at, feedback=fb, mix=float(_p(e, "mistura")))])(x, sr)
        elif t == "reverb":
            m = float(_p(e, "mistura"))
            x = np.concatenate([x, np.zeros(int(sr * (0.2 + 1.8 * float(_p(e, "sala")))), dtype=np.float32)])
            x = pb.Pedalboard([pb.Reverb(room_size=float(_p(e, "sala")), damping=float(_p(e, "amortecimento")),
                                         wet_level=m, dry_level=1.0 - 0.5 * m, width=0.6)])(x, sr)
        elif t == "ruido":
            nivel = 10 ** (float(_p(e, "nivel")) / 20)
            rng = np.random.default_rng(11)
            from scipy.signal import butter, lfilter

            b, a = butter(2, [200 / (sr / 2), min(0.9, 5000 / (sr / 2))], btype="band")
            r = lfilter(b, a, rng.standard_normal(len(x))).astype(np.float32)
            r /= max(1e-6, float(np.std(r)))
            # chiado mais forte onde há fala (rádio abrindo o squelch)
            env = np.abs(x)
            k = max(1, int(sr * 0.05))
            env = np.convolve(env, np.ones(k, dtype=np.float32) / k, mode="same")
            x = x + r * nivel * (0.4 + 0.6 * np.clip(env * 6, 0, 1))
        elif t == "compressor":
            x = pb.Pedalboard([pb.Compressor(threshold_db=float(_p(e, "limiar")), ratio=float(_p(e, "razao")), attack_ms=8, release_ms=120)])(x, sr)
        elif t == "ganho":
            x = pb.Pedalboard([pb.Gain(float(_p(e, "db")))])(x, sr)
    x = np.nan_to_num(x.astype(np.float32))
    pico = float(np.max(np.abs(x))) if len(x) else 0.0
    if pico > 0.98:
        x = x * (0.98 / pico)
    return x
