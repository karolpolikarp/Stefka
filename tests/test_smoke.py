"""Smoke testy — czysta logika, bez Ollamy i bez mlx-whisper.

Uruchomienie:
    pip install -r requirements-dev.txt
    pytest
"""

from app import config
from app.services import llm


# --- config ---------------------------------------------------------------

def test_allowed_extensions_is_union():
    assert config.ALLOWED_EXTENSIONS == config.AUDIO_EXTENSIONS | config.TEXT_EXTENSIONS
    assert ".mp3" in config.AUDIO_EXTENSIONS
    assert ".pdf" in config.TEXT_EXTENSIONS


def test_limits_and_formats():
    assert config.MAX_UPLOAD_SIZE_MB > 0
    assert config.EXPORT_FORMATS == {"md", "pdf", "docx"}


# --- chunkowanie ----------------------------------------------------------

def test_short_text_single_chunk():
    assert llm._split_into_chunks("Krótki tekst.", llm.CHUNK_SIZE) == ["Krótki tekst."]


def test_long_text_splits_into_multiple_chunks():
    text = ("To jest zdanie testowe. " * 600)  # ~ 14k znaków
    chunks = llm._split_into_chunks(text, llm.CHUNK_SIZE)
    assert len(chunks) > 1
    assert all(len(c) <= llm.CHUNK_SIZE + len("To jest zdanie testowe. ") for c in chunks)


# --- detekcja zdegenerowanego outputu ------------------------------------

def test_is_garbage_detects_repeated_lines():
    assert llm._is_garbage("\n".join(["to samo zdanie"] * 6)) is True


def test_is_garbage_detects_char_run():
    assert llm._is_garbage("aaaaaaaaaaaaaaaaaaaaaaaaa") is True


def test_normal_text_is_not_garbage():
    assert llm._is_garbage("Spotkanie dotyczyło budżetu. Omówiono harmonogram prac.") is False


# --- wykrywanie kopiowania surowego tekstu --------------------------------

def test_overlap_ratio_high_for_verbatim_copy():
    src = "Ala ma kota i psa. " * 20
    assert llm._text_overlap_ratio(src, src) > 0.9


def test_overlap_ratio_zero_for_short_output():
    assert llm._text_overlap_ratio("dowolne źródło", "krótki") == 0.0


# --- składanie noty -------------------------------------------------------

def test_assemble_note_has_header():
    note = llm._assemble_note(["Pierwszy akapit streszczenia spotkania o budżecie."])
    assert "NOTATKA SŁUŻBOWA" in note
    assert "Data przetworzenia" in note
