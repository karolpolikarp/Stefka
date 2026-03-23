import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

import mlx_whisper

from app.config import WHISPER_MODEL

logger = logging.getLogger(__name__)

# Common Whisper hallucinations on silence/noise (Polish and multilingual)
_HALLUCINATION_PATTERNS = [
    r'Dziękuję za oglądanie\.?',
    r'Dzięki za oglądanie\.?',
    r'Dziękuję za uwagę\.?',
    r'Dziękuję za obejrzenie\.?',
    r'Dziękuję za wysłuchanie\.?',
    r'Dziękuję\.?',
    r'Napisy stworzone przez społeczność[^.]*\.?',
    r'Napisy wykonał[^.]*\.?',
    r'Tłumaczenie[^.]*\.?',
    r'Subskrybuj[^.]*\.?',
    r'Do zobaczenia[^.]*\.?',
    r'Do usłyszenia[^.]*\.?',
    r'Zapraszam do subskrypcji[^.]*\.?',
    r'Proszę o subskrypcję[^.]*\.?',
    r'www\.\S+',
    r'Music',
    r'\[muzyka\]',
    r'\(muzyka\)',
    r'Podoba Ci się ten film\??',
    r'Zostaw łapkę[^.]*\.?',
]

# Compile once: each pattern repeated 2+ times in a row
_HALLUCINATION_BLOCK_RE = re.compile(
    '|'.join(rf'(?:{p}\s*){{2,}}' for p in _HALLUCINATION_PATTERNS),
    re.IGNORECASE,
)

# Single occurrence of pure filler hallucinations (these never appear in real speech)
_HALLUCINATION_SINGLE_RE = re.compile(
    r'(?:' + '|'.join([
        r'Napisy stworzone przez społeczność[^.]*\.?',
        r'Napisy wykonał[^.]*\.?',
        r'Subskrybuj[^.]*\.?',
        r'Zapraszam do subskrypcji[^.]*\.?',
        r'Proszę o subskrypcję[^.]*\.?',
        r'Dziękuję za oglądanie\.?',
        r'Dzięki za oglądanie\.?',
        r'Dziękuję za obejrzenie\.?',
        r'Podoba Ci się ten film\??',
        r'Zostaw łapkę[^.]*\.?',
        r'\[muzyka\]',
        r'\(muzyka\)',
    ]) + r')',
    re.IGNORECASE,
)


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
    # Early per-chunk cleaning — catch hallucinations before they merge
    text = _HALLUCINATION_SINGLE_RE.sub('', text).strip()
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
    full_text = _normalize_punctuation(full_text)
    logger.info("Transcription complete: %d chunks -> %d chars", total, len(full_text))
    return full_text


def _remove_overlap(prev: str, current: str) -> str:
    """Remove overlapping text between consecutive chunks.

    Uses both exact word matching and fuzzy matching (SequenceMatcher)
    to handle slight Whisper variations between overlapping audio.
    """
    tail = prev[-200:] if len(prev) > 200 else prev
    tail_words = tail.split()
    curr_words = current.split()

    if not tail_words or not curr_words:
        return current

    # Pass 1: exact word-level overlap (fast path)
    for overlap_len in range(min(20, len(tail_words), len(curr_words)), 2, -1):
        tail_end = " ".join(tail_words[-overlap_len:]).lower()
        curr_start = " ".join(curr_words[:overlap_len]).lower()
        if tail_end == curr_start:
            result = " ".join(curr_words[overlap_len:])
            logger.debug("Exact overlap removed: %d words", overlap_len)
            return result

    # Pass 2: fuzzy matching for Whisper transcription variations
    # Compare the tail of prev with the head of current at character level
    tail_text = " ".join(tail_words[-15:]).lower() if len(tail_words) >= 15 else tail.lower()

    # Build curr_head from first 20 words, but track its length in original string
    head_word_count = min(20, len(curr_words))
    curr_head_original = " ".join(curr_words[:head_word_count])
    curr_head = curr_head_original.lower()

    matcher = SequenceMatcher(None, tail_text, curr_head)
    match = matcher.find_longest_match(0, len(tail_text), 0, len(curr_head))

    # If a substantial overlap is found (>30 chars), trim it
    if match.size > 30:
        overlap_end_in_head = match.b + match.size
        # Map position from curr_head back to original current string
        # curr_head corresponds to first head_word_count words of current
        remaining = curr_head_original[overlap_end_in_head:]
        # If we truncated current to 20 words, append the rest
        if head_word_count < len(curr_words):
            remaining = remaining + " " + " ".join(curr_words[head_word_count:])
        # Find next word boundary to avoid cutting mid-word
        boundary = re.search(r'[\s]', remaining)
        if boundary:
            remaining = remaining[boundary.end():]
        if remaining.strip():
            logger.debug("Fuzzy overlap removed: %d chars matched", match.size)
            return remaining.strip()

    return current


def _clean_transcription(text: str) -> str:
    """Remove Whisper artifacts: repeated words, hallucinated filler."""
    # Remove blocks of repeated hallucinations
    text = _HALLUCINATION_BLOCK_RE.sub('', text)

    # Collapse repeated words (e.g. "musimy musimy musimy ..." -> "musimy")
    text = re.sub(r'\b(\w+)(?:\s+\1){2,}\b', r'\1', text)

    # Collapse repeated short phrases (2-5 words repeated 2+ times)
    text = re.sub(r'((?:\S+\s+){1,5}\S+)(?:\s+\1){2,}', r'\1', text)

    # Remove lone "Dziękuję." at end (common Whisper closing hallucination)
    text = re.sub(r'\s*Dziękuję\.\s*$', '', text)

    # Normalize whitespace
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def _normalize_punctuation(text: str) -> str:
    """Fix common punctuation issues from Whisper output."""
    # Fix missing space after period/question/exclamation
    text = re.sub(r'([.?!])([A-ZĄĆĘŁŃÓŚŹŻ])', r'\1 \2', text)

    # Fix double periods
    text = re.sub(r'\.{2,}', '.', text)

    # Fix space before period/comma
    text = re.sub(r'\s+([.,;:?!])', r'\1', text)

    # Fix missing space after comma
    text = re.sub(r',([a-ząćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ])', r', \1', text)

    # Collapse multiple consecutive sentence-ending punctuation
    text = re.sub(r'([.?!])\s*([.?!])+', r'\1', text)

    # Fix quotes — ensure space before opening and after closing
    text = re.sub(r'(?<=\S)"(?=\S)', ' "', text)

    return text.strip()
