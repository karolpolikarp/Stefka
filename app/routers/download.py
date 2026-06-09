from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR, EXPORT_FORMATS
from app.models.schemas import JobStatus
from app.routers.upload import jobs

router = APIRouter(prefix="/api", tags=["download"])


@router.get("/download/{job_id}")
async def download_note(job_id: str, fmt: str | None = None):
    """Download the generated note file.

    If fmt is not specified, uses the format chosen during upload.
    """
    # Validate job_id format (alphanumeric, max 12 chars)
    if not job_id.isalnum() or len(job_id) > 12:
        raise HTTPException(status_code=400, detail="Nieprawidłowy identyfikator.")

    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nie znaleziony.")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job nie jest jeszcze ukończony.")

    # Use the format from upload if not explicitly requested
    fmt = fmt or job.export_format
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Nieobsługiwany format: {fmt}. Dozwolone: {', '.join(EXPORT_FORMATS)}",
        )

    file_path = (OUTPUT_DIR / f"{job_id}_notatka.{fmt}").resolve()
    if not file_path.is_relative_to(OUTPUT_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Nieprawidłowa ścieżka pliku.")
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Plik wyniku w formacie .{fmt} nie znaleziony. "
            f"Wynik został wyeksportowany jako .{job.export_format}.",
        )

    safe_name = Path(job.original_filename).stem if job.original_filename else "wynik"
    download_name = f"{safe_name}_tresc.{fmt}"

    media_types = {
        "md": "text/markdown",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    return FileResponse(
        path=str(file_path),
        filename=download_name,
        media_type=media_types.get(fmt, "application/octet-stream"),
    )
