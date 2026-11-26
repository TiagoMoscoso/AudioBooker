"""Exemplo de motor de terceiros: qualquer servidor com a API `POST /v1/audio/speech` (OpenAI, Kokoro-FastAPI, Voicebox, Orpheus,
Qwen3-TTS servido por vLLM...).

Como usar: copie este arquivo para  %LOCALAPPDATA%\\AUDIOBOOKER\\motores_extras\\  e crie ao lado `openai_compativel.json`:

  {"url": "http://127.0.0.1:8880/v1/audio/speech", "modelo": "kokoro", "voz": "af_heart", "chave": "",
   "capacidades": ["instrucao"]}

`capacidades` diz o que ESSE servidor executa (ver motores/base.py: emocao, cfg, tags, clonagem, fonemas, instrucao, palavra...).
Só o que estiver lá é enviado; o resto das direções é ignorado e avisado na interface. Crie uma voz com motor "openai-compativel".
Contrato de um motor: subclasse de `audiobooker.motores.base.Motor` exposta como `MOTOR` (nome único).
"""
from __future__ import annotations

import io
import json
import urllib.request

import numpy as np

from audiobooker import caminhos
from audiobooker.motores.base import Motor, MotorIndisponivel

_CONFIG = caminhos.LOCAL / "motores_extras" / "openai_compativel.json"


class MotorOpenAICompativel(Motor):
    nome = "openai-compativel"
    rotulo = "Servidor compatível com OpenAI"

    def __init__(self) -> None:
        super().__init__()
        self._cfg: dict = {}

    def _ler(self) -> dict:
        try:
            self._cfg = json.loads(_CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._cfg = {}
        return self._cfg

    def capacidades(self, voz=None) -> frozenset[str]:
        return frozenset(self._ler().get("capacidades", []))

    def estado(self) -> tuple[bool, str]:
        c = self._ler()
        if not c.get("url"):
            return False, f"Crie {_CONFIG} com a url do servidor (veja o topo de openai_compativel.py)."
        return True, f"Servidor em {c['url']}"

    def baixar(self, progresso=None) -> None:
        raise MotorIndisponivel("Este motor é um servidor externo: nada para baixar aqui.")

    def carregar(self, preferencia: str, threads: int, progresso=None) -> None:
        self.dispositivo = "servidor"

    def descarregar(self) -> None:
        self.dispositivo = "cpu"

    @property
    def carregado(self) -> bool:
        return self.dispositivo == "servidor"

    def sintetizar(self, texto, voz, pronuncias=None, entrega=None) -> np.ndarray:
        import soundfile as sf

        c = self._ler()
        corpo = {"model": c.get("modelo", ""), "input": texto, "voice": (next(iter(voz.base), "") or c.get("voz", "")),
                 "response_format": "wav"}
        if entrega and entrega.get("instrucao") and "instrucao" in self.capacidades():
            corpo["instructions"] = entrega["instrucao"]
        req = urllib.request.Request(c["url"], json.dumps(corpo).encode("utf-8"),
                                     {"Content-Type": "application/json", **({"Authorization": f"Bearer {c['chave']}"} if c.get("chave") else {})})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                dados = r.read()
        except OSError as e:
            raise MotorIndisponivel(f"Servidor não respondeu ({e}). Ele está ligado?") from e
        x, sr = sf.read(io.BytesIO(dados), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        if sr != self.sr:
            x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * self.sr / sr)), np.arange(len(x)), x).astype(np.float32)
        return x


MOTOR = MotorOpenAICompativel
