"""Biblioteca de vozes: fábrica (código) + minhas (um .json por voz em vozes\\)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .. import caminhos
from . import predefinidas
from .modelo import Voz

_NOMES_KOKORO_PADRAO = [
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    "pf_dora", "pm_alex", "pm_santa",
]


def nomes_kokoro_instalados() -> list[str]:
    """Lê os nomes direto do arquivo de vozes do Kokoro. Sem o modelo baixado não há vozes do Kokoro na biblioteca
    (o Chatterbox é o motor padrão; Kokoro e Piper são opcionais)."""
    arq = caminhos.MODELOS / "kokoro" / "voices-v1.0.bin"
    if arq.exists():
        try:
            import numpy as np

            with np.load(arq) as v:
                return sorted(n for n in v.files if n[0] in predefinidas.IDIOMAS_ACEITOS)  # só inglês e português
        except Exception:  # noqa: BLE001
            pass
    return []


class BibliotecaVozes:
    def __init__(self) -> None:
        caminhos.garantir()
        from . import catalogo_externo

        self._fabrica = {v.id: v for v in predefinidas.todas(nomes_kokoro_instalados(), catalogo_externo.instaladas())}

    # ---- leitura
    def minhas(self) -> list[Voz]:
        saida = []
        for arq in sorted(caminhos.VOZES.glob("*.json")):
            try:
                saida.append(Voz.de_dict(json.loads(arq.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError):
                continue
        return saida

    def fabrica(self) -> list[Voz]:
        return list(self._fabrica.values())

    def todas(self) -> list[Voz]:
        return self.minhas() + self.fabrica()

    def obter(self, id_: str) -> Voz | None:
        arq = caminhos.VOZES / f"{id_}.json"
        if arq.exists():
            try:
                return Voz.de_dict(json.loads(arq.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError):
                pass
        return self._fabrica.get(id_)

    def obter_ou_erro(self, id_: str) -> Voz:
        v = self.obter(id_)
        if v is None:
            raise KeyError(f"Voz não encontrada: {id_}")
        return v

    # ---- escrita
    def id_livre(self, nome: str) -> str:
        base = caminhos.nome_seguro(nome)
        id_, n = base, 2
        while (caminhos.VOZES / f"{id_}.json").exists() or id_ in self._fabrica:
            id_ = f"{base}-{n}"
            n += 1
        return id_

    def salvar(self, voz: Voz) -> Voz:
        if voz.sistema or voz.id in self._fabrica:
            voz = voz.copia(id=self.id_livre(voz.nome))
        tmp = caminhos.VOZES / f"{voz.id}.json.tmp"
        tmp.write_text(json.dumps(voz.para_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(caminhos.VOZES / f"{voz.id}.json")
        return voz

    def apagar(self, id_: str) -> None:
        arq = caminhos.VOZES / f"{id_}.json"
        if arq.exists():
            _para_lixeira(arq)

    # ---- troca entre PCs / backup
    def exportar(self, id_: str, destino: Path) -> Path:
        """Zip com o preset e o áudio de referência (se houver)."""
        v = self.obter_ou_erro(id_)
        destino = Path(destino)
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("voz.json", json.dumps(v.para_dict(), indent=2, ensure_ascii=False))
            ref = v.caminho_referencia()
            if ref and ref.exists():
                z.write(ref, f"referencias/{ref.name}")
        return destino

    def importar(self, arquivo: Path) -> Voz:
        with zipfile.ZipFile(arquivo) as z:
            voz = Voz.de_dict(json.loads(z.read("voz.json")))
            for nome in z.namelist():
                if nome.startswith("referencias/") and not nome.endswith("/"):
                    alvo = caminhos.REFERENCIAS / Path(nome).name
                    caminhos.REFERENCIAS.mkdir(parents=True, exist_ok=True)
                    alvo.write_bytes(z.read(nome))
        voz.id = self.id_livre(voz.nome)
        voz.sistema = False
        return self.salvar(voz)


def _para_lixeira(arq: Path) -> None:
    try:
        from ctypes import windll, Structure, c_void_p, c_wchar_p, c_uint, c_int, byref, sizeof

        class SHFILEOPSTRUCT(Structure):
            _fields_ = [("hwnd", c_void_p), ("wFunc", c_uint), ("pFrom", c_wchar_p), ("pTo", c_wchar_p),
                        ("fFlags", c_uint), ("fAnyOperationsAborted", c_int), ("hNameMappings", c_void_p), ("lpszProgressTitle", c_wchar_p)]

        op = SHFILEOPSTRUCT(None, 3, str(arq) + "\0", None, 0x40 | 0x10 | 0x4 | 0x400, 0, None, None)
        windll.shell32.SHFileOperationW(byref(op))
        if not arq.exists():
            return
    except Exception:  # noqa: BLE001
        pass
    arq.unlink(missing_ok=True)
