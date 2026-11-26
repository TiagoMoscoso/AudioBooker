"""Detecta CPU/GPU e escolhe onde cada motor roda.

- Kokoro (ONNX): CUDA (se onnxruntime-gpu), DirectML (AMD/Intel/NVIDIA no Windows) ou CPU.
  O DirectML é testado de verdade com uma frase curta; se falhar (acontece em algumas placas AMD antigas), cai para CPU.
- Chatterbox (PyTorch): CUDA ou CPU.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Informacao:
    nucleos: int
    cuda: bool
    nome_cuda: str
    dml: bool
    nome_gpu: str  # nome da placa de vídeo principal (qualquer marca)

    def resumo(self) -> str:
        partes = [f"CPU {self.nucleos} núcleos"]
        if self.cuda:
            partes.append(f"CUDA: {self.nome_cuda}")
        elif self.nome_gpu:
            partes.append(f"GPU: {self.nome_gpu}" + (" (DirectML)" if self.dml else " (sem CUDA)"))
        return " · ".join(partes)


@lru_cache(maxsize=1)
def detectar() -> Informacao:
    nucleos = os.cpu_count() or 4
    cuda, nome_cuda = False, ""
    try:
        import torch

        if torch.cuda.is_available():
            cuda, nome_cuda = True, torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001 - torch é opcional
        pass
    dml = False
    try:
        import onnxruntime as rt

        dml = "DmlExecutionProvider" in rt.get_available_providers()
        if not cuda and "CUDAExecutionProvider" in rt.get_available_providers():
            cuda, nome_cuda = True, "CUDA (onnxruntime)"
    except Exception:  # noqa: BLE001
        pass
    return Informacao(nucleos=nucleos, cuda=cuda, nome_cuda=nome_cuda, dml=dml, nome_gpu=_nome_gpu())


def _nome_gpu() -> str:
    try:
        import subprocess

        saida = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name"],
            capture_output=True, text=True, timeout=15, creationflags=0x08000000,
        ).stdout.strip()
        return saida
    except Exception:  # noqa: BLE001
        return ""


def escolher_kokoro(preferencia: str) -> list[str]:
    """Lista de provedores ONNX, do preferido ao reserva."""
    import onnxruntime as rt

    disponiveis = rt.get_available_providers()
    ordem: list[str] = []
    pref = (preferencia or "auto").lower()
    if pref in ("auto", "cuda") and "CUDAExecutionProvider" in disponiveis:
        ordem.append("CUDAExecutionProvider")
    if pref in ("auto", "dml") and "DmlExecutionProvider" in disponiveis:
        ordem.append("DmlExecutionProvider")
    ordem.append("CPUExecutionProvider")
    return ordem


def escolher_chatterbox(preferencia: str) -> str:
    pref = (preferencia or "auto").lower()
    if pref == "cpu":
        return "cpu"
    info = detectar()
    return "cuda" if info.cuda else "cpu"


def threads_efetivas(configurado: int) -> int:
    return configurado if configurado > 0 else max(1, os.cpu_count() or 4)
