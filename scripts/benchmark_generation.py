#!/usr/bin/env python3
"""Standalone benchmark harness for the audiobook generation pipeline.

Drives GenerateAudiobookService directly against a plain text file, with no
Qt/GUI dependency, using the same composition-root wiring as
presentation.windows.main_window.MainWindow (ChatterboxModelManager ->
ChatterboxSpeechSynthesizer -> ReliableSpeechSynthesizer ->
GenerateAudiobookService) — so a benchmark run exercises exactly the
production code path, just headless. Every run gets its own isolated
sessions/cache/config/library workspace under --output-dir; the real app's
XDG cache/config directories are never touched.

Each --repeat gets a completely fresh ChunkCache (a new subdirectory), so
repeats measure genuine generation-time variance rather than being skewed by
cache hits from a previous repeat.

Usage:
    scripts/benchmark_generation.py --language en
    scripts/benchmark_generation.py --language pt --repeat 3
    scripts/benchmark_generation.py --input my_chapter.txt --language en --no-warmup
    scripts/benchmark_generation.py --language en --tf32   # EXPERIMENTAL, see --help

Prints a summary table and writes each repeat's performance_report.json /
diagnostics_report.json path so before/after change sets can be diffed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"
sys.path.insert(0, str(_SRC_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input", type=Path, default=None,
        help="Plain text file to narrate (default: teste_en.txt/teste_pt.txt matching --language)",
    )
    parser.add_argument("--language", choices=["en", "pt"], default="en")
    parser.add_argument("--voice", type=Path, default=None, help="Optional voice reference WAV")
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Isolated benchmark workspace (default: scripts/.benchmark_runs/<timestamp>)",
    )
    parser.add_argument("--repeat", type=int, default=1, help="Number of independent repeats")
    parser.add_argument(
        "--warmup", action=argparse.BooleanOptionalAction, default=True,
        help="Toggle the post-load warm-up inference call (default: on, matching production)",
    )
    parser.add_argument(
        "--cpu-threads", type=int, default=None,
        help="Sets OMP_NUM_THREADS/MKL_NUM_THREADS before torch is ever imported (BENCHMARK REQUIRED — no tuned default exists yet)",
    )
    parser.add_argument(
        "--tf32", action="store_true",
        help=(
            "EXPERIMENTAL, off by default: enables torch.backends.cuda.matmul.allow_tf32 "
            "for this run only. Not enabled by default anywhere in the app — this flag exists "
            "purely so a benchmark can numerically compare RTF/VRAM with/without it. Quality "
            "must still be judged by listening; this script only reports timing and the "
            "existing AudioQualityValidator pass/fail heuristics, not perceptual quality."
        ),
    )
    return parser.parse_args()


def _default_input(language: str) -> Path:
    name = "teste_en.txt" if language == "en" else "teste_pt.txt"
    return _PROJECT_ROOT / name


def _run_once(
    run_dir: Path, input_path: Path, language: str, voice: Path | None,
    warmup: bool, run_label: str,
) -> dict:
    from domain.chapter import Chapter
    from domain.generation import OutputSettings
    from domain.narration import NarrationLanguage, NarrationSettings, VoiceReference
    from infrastructure.persistence.checkpoint_store import CheckpointStore
    from infrastructure.persistence.chunk_cache import ChunkCache
    from infrastructure.persistence.pronunciation_store import PronunciationStore
    from infrastructure.tts.chatterbox_synthesizer import ChatterboxSpeechSynthesizer
    from infrastructure.tts.hardware import HardwareDetector
    from infrastructure.tts.model_manager import ChatterboxModelManager
    from infrastructure.tts.reliable_synthesizer import ReliableSpeechSynthesizer
    from application.generate_audiobook import GenerateAudiobookService
    from services.narration_chunker import NarrationChunker
    from services.spoken_form_normalizer import SpokenFormNormalizer

    sessions_dir = run_dir / "sessions"
    cache_dir = run_dir / "cache"
    config_dir = run_dir / "config"
    library_dir = run_dir / "library"
    for d in (sessions_dir, cache_dir, config_dir, library_dir):
        d.mkdir(parents=True, exist_ok=True)

    model_manager = ChatterboxModelManager(warm_up=warmup)
    pronunciation_rules = PronunciationStore(config_dir).load_effective()
    chunker = NarrationChunker(abbreviation_tokens=pronunciation_rules.abbreviation_tokens())
    normalizer = SpokenFormNormalizer(rule_set=pronunciation_rules)
    synthesizer = ReliableSpeechSynthesizer(ChatterboxSpeechSynthesizer(model_manager))
    checkpoint_store = CheckpointStore(sessions_dir)
    chunk_cache = ChunkCache(cache_dir)
    service = GenerateAudiobookService(
        synthesizer, checkpoint_store, chunk_cache, library_dir,
        chunker=chunker, normalizer=normalizer,
    )

    nl = NarrationLanguage(language)
    voice_reference = VoiceReference(name=voice.stem, path=voice) if voice else None
    settings = NarrationSettings(language=nl, voice_reference=voice_reference)
    output_settings = OutputSettings()

    chapter = Chapter(
        id=uuid.uuid4().hex[:12], title=input_path.stem, order=0,
        text=input_path.read_text(encoding="utf-8"), included=True,
    )

    # Model preparation (download/load + optional warm-up) is deliberately
    # timed and reported separately, mirroring the real app's ModelPrepareWorker
    # running ahead of the generation screen — otherwise the first repeat's
    # generation_time would be dominated by one-time load cost that has
    # nothing to do with the pipeline changes being measured.
    hardware = HardwareDetector().detect()
    prep_start = time.monotonic()
    model_manager.get_model(nl)
    model_prep_seconds = time.monotonic() - prep_start

    manifest = service.start_session(
        book_title=f"benchmark-{run_label}", source_path=str(input_path),
        chapters=[chapter], settings=settings, output_settings=output_settings,
    )

    gen_start = time.monotonic()
    result = service.run(
        manifest, [chapter], settings, on_progress=lambda p: None, should_cancel=lambda: False,
    )
    wall_clock_seconds = time.monotonic() - gen_start

    book_dir = library_dir / result.book_id
    performance_report = json.loads((book_dir / "performance_report.json").read_text(encoding="utf-8"))
    diagnostics_report = json.loads((book_dir / "diagnostics_report.json").read_text(encoding="utf-8"))

    return {
        "run_label": run_label,
        "device": hardware.device,
        "device_name": hardware.device_name,
        "model_prep_seconds": model_prep_seconds,
        "wall_clock_seconds": wall_clock_seconds,
        "book_dir": str(book_dir),
        "performance_report": performance_report,
        "diagnostics_report": diagnostics_report,
    }


def _print_summary(runs: list[dict]) -> None:
    header = (
        f"{'run':<8} {'model_prep_s':>12} {'wall_clock_s':>12} {'avg_rtf':>8} "
        f"{'peak_vram_mb':>12} {'ckpt_flushes':>12} {'ckpt_flush_s':>12} {'retries':>8} {'warnings':>9}"
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        perf = run["performance_report"]
        diag = run["diagnostics_report"]
        peak_vram = perf.get("peak_gpu_memory_bytes")
        peak_vram_mb = f"{peak_vram / (1024 * 1024):.1f}" if peak_vram is not None else "n/a"
        avg_rtf = perf.get("average_rtf")
        avg_rtf_s = f"{avg_rtf:.3f}" if avg_rtf is not None else "n/a"
        print(
            f"{run['run_label']:<8} {run['model_prep_seconds']:>12.2f} {run['wall_clock_seconds']:>12.2f} "
            f"{avg_rtf_s:>8} {peak_vram_mb:>12} {perf['checkpoint_flush_count']:>12} "
            f"{perf['total_checkpoint_flush_time_seconds']:>12.3f} {diag['total_retries']:>8} "
            f"{diag['chunks_with_warnings']:>9}"
        )


def main() -> int:
    args = _parse_args()

    # Must happen before torch is ever imported anywhere in the process
    # (mirrors main._configure_cpu_threads — duplicated here in ~2 lines
    # rather than imported, so this script never has to import main.py and
    # drag in PySide6/Qt just to set two env vars).
    if args.cpu_threads:
        os.environ.setdefault("OMP_NUM_THREADS", str(args.cpu_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(args.cpu_threads))

    if args.tf32:
        import torch
        print("WARNING: --tf32 is experimental and not enabled by default anywhere in the app.")
        print("         This only measures timing/VRAM — judge audio quality by listening before")
        print("         ever considering this for a default profile.")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    input_path = args.input or _default_input(args.language)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or (_PROJECT_ROOT / "scripts" / ".benchmark_runs" / timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input: {input_path}")
    print(f"Output dir: {output_dir}")
    print(f"Language: {args.language}  Warmup: {args.warmup}  Repeats: {args.repeat}")
    print()

    runs = []
    for i in range(1, args.repeat + 1):
        run_label = f"run{i}"
        run_dir = output_dir / run_label
        print(f"--- {run_label} ---")
        result = _run_once(run_dir, input_path, args.language, args.voice, args.warmup, run_label)
        print(
            f"  model_prep={result['model_prep_seconds']:.2f}s  "
            f"generation+finalize={result['wall_clock_seconds']:.2f}s  "
            f"book_dir={result['book_dir']}"
        )
        runs.append(result)

    print()
    _print_summary(runs)

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps({"runs": runs}, indent=2), encoding="utf-8")
    print(f"\nFull details: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
