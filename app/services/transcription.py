import logging
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
            segments.append(text)
        if on_progress:
            on_progress(i + 1, total)

    full_text = " ".join(segments)
    logger.info("Transcription complete: %d chunks -> %d chars", total, len(full_text))
    return full_text
