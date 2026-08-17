"""Domain model for the generation pipeline: output shape, real-time progress
reporting, and generation state (§21-§26, §31, §33)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OutputMode(Enum):
    SEPARATE_CHAPTERS = "separate_chapters"
    SINGLE_FILE = "single_file"


class OutputFormat(Enum):
    MP3 = "mp3"
    WAV = "wav"
    FLAC = "flac"


class GenerationState(Enum):
    PREPARING_TEXT = "preparing_text"
    GENERATING_AUDIO = "generating_audio"
    PROCESSING_CHAPTER = "processing_chapter"
    FINALIZING = "finalizing"
    COMPACTING = "compacting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class OutputSettings:
    mode: OutputMode = OutputMode.SEPARATE_CHAPTERS
    audio_format: OutputFormat = OutputFormat.MP3
    bitrate_kbps: int = 128


@dataclass
class GenerationProgress:
    state: GenerationState
    chapter_index: int
    chapter_count: int
    chapter_title: str
    chunk_index: int
    chunk_count: int
    elapsed_seconds: float
    fraction_complete: float
    estimated_remaining_seconds: float | None = None
