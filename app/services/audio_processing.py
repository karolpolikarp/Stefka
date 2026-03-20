import logging
import subprocess
from pathlib import Path

from app.config import AUDIO_CHUNK_SECONDS, AUDIO_OVERLAP_SECONDS

logger = logging.getLogger(__name__)


def convert_to_wav_16k(input_path: Path, output_path: Path) -> Path:
    """Convert any audio file to WAV 16kHz mono using ffmpeg."""
    logger.info("Converting %s to WAV 16kHz", input_path.name)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg nie jest zainstalowany. Uruchom: brew install ffmpeg")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Konwersja audio nie powiodła się: {e.stderr[:500]}")
    return output_path


def get_audio_duration(file_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe nie jest zainstalowany. Uruchom: brew install ffmpeg")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Nie udało się odczytać długości audio: {e.stderr[:500]}")
    return float(result.stdout.strip())


def chunk_audio(wav_path: Path, output_dir: Path) -> list[Path]:
    """Split WAV file into chunks with overlap using ffmpeg.

    Returns list of chunk file paths in order.
    """
    duration = get_audio_duration(wav_path)
    logger.info("Audio duration: %.1fs, chunking with %ds segments (%ds overlap)", duration, AUDIO_CHUNK_SECONDS, AUDIO_OVERLAP_SECONDS)
    chunk_length = AUDIO_CHUNK_SECONDS
    overlap = AUDIO_OVERLAP_SECONDS
    step = chunk_length - overlap

    chunks: list[Path] = []
    start = 0.0
    idx = 0

    while start < duration:
        chunk_path = output_dir / f"chunk_{idx:04d}.wav"
        end = min(start + chunk_length, duration)

        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(wav_path),
                    "-ss", str(start),
                    "-t", str(end - start),
                    "-c:a", "pcm_s16le",
                    str(chunk_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Błąd podczas dzielenia audio (chunk {idx}): {e.stderr[:300]}")

        chunks.append(chunk_path)
        idx += 1
        start += step

    return chunks
