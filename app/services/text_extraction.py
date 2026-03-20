from pathlib import Path

import docx
import PyPDF2


def extract_text(file_path: Path) -> str:
    """Extract text content from supported file formats."""
    suffix = file_path.suffix.lower()

    if suffix in (".txt", ".md"):
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="latin-1")

    if suffix == ".docx":
        return _extract_docx(file_path)

    if suffix == ".pdf":
        return _extract_pdf(file_path)

    raise ValueError(f"Nieobsługiwany format tekstowy: {suffix}")


def _extract_docx(file_path: Path) -> str:
    try:
        doc = docx.Document(str(file_path))
    except Exception as e:
        raise ValueError(f"Nie udało się otworzyć pliku DOCX: {e}")
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_pdf(file_path: Path) -> str:
    try:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as e:
        raise ValueError(f"Nie udało się otworzyć pliku PDF: {e}")
    return "\n\n".join(p.strip() for p in pages if p.strip())
