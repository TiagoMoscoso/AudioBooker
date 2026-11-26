"""Kokoro-82M (ONNX): rápido, leve, dezenas de vozes, e as vozes podem ser misturadas para criar vozes novas.

Roda em CPU (RTF ~0,3 numa CPU de 8 núcleos) ou GPU (CUDA/DirectML) quando o provedor funciona de verdade; o DirectML é
testado com uma frase e, se falhar, o programa cai para CPU e avisa.
"""
from __future__ import annotations

import re
import urllib.request

import numpy as np

from .. import caminhos, dispositivos
from ..vozes.modelo import Voz
from .base import Motor, MotorIndisponivel, Progresso

_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
_ARQUIVOS = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
_PASTA = caminhos.MODELOS / "kokoro"

_LINGUAS = {"en": "en-us", "pt": "pt-br", "es": "es", "fr": "fr-fr", "it": "it", "hi": "hi", "ja": "ja", "zh": "cmn"}


def _lingua(voz: Voz) -> str:
    if voz.idioma == "en" and voz.base:
        dominante = max(voz.base.items(), key=lambda kv: kv[1])[0]
        if dominante.startswith("b"):
            return "en-gb"
    return _LINGUAS.get(voz.idioma, "en-us")


class MotorKokoro(Motor):
    nome = "kokoro"
    rotulo = "Kokoro (rápido, vozes internas e mistura)"

    def __init__(self) -> None:
        super().__init__()
        self._k = None
        self._estilos: dict[str, np.ndarray] = {}

    @property
    def carregado(self) -> bool:
        return self._k is not None

    def capacidades(self, voz=None) -> frozenset[str]:
        return frozenset({"fonemas"})

    # ---- instalação
    def estado(self) -> tuple[bool, str]:
        faltam = [a for a in _ARQUIVOS if not (_PASTA / a).exists()]
        if faltam:
            return False, "Modelo ainda não baixado (≈350 MB). Use Configurações → Baixar modelos."
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False, "Biblioteca kokoro-onnx não instalada. Rode a instalação do Audiobooker."
        return True, "Pronto"

    def baixar(self, progresso: Progresso | None = None) -> None:
        _PASTA.mkdir(parents=True, exist_ok=True)
        for arq in _ARQUIVOS:
            alvo = _PASTA / arq
            if alvo.exists():
                continue
            tmp = alvo.with_suffix(alvo.suffix + ".parcial")
            if progresso:
                progresso(f"Baixando {arq}…")
            with urllib.request.urlopen(_URL + arq, timeout=60) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                lido = 0
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    f.write(bloco)
                    lido += len(bloco)
                    if progresso and total:
                        progresso(f"Baixando {arq}: {lido * 100 // total}%")
            tmp.replace(alvo)

    # ---- carga
    def carregar(self, preferencia: str, threads: int, progresso: Progresso | None = None) -> None:
        if self._k is not None:
            return
        ok, msg = self.estado()
        if not ok:
            raise MotorIndisponivel(msg)
        import onnxruntime as rt
        from kokoro_onnx import Kokoro

        modelo, vozes = str(_PASTA / _ARQUIVOS[0]), str(_PASTA / _ARQUIVOS[1])
        if "CUDAExecutionProvider" in rt.get_available_providers() and hasattr(rt, "preload_dlls"):
            try:  # usa as DLLs de CUDA/cuDNN que o PyTorch já trouxe
                import torch  # noqa: F401

                rt.preload_dlls()
            except Exception:  # noqa: BLE001
                pass
        opcoes = rt.SessionOptions()
        opcoes.intra_op_num_threads = dispositivos.threads_efetivas(threads)
        opcoes.log_severity_level = 4
        tentativas = dispositivos.escolher_kokoro(preferencia)
        ultimo_erro = ""
        for prov in tentativas:
            try:
                if progresso:
                    progresso(f"Carregando Kokoro ({prov.replace('ExecutionProvider', '')})…")
                sessao = rt.InferenceSession(modelo, opcoes, providers=[prov] if prov != "CPUExecutionProvider" else [prov])
                k = Kokoro.from_session(sessao, vozes)
                k.create("Hello.", voice=next(iter(k.voices.keys())), lang="en-us")  # teste de verdade
                real = sessao.get_providers()[0]  # o ORT pode cair para CPU sem avisar: vale o provedor que ficou ativo
                if prov != "CPUExecutionProvider" and real == "CPUExecutionProvider":
                    raise RuntimeError("o provedor de GPU não carregou (faltam DLLs do CUDA/cuDNN?)")
                self._k = k
                self.dispositivo = {"CUDAExecutionProvider": "cuda", "DmlExecutionProvider": "dml"}.get(real, "cpu")
                if prov != tentativas[0]:
                    self.nota_dispositivo = f"GPU não funcionou com o Kokoro ({ultimo_erro[:80]}); usando CPU."
                break
            except Exception as e:  # noqa: BLE001
                ultimo_erro = str(e).replace("\n", " ")
                self._k = None
        if self._k is None:
            raise MotorIndisponivel(f"Não consegui carregar o Kokoro: {ultimo_erro[:200]}")

    def descarregar(self) -> None:
        self._k = None
        self._estilos.clear()

    # ---- voz
    def _estilo(self, base: dict) -> np.ndarray:
        assert self._k is not None
        if not base:
            base = {"af_heart": 1.0}
        chave = repr(sorted(base.items()))
        if chave in self._estilos:
            return self._estilos[chave]
        total = sum(max(0.0, float(p)) for p in base.values()) or 1.0
        mistura = None
        for nome, peso in base.items():
            if nome not in self._k.voices:
                raise MotorIndisponivel(f"Voz interna '{nome}' não existe neste Kokoro.")
            parte = self._k.get_voice_style(nome) * (max(0.0, float(peso)) / total)
            mistura = parte if mistura is None else mistura + parte
        self._estilos[chave] = mistura.astype(np.float32)
        return self._estilos[chave]

    def sintetizar(self, texto: str, voz: Voz, pronuncias: dict[str, str] | None = None,
                   entrega: dict | None = None) -> np.ndarray:
        if self._k is None:
            raise MotorIndisponivel("Kokoro não carregado.")
        estilo = self._estilo(voz.base)
        lingua = _lingua(voz)
        vel = float(np.clip(voz.velocidade, 0.5, 2.0))
        if pronuncias:
            fonemas = self._fonemizar(texto, lingua, pronuncias)
            audio, _ = self._k.create(fonemas, voice=estilo, speed=vel, lang=lingua, is_phonemes=True, trim=True)
        else:
            audio, _ = self._k.create(texto, voice=estilo, speed=vel, lang=lingua, trim=True)
        return np.asarray(audio, dtype=np.float32)

    def _fonemizar(self, texto: str, lingua: str, ipa: dict[str, str]) -> str:
        """Converte para fonemas, trocando as palavras do dicionário pelo IPA escolhido."""
        k = self._k
        padrao = re.compile(r"(?<!\w)(" + "|".join(re.escape(p) for p in sorted(ipa, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
        saida, pos = [], 0
        for m in padrao.finditer(texto):
            if m.start() > pos:
                saida.append(k.tokenizer.phonemize(texto[pos:m.start()], lingua))
            saida.append(ipa[m.group(1).lower()])
            pos = m.end()
        if pos < len(texto):
            saida.append(k.tokenizer.phonemize(texto[pos:], lingua))
        return re.sub(r"\s+", " ", " ".join(s.strip() for s in saida if s.strip()))
