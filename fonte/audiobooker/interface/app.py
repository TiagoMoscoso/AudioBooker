"""Ponto de entrada da interface:  pythonw -m audiobooker.interface.app"""
from __future__ import annotations

import logging
import sys
import traceback


def _preparar_log() -> logging.Logger:
    from logging.handlers import RotatingFileHandler

    from .. import caminhos

    caminhos.garantir()
    log = logging.getLogger("audiobooker")
    log.setLevel(logging.INFO)
    h = RotatingFileHandler(caminhos.LOGS / "audiobooker.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    return log


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .. import caminhos
    from . import tema
    from .janela import Janela

    log = _preparar_log()

    def erro_nao_tratado(tipo, valor, tb) -> None:
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        log.error(texto)
        try:
            QMessageBox.critical(None, "Audiobooker", f"Algo deu errado:\n\n{valor}\n\nDetalhes em {caminhos.LOGS / 'audiobooker.log'}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = erro_nao_tratado
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Audiobooker")
    tema.aplicar(app)
    from .base import limpar_previas

    limpar_previas()
    j = Janela()
    j.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
