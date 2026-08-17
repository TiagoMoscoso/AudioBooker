"""AudioPostProcessor (§29): concatenates narrated chunks into chapters/whole
book with natural, boundary-aware pauses (§ pausas inteligentes), trims/fades
each chunk's edges to avoid clicks at the joins (infrastructure.audio.
assembly), and encodes to the final output format via ffmpeg. Loudness
mastering (infrastructure.audio.mastering.LoudnessMaster) is applied by
GenerateAudiobookService as a whole-book pass, not per-chapter here — see
its docstring for why. ffmpeg is resolved from the system PATH first,
falling back to the prebuilt binary bundled through imageio-ffmpeg, so end
users never have to install ffmpeg manually (§29)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from domain.generation import OutputFormat
from i18n import tr
from infrastructure.audio.assembly import apply_edge_fade, trim_silence

# Pause durations (§22), a starting point meant to be tuned after auditory
# testing. Selected per chunk by its ChunkBoundary (services.narration_chunker)
# — see GenerateAudiobookService._finalize, which builds the pauses_ms list
# `concatenate` below accepts.
CHUNK_PAUSE_MS = 180
PARAGRAPH_PAUSE_MS = 450
SCENE_BREAK_PAUSE_MS = 900
CHAPTER_PAUSE_MS = 1500


def _ffmpeg_path() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class AudioPostProcessor:
    def concatenate(
        self,
        chunk_paths: list[Path],
        sample_rate: int,
        pause_ms: int = CHUNK_PAUSE_MS,
        pauses_ms: list[int] | None = None,
    ) -> np.ndarray:
        """Concatenates a chapter's chunk WAVs, trimming/fading each chunk's
        edges first to avoid clicks at the join. `pauses_ms`, when given,
        must have length `len(chunk_paths) - 1` and gives the pause before
        each chunk after the first (its boundary-aware replacement for the
        flat `pause_ms`); omitting it preserves the previous flat-pause
        behavior exactly."""
        if pauses_ms is not None and len(pauses_ms) != max(0, len(chunk_paths) - 1):
            raise ValueError(
                tr(
                    "error.pauses_length_mismatch",
                    expected=max(0, len(chunk_paths) - 1),
                    actual=len(pauses_ms),
                )
            )

        pieces: list[np.ndarray] = []
        for i, path in enumerate(chunk_paths):
            data, sr = sf.read(str(path), dtype="float32")
            if sr != sample_rate:
                raise ValueError(
                    tr("error.sample_rate_mismatch", path=path, expected=sample_rate, actual=sr)
                )
            if data.ndim > 1:
                data = data.mean(axis=1)
            data = trim_silence(data, sample_rate)
            data = apply_edge_fade(data, sample_rate)
            if i > 0:
                gap_ms = pauses_ms[i - 1] if pauses_ms is not None else pause_ms
                pieces.append(np.zeros(int(sample_rate * gap_ms / 1000), dtype=np.float32))
            pieces.append(data)
        if not pieces:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(pieces)

    def concatenate_with_pauses(
        self, wav_paths: list[Path], sample_rate: int, pause_ms: int = CHAPTER_PAUSE_MS
    ) -> np.ndarray:
        """Concatenates already-finalized WAVs (e.g. one per chapter) with a
        pause between each, without re-normalizing each piece — used to build
        a single combined file out of separately-encoded chapters, both at
        generation time and at on-demand export time."""
        pause = np.zeros(int(sample_rate * pause_ms / 1000), dtype=np.float32)
        pieces: list[np.ndarray] = []
        for i, path in enumerate(wav_paths):
            data, _ = sf.read(str(path), dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)
            if i > 0:
                pieces.append(pause)
            pieces.append(data)
        return np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)

    def write_wav(self, samples: np.ndarray, sample_rate: int, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), samples, sample_rate)

    def write_flac(self, samples: np.ndarray, sample_rate: int, path: Path) -> None:
        """Writes a permanent lossless chapter master (§ um único encode
        final): soundfile encodes FLAC natively, no ffmpeg subprocess
        needed. Kept as a distinct, correctly-named method from write_wav
        even though both ultimately call sf.write — the extension alone
        picking the codec would be an easy detail to get wrong later."""
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), samples, sample_rate, format="FLAC")

    def encode(
        self,
        wav_path: Path,
        output_path: Path,
        output_format: OutputFormat,
        bitrate_kbps: int = 128,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_format == OutputFormat.WAV:
            shutil.copyfile(wav_path, output_path)
            return

        args = [_ffmpeg_path(), "-y", "-i", str(wav_path), "-ac", "1"]
        if output_format == OutputFormat.MP3:
            args += ["-codec:a", "libmp3lame", "-b:a", f"{bitrate_kbps}k"]
        elif output_format == OutputFormat.FLAC:
            args += ["-codec:a", "flac"]
        args.append(str(output_path))

        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(tr("error.audio_encode_failed", detail=result.stderr[-500:]))

    def decode_to_wav(self, input_path: Path, output_wav_path: Path) -> None:
        """Decodes an already-encoded audio file (e.g. a library chapter
        stored as MP3) back to WAV, so it can be concatenated with
        soundfile/numpy — used only when exporting a combined single-file
        ZIP out of separately-encoded chapter files (§ export)."""
        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        args = [_ffmpeg_path(), "-y", "-i", str(input_path), str(output_wav_path)]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(tr("error.audio_decode_failed", detail=result.stderr[-500:]))
