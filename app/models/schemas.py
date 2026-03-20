from enum import Enum
from pydantic import BaseModel


class FileType(str, Enum):
    AUDIO = "audio"
    TEXT = "text"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    TRANSCRIBING = "transcribing"
    STRUCTURING = "structuring"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportFormat(str, Enum):
    MD = "md"
    PDF = "pdf"
    DOCX = "docx"


class JobInfo(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = 0  # 0-100
    message: str = ""
    file_type: FileType | None = None
    original_filename: str = ""
    export_format: str = "md"
    error: str | None = None


class UploadResponse(BaseModel):
    job_id: str
    message: str
