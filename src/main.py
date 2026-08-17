"""Audiobooker entry point: composition root (§42). Wires infrastructure,
application services, and the presentation layer together explicitly — no
dependency-injection framework, no globals."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from infrastructure.persistence.settings_store import cache_dir, config_dir, library_dir
from infrastructure.tts.model_manager import ChatterboxModelManager
from presentation.windows.main_window import MainWindow

# Project root: two levels up from this file (src/main.py -> project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _configure_cpu_threads() -> None:
    """Must run before the first `import torch` anywhere in the process —
    OMP/MKL read their thread-count env vars once, at native thread-pool
    init time, and no module in this codebase imports torch at module scope,
    so the top of main() is genuinely the earliest safe point. No-op by
    default: the right thread count is hardware-specific (and matters far
    more for CPU-fallback narration than the GPU path, where only cheap
    numpy-based validation/assembly work runs on CPU), so it needs
    benchmarking (scripts/benchmark_generation.py --cpu-threads) rather than
    a guessed default. Setting AUDIOBOOKER_CPU_THREADS lets that benchmark
    (or an advanced user) opt into a specific value without any other code
    change."""
    threads = os.environ.get("AUDIOBOOKER_CPU_THREADS")
    if threads:
        os.environ.setdefault("OMP_NUM_THREADS", threads)
        os.environ.setdefault("MKL_NUM_THREADS", threads)


def _setup_logging() -> None:
    """Rotating file logger (§40). Never logs full book content, voice
    samples, or other sensitive data — only operational messages."""
    logs_dir = _PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        logs_dir / "audiobooker.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    # On Windows, a console attached via a legacy code page (cp1252
    # "charmap") can't encode characters like the ✅ that chatterbox's own
    # logger emits. StreamHandler.emit() normally swallows encoding errors,
    # but its handleError() fallback re-prints the same unencodable message
    # and that second UnicodeEncodeError isn't an OSError, so it escapes
    # uncaught and crashes whatever code triggered the log call instead of
    # just dropping the console line. errors="backslashreplace" makes the
    # stream itself tolerant so this can't happen.
    if hasattr(console_handler.stream, "reconfigure"):
        try:
            console_handler.stream.reconfigure(errors="backslashreplace")
        except (ValueError, OSError):
            pass

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    root_logger.addHandler(console_handler)


def _resolve_resources_dir() -> Path:
    """Where logo.png lives. Prefers the bundled presentation/resources copy
    (always present after packaging); falls back to the project root copy
    used during development, per §2."""
    bundled = Path(__file__).resolve().parent / "presentation" / "resources"
    if (bundled / "logo.png").exists():
        return bundled
    return _PROJECT_ROOT


def main() -> int:
    _configure_cpu_threads()
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Iniciando Audiobooker")

    # Must be set before QApplication() so Wayland/KDE can match the running
    # process to scripts/audiobooker.desktop and use its Icon= for the
    # taskbar/dock, not just the in-process setWindowIcon below (per §2).
    QGuiApplication.setDesktopFileName("audiobooker")

    if sys.platform == "win32":
        # Without an explicit AppUserModelID, Windows falls back to grouping
        # this process under its host executable's own taskbar identity
        # (python.exe/pythonw.exe in dev mode, or a generic default even for
        # the frozen .exe) instead of treating it as its own app — which is
        # why the taskbar/titlebar can show a blank or wrong icon even
        # though setWindowIcon() below is set correctly and the .exe has its
        # own --icon resource. Must run before QApplication()/any window is
        # created. No-op (silently) on non-Windows or older Windows builds
        # missing this shell32 export.
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Audiobooker.Audiobooker")
        except (AttributeError, OSError):
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Audiobooker")
    app.setOrganizationName("Audiobooker")

    resources_dir = _resolve_resources_dir()
    logo_path = resources_dir / "logo.png"
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))

    sessions_dir = _PROJECT_ROOT / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    cache_directory = cache_dir()
    cache_directory.mkdir(parents=True, exist_ok=True)
    config_directory = config_dir()
    config_directory.mkdir(parents=True, exist_ok=True)
    library_directory = library_dir()
    library_directory.mkdir(parents=True, exist_ok=True)

    model_manager = ChatterboxModelManager()

    window = MainWindow(
        resources_dir=resources_dir,
        sessions_dir=sessions_dir,
        cache_dir=cache_directory,
        config_dir=config_directory,
        library_dir=library_directory,
        model_manager=model_manager,
    )
    window.show()

    exit_code = app.exec()
    logger.info("Encerrando Audiobooker")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
