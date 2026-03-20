import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import JobInfo, JobStatus
from app.routers.upload import jobs

router = APIRouter(prefix="/api", tags=["status"])

SSE_MAX_ITERATIONS = 1200  # 10 minutes at 0.5s intervals
SSE_HEARTBEAT_INTERVAL = 30  # Send heartbeat every 30 iterations (~15s)


@router.get("/status/{job_id}")
async def get_status(job_id: str) -> JobInfo:
    """Get current job status."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nie znaleziony.")
    return job


@router.get("/status/{job_id}/stream")
async def stream_status(job_id: str):
    """SSE endpoint for real-time job progress updates."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nie znaleziony.")

    async def event_generator():
        last_progress = -1
        last_status = None
        iterations = 0

        while iterations < SSE_MAX_ITERATIONS:
            iterations += 1
            job = jobs.get(job_id)
            if not job:
                break

            if job.progress != last_progress or job.status != last_status:
                last_progress = job.progress
                last_status = job.status
                data = json.dumps(job.model_dump(), ensure_ascii=False)
                yield f"data: {data}\n\n"
            elif iterations % SSE_HEARTBEAT_INTERVAL == 0:
                yield ": heartbeat\n\n"

            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
