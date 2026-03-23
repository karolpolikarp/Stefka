import asyncio
import logging
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.config import (
    ALLOWED_EXTENSIONS,
    AUDIO_EXTENSIONS,
    TEXT_EXTENSIONS,
    MAX_UPLOAD_SIZE_MB,
    UPLOAD_DIR,
    OUTPUT_DIR,
)
from app.models.schemas import (
    ExportFormat,
    FileType,
    JobInfo,
    JobStatus,
    UploadResponse,
)
from app.services.audio_processing import chunk_audio, convert_to_wav_16k
from app.services.export import export_note
from app.services.llm import check_ollama_health, structure_note
from app.services.text_extraction import extract_text
from app.services.transcription import transcribe_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])

# In-memory job store with timestamps for cleanup
jobs: dict[str, JobInfo] = {}
_job_timestamps: dict[str, float] = {}

JOB_TTL_SECONDS = 3600  # clean up jobs older than 1 hour
OUTPUT_TTL_SECONDS = 86400  # clean up output files older than 24 hours


def _update_job(job_id: str, **kwargs):
    if job_id in jobs:
        for k, v in kwargs.items():
            setattr(jobs[job_id], k, v)


def _cleanup_old_jobs():
    """Remove completed/failed jobs older than TTL."""
    now = time.time()
    expired = [
        jid for jid, ts in _job_timestamps.items()
        if now - ts > JOB_TTL_SECONDS and jid in jobs
        and jobs[jid].status in (JobStatus.COMPLETED, JobStatus.FAILED)
    ]
    for jid in expired:
        jobs.pop(jid, None)
        _job_timestamps.pop(jid, None)
    if expired:
        logger.info("Cleaned up %d expired jobs", len(expired))


def _cleanup_old_outputs():
    """Remove output files older than TTL."""
    now = time.time()
    removed = 0
    for f in OUTPUT_DIR.iterdir():
        if f.is_file() and now - f.stat().st_mtime > OUTPUT_TTL_SECONDS:
            f.unlink()
            removed += 1
    if removed:
        logger.info("Cleaned up %d old output files", removed)


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    export_format: ExportFormat = Form(ExportFormat.MD),
    email: str = Form(""),
):
    # Periodic cleanup on each upload
    _cleanup_old_jobs()
    _cleanup_old_outputs()

    # Check Ollama health before accepting file
    if not await check_ollama_health():
        raise HTTPException(
            status_code=503,
            detail="Ollama nie jest dostępna lub model PLLuM nie jest załadowany. "
            "Uruchom: ollama serve && ollama pull pllum-12b-instruct",
        )

    # Validate extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Nieobsługiwany format pliku: {suffix}. "
            f"Dozwolone: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Validate file size before writing
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"Plik przekracza limit {MAX_UPLOAD_SIZE_MB} MB.",
        )

    # Create job
    job_id = uuid.uuid4().hex[:12]
    file_type = FileType.AUDIO if suffix in AUDIO_EXTENSIONS else FileType.TEXT

    _job_timestamps[job_id] = time.time()
    jobs[job_id] = JobInfo(
        job_id=job_id,
        status=JobStatus.PENDING,
        progress=0,
        message="Plik przyjęty, oczekuje na przetworzenie...",
        file_type=file_type,
        original_filename=file.filename or "unknown",
        export_format=export_format.value,
    )

    # Save uploaded file
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    upload_path = job_dir / f"input{suffix}"
    upload_path.write_bytes(content)

    logger.info("Job %s: uploaded %s (%d bytes, format=%s)", job_id, file.filename, len(content), export_format.value)

    # Process in background
    asyncio.create_task(_process_job(job_id, upload_path, file_type, export_format.value))

    return UploadResponse(job_id=job_id, message="Plik przyjęty do przetworzenia.")


async def _process_job(job_id: str, file_path: Path, file_type: FileType, export_format: str):
    """Background task to process uploaded file."""
    try:
        if file_type == FileType.AUDIO:
            await _process_audio(job_id, file_path, export_format)
        else:
            await _process_text(job_id, file_path, export_format)
    except Exception as e:
        logger.exception("Job %s failed", job_id)
        _update_job(
            job_id,
            status=JobStatus.FAILED,
            error=str(e),
            message=f"Błąd przetwarzania: {e}",
        )
    finally:
        # Clean up uploaded file (processing is done at this point)
        job_dir = file_path.parent
        shutil.rmtree(job_dir, ignore_errors=True)


async def _process_audio(job_id: str, file_path: Path, export_format: str):
    """Process audio file: convert -> chunk -> transcribe -> structure -> export."""
    # Step 1: Convert to WAV
    _update_job(
        job_id,
        status=JobStatus.PROCESSING,
        progress=5,
        message="Konwersja audio do WAV 16kHz...",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        wav_path = tmp_path / "audio.wav"

        await asyncio.to_thread(convert_to_wav_16k, file_path, wav_path)

        # Step 2: Chunk audio
        _update_job(
            job_id,
            progress=10,
            message="Dzielenie audio na segmenty...",
        )
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        chunks = await asyncio.to_thread(chunk_audio, wav_path, chunks_dir)

        if not chunks:
            raise RuntimeError("Nie udało się podzielić audio na segmenty.")

        # Step 3: Transcribe
        _update_job(
            job_id,
            status=JobStatus.TRANSCRIBING,
            progress=15,
            message=f"Transkrypcja (0/{len(chunks)} segmentów)...",
        )

        def on_transcription_progress(current, total):
            pct = 15 + int((current / total) * 55)  # 15-70%
            _update_job(
                job_id,
                progress=pct,
                message=f"Transkrypcja ({current}/{total} segmentów)...",
            )

        transcription = await asyncio.to_thread(
            transcribe_chunks, chunks, on_transcription_progress
        )

    if not transcription.strip():
        _update_job(
            job_id,
            status=JobStatus.FAILED,
            error="Transkrypcja jest pusta — plik audio może nie zawierać mowy.",
            message="Transkrypcja nie powiodła się.",
        )
        return

    # Save transcription for debugging
    debug_path = OUTPUT_DIR / f"{job_id}_transcription.txt"
    debug_path.write_text(transcription, encoding="utf-8")
    logger.info("Job %s: saved transcription to %s (%d chars)", job_id, debug_path.name, len(transcription))

    # Step 4: Structure with PLLuM
    def on_llm_progress(message: str):
        _update_job(job_id, status=JobStatus.STRUCTURING, progress=80, message=message)

    _update_job(
        job_id,
        status=JobStatus.STRUCTURING,
        progress=75,
        message="PLLuM strukturyzuje notatkę...",
    )
    note = await structure_note(transcription, on_progress=on_llm_progress)

    # Step 5: Export
    _update_job(
        job_id,
        status=JobStatus.EXPORTING,
        progress=90,
        message="Eksportowanie notatki...",
    )
    output_path = OUTPUT_DIR / f"{job_id}_notatka"
    result_path = await asyncio.to_thread(export_note, note, output_path, export_format)

    logger.info("Job %s: completed -> %s", job_id, result_path.name)
    _update_job(
        job_id,
        status=JobStatus.COMPLETED,
        progress=100,
        message=f"Gotowe! Notatka: {result_path.name}",
    )


async def _process_text(job_id: str, file_path: Path, export_format: str):
    """Process text file: extract -> structure -> export."""
    # Step 1: Extract text
    _update_job(
        job_id,
        status=JobStatus.PROCESSING,
        progress=10,
        message="Ekstrakcja tekstu z pliku...",
    )
    text = await asyncio.to_thread(extract_text, file_path)

    if not text.strip():
        _update_job(
            job_id,
            status=JobStatus.FAILED,
            error="Plik nie zawiera tekstu.",
            message="Ekstrakcja tekstu nie powiodła się.",
        )
        return

    # Step 2: Structure with PLLuM
    def on_llm_progress(message: str):
        _update_job(job_id, status=JobStatus.STRUCTURING, progress=50, message=message)

    _update_job(
        job_id,
        status=JobStatus.STRUCTURING,
        progress=30,
        message="PLLuM strukturyzuje notatkę...",
    )
    note = await structure_note(text, on_progress=on_llm_progress)

    # Step 3: Export
    _update_job(
        job_id,
        status=JobStatus.EXPORTING,
        progress=85,
        message="Eksportowanie notatki...",
    )
    output_path = OUTPUT_DIR / f"{job_id}_notatka"
    result_path = await asyncio.to_thread(export_note, note, output_path, export_format)

    logger.info("Job %s: completed -> %s", job_id, result_path.name)
    _update_job(
        job_id,
        status=JobStatus.COMPLETED,
        progress=100,
        message=f"Gotowe! Notatka: {result_path.name}",
    )
