"""Mantém os motores carregados uma vez só e entrega o áudio de uma voz (com efeitos)."""
from __future__ import annotations

import threading

import numpy as np

from .. import caminhos
from ..configuracao import Configuracao
from ..vozes import efeitos as fx
from ..vozes.modelo import Voz
from .base import Motor, MotorIndisponivel, Progresso
from .chatterbox import MotorChatterbox
from .kokoro import MotorKokoro
from .piper import MotorPiper


class Gerenciador:
    def __init__(self, cfg: Configuracao | None = None) -> None:
        self.cfg = cfg or Configuracao.carregar()
        self._motores: dict[str, Motor] = {"kokoro": MotorKokoro(), "chatterbox": MotorChatterbox(), "piper": MotorPiper()}
        self.erros_plugins: list[str] = []
        self._carregar_plugins()
        self._trava = threading.Lock()  # um motor sintetiza por vez (espeak e torch não gostam de concorrência)

    def _carregar_plugins(self) -> None:
        """Motores de terceiros: cada `*.py` em %LOCALAPPDATA%\\AUDIOBOOKER\\motores_extras define `MOTOR` (subclasse de Motor).
        É assim que cada pessoa usa o modelo que quiser (ver motores_extras_exemplo\\ no código-fonte)."""
        import importlib.util

        pasta = caminhos.LOCAL / "motores_extras"
        for arq in sorted(pasta.glob("*.py")) if pasta.exists() else []:
            try:
                spec = importlib.util.spec_from_file_location(f"audiobooker_plugin_{arq.stem}", arq)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                m = mod.MOTOR()
                if not isinstance(m, Motor) or not m.nome or m.nome in self._motores:
                    raise ValueError("MOTOR precisa ser um Motor com `nome` único")
                self._motores[m.nome] = m
            except Exception as e:  # noqa: BLE001  (um plugin quebrado não derruba o programa)
                self.erros_plugins.append(f"{arq.name}: {e}")

    def lista(self) -> list[Motor]:
        return list(self._motores.values())

    def motor(self, nome: str) -> Motor:
        if nome not in self._motores:
            raise MotorIndisponivel(f"Motor desconhecido: {nome}")
        return self._motores[nome]

    def preparar(self, voz: Voz, progresso: Progresso | None = None) -> Motor:
        m = self.motor(voz.motor)
        if not m.carregado:
            # placa de pouca memória (ex.: 4 GB): dois modelos na GPU ao mesmo tempo derrubam a velocidade em 8x
            for outro in self._motores.values():
                if outro is not m and outro.carregado and outro.dispositivo != "cpu":
                    outro.descarregar()
                    import gc

                    gc.collect()
            pref = self.cfg.dispositivo_kokoro if voz.motor == "kokoro" else self.cfg.dispositivo_chatterbox
            m.carregar(pref, self.cfg.threads, progresso)
        return m

    def seco(self, voz: Voz, texto: str, pronuncias: dict[str, str] | None = None,
             progresso: Progresso | None = None, entrega: dict | None = None) -> np.ndarray:
        """Áudio do motor, sem efeitos (é o que vai para o cache)."""
        with self._trava:
            m = self.preparar(voz, progresso)
            return m.sintetizar(texto, voz, pronuncias, entrega)

    def com_efeitos(self, voz: Voz, audio: np.ndarray) -> np.ndarray:
        return fx.aplicar(audio, 24000, voz.efeitos)

    def falar(self, voz: Voz, texto: str, pronuncias: dict[str, str] | None = None,
              progresso: Progresso | None = None) -> np.ndarray:
        return self.com_efeitos(voz, self.seco(voz, texto, pronuncias, progresso))

    def descrever(self) -> str:
        partes = []
        for m in self._motores.values():
            if m.carregado:
                partes.append(f"{m.nome}: {m.dispositivo.upper()}")
        return " · ".join(partes) or "nenhum motor carregado"
