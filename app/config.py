from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
OUTPUT_DIR = BASE_DIR / "data" / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Ollama / PLLuM
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "PRIHLOP/PLLuM:12b"

# mlx-whisper
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

# Limity
MAX_UPLOAD_SIZE_MB = 500
AUDIO_CHUNK_SECONDS = 30
AUDIO_OVERLAP_SECONDS = 2

# Obsługiwane formaty
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm", ".wma", ".aac"}
TEXT_EXTENSIONS = {".txt", ".md", ".docx", ".pdf"}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | TEXT_EXTENSIONS

# Eksport
EXPORT_FORMATS = {"md", "pdf", "docx"}

# Logowanie
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "juliusz.log"
