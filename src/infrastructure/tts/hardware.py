"""Detects available compute hardware for TTS inference (§17): CUDA first,
CPU fallback. Never assumes CUDA is present."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareInfo:
    device: str  # "cuda" or "cpu"
    device_name: str  # human-readable label for the UI, e.g. "NVIDIA GeForce RTX 4090 — CUDA"


class HardwareDetector:
    def detect(self) -> HardwareInfo:
        try:
            import torch
        except ImportError:
            return HardwareInfo(device="cpu", device_name="CPU")

        if torch.cuda.is_available():
            try:
                name = torch.cuda.get_device_name(0)
            except Exception:
                name = "CUDA"
            return HardwareInfo(device="cuda", device_name=f"{name} — CUDA")
        return HardwareInfo(device="cpu", device_name="CPU")
