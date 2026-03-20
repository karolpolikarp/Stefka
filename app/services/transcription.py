import logging
import re
from pathlib import Path

import mlx_whisper

from app.config import WHISPER_MODEL

logger = logging.getLogger(__name__)


def transcribe_chunk(chunk_path: Path) -> str:
    """Transcribe a single audio chunk using mlx-whisper."""
    logger.debug("Transcribing chunk: %s", chunk_path.name)
    result = mlx_whisper.transcribe(
        str(chunk_path),
        path_or_hf_repo=WHISPER_MODEL,
        language="pl",
        verbose=False,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.0,
        no_speech_threshold=0.5,
    )
    text = result.get("text", "").strip()
    logger.debug("Chunk %s -> %d chars", chunk_path.name, len(text))
    return text


def transcribe_chunks(chunk_paths: list[Path], on_progress=None) -> str:
    """Transcribe all audio chunks and combine results.

    Args:
        chunk_paths: List of audio chunk file paths.
        on_progress: Optional callback(current, total) for progress reporting.

    Returns:
        Combined transcription text.
    """
    segments: list[str] = []
    total = len(chunk_paths)
    logger.info("Starting transcription of %d chunks", total)

    for i, chunk_path in enumerate(chunk_paths):
        text = transcribe_chunk(chunk_path)
        if text:
            # Deduplicate overlap with previous segment
            if segments:
                text = _remove_overlap(segments[-1], text)
            if text:
                segments.append(text)
        if on_progress:
            on_progress(i + 1, total)

    full_text = " ".join(segments)
    full_text = _clean_transcription(full_text)
    logger.info("Transcription complete: %d chunks -> %d chars", total, len(full_text))
    return full_text


def _remove_overlap(prev: str, current: str) -> str:
    """Remove overlapping text between consecutive chunks."""
    # Take last ~100 chars of previous segment, check if current starts with similar text
    tail = prev[-150:] if len(prev) > 150 else prev
    tail_words = tail.split()
    curr_words = current.split()

    # Try progressively shorter overlaps (from ~15 words down to 3)
    for overlap_len in range(min(15, len(tail_words), len(curr_words)), 2, -1):
        tail_end = " ".join(tail_words[-overlap_len:]).lower()
        curr_start = " ".join(curr_words[:overlap_len]).lower()
        if tail_end == curr_start:
            return " ".join(curr_words[overlap_len:])
    return current


def _clean_transcription(text: str) -> str:
    """Remove Whisper artifacts: repeated words, hallucinated filler."""
    # Collapse repeated words (e.g. "musimy musimy musimy ..." -> "musimy")
    text = re.sub(r'\b(\w+)(?:\s+\1){3,}\b', r'\1', text)
    # Collapse repeated short phrases (2-4 words repeated 3+ times)
    text = re.sub(r'((?:\S+\s+){1,4}\S+)(?:\s+\1){2,}', r'\1', text)
    # Remove common Whisper hallucinations on silence
    text = re.sub(r'(?:Dziękuję za oglądanie\.?\s*){2,}', '', text)
    text = re.sub(r'(?:Napisy stworzone przez społeczność.*?\.?\s*){1,}', '', text)
    text = re.sub(r'(?:Subskrybuj.*?\.?\s*){1,}', '', text)
    # Normalize whitespace
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()
