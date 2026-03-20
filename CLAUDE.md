# Stefka - Lokalna Aplikacja do Transkrypcji i Strukturyzowania Notatek

## Kontekst i Cel

Stefka to lokalna aplikacja webowa inspirowana [TurboScribe.ai](https://turboscribe.ai), zaprojektowana z naciskiem na **bezpieczeństwo i prywatność danych**. Wszystkie modele AI działają lokalnie na MacBooku użytkownika — żadne dane nie opuszczają maszyny.

Aplikacja przyjmuje pliki audio lub tekstowe i przetwarza je na ustandaryzowane notatki przy użyciu lokalnych modeli AI:
- **Whisper** (transkrypcja mowy na tekst)
- **PLLuM** (polski model językowy do strukturyzowania treści)

### Środowisko docelowe
- **MacBook M4 Pro, 48GB RAM**
- macOS (Apple Silicon)

---

## Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                      PRZEGLĄDARKA                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Upload pliku (audio/tekst) → Progress bar → Download │  │
│  └───────────────────────┬───────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────┼──────────────────────────────────┐
│                    FastAPI Backend                           │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │              Router: /api/upload                       │  │
│  │              Router: /api/status/{job_id}              │  │
│  │              Router: /api/download/{job_id}            │  │
│  └───────────┬────────────────────────────┬──────────────┘  │
│              │                            │                  │
│  ┌───────────▼──────────┐  ┌──────────────▼─────────────┐  │
│  │  Serwis Transkrypcji │  │     Serwis Eksportu        │  │
│  │  (mlx-whisper)       │  │  (MD / PDF / DOCX)         │  │
│  └───────────┬──────────┘  └──────────────▲─────────────┘  │
│              │                            │                  │
│  ┌───────────▼────────────────────────────┴─────────────┐  │
│  │              Serwis LLM (Ollama / PLLuM)             │  │
│  │              Strukturyzowanie notatki                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                    Lokalne Modele AI                         │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │  mlx-whisper         │  │  Ollama                     │  │
│  │  large-v3-turbo      │  │  PLLuM-12B-instruct         │  │
│  │  (natywne Apple Si.) │  │  (GGUF, ~13GB)              │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflow

### Workflow A: Plik Audio

```
Użytkownik wchodzi na stronę (localhost:8000)
        │
        ▼
Uploaduje plik audio (.mp3, .wav, .m4a, .flac, .ogg, .webm)
+ opcjonalnie podaje email
        │
        ▼
Backend waliduje plik (format, rozmiar)
        │
        ▼
Audio jest konwertowane do formatu WAV 16kHz mono (ffmpeg)
        │
        ▼
Audio jest dzielone na segmenty ~30s z 2s overlap (VAD-based)
        │
        ▼
Każdy segment transkrybowany przez mlx-whisper (large-v3-turbo)
        │
        ▼
Segmenty transkrypcji łączone w pełny tekst
        │
        ▼
Tekst transkrypcji → PLLuM (Ollama) z promptem strukturyzującym
        │
        ▼
PLLuM generuje ustandaryzowaną notatkę
        │
        ▼
Notatka eksportowana do wybranego formatu (MD / PDF / DOCX)
        │
        ▼
Użytkownik pobiera plik z przeglądarki
(lub otrzymuje na email — funkcja planowana)
```

### Workflow B: Plik Tekstowy

```
Użytkownik uploaduje plik tekstowy (.txt, .md, .docx, .pdf)
+ opcjonalnie podaje email
        │
        ▼
Backend waliduje i ekstrahuje tekst z pliku
        │
        ▼
Tekst → PLLuM (Ollama) z promptem strukturyzującym
        │
        ▼
PLLuM generuje ustandaryzowaną notatkę
        │
        ▼
Notatka eksportowana do wybranego formatu (MD / PDF / DOCX)
        │
        ▼
Użytkownik pobiera plik z przeglądarki
```

---

## Tech Stack

| Komponent | Technologia | Uzasadnienie |
|-----------|-------------|--------------|
| **Backend** | Python 3.11+ / FastAPI | Szybki, async, WebSocket/SSE support |
| **Transkrypcja** | mlx-whisper (large-v3-turbo) | Natywna optymalizacja Apple Silicon, 30-40% szybszy niż whisper.cpp |
| **LLM** | Ollama + PLLuM-12B-instruct | Łatwy deployment, 128K context window, ~13GB VRAM |
| **Audio processing** | pydub + ffmpeg | Konwersja formatów, chunking |
| **Frontend** | Vanilla HTML/CSS/JS + Jinja2 | Prostota, zero zależności frontendowych |
| **Eksport MD** | Natywny string | Bez zależności |
| **Eksport PDF** | weasyprint | Konwersja HTML/CSS → PDF |
| **Eksport DOCX** | python-docx | Generowanie dokumentów Word |
| **Ekstrakcja tekstu** | python-docx, PyPDF2 | Odczyt uploadowanych plików tekstowych |
| **Task queue** | asyncio + background tasks | Przetwarzanie w tle z raportowaniem postępu |

### Dobór modeli AI

**Transkrypcja: mlx-whisper z modelem large-v3-turbo**
- Model: `mlx-community/whisper-large-v3-turbo` (~809M parametrów)
- Zoptymalizowany pod Apple Silicon (MLX framework)
- Na M4 Pro: ~10-15x szybciej niż real-time
- Dokładność porównywalna z large-v3, 6x szybszy
- Obsługuje 98+ języków, w tym polski

**LLM: PLLuM-12B-instruct via Ollama**
- Model: `PRIHLOP/PLLuM:12b` (~13GB)
- Specjalizowany w języku polskim (150B tokenów polskich)
- 128K token context window
- Instruction-tuned — idealny do zadań strukturyzowania
- Przy 48GB RAM: komfortowe działanie z zapasem na Whisper

### Wymagania sprzętowe (estymacja dla M4 Pro 48GB)

| Model | RAM/VRAM | Uwagi |
|-------|----------|-------|
| mlx-whisper large-v3-turbo | ~3-4 GB | Załadowany w czasie transkrypcji |
| PLLuM-12B-instruct (Q8) | ~13 GB | Ollama zarządza pamięcią |
| System + FastAPI | ~4-6 GB | macOS + Python runtime |
| **Razem** | **~20-23 GB** | Duży zapas przy 48GB |

---

## Struktura Projektu

```
stefka/
├── CLAUDE.md                     # Ten plik — dokumentacja projektu
├── requirements.txt              # Zależności Python
├── setup.sh                      # Skrypt instalacyjny (Ollama, modele, ffmpeg)
├── run.sh                        # Skrypt uruchomieniowy
│
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI — punkt wejścia, montowanie routerów
│   ├── config.py                 # Konfiguracja (ścieżki, modele, porty)
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── upload.py             # POST /api/upload — przyjmowanie plików
│   │   ├── status.py             # GET /api/status/{job_id} — SSE progress
│   │   └── download.py           # GET /api/download/{job_id} — pobieranie notatki
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── transcription.py      # Transkrypcja audio via mlx-whisper
│   │   ├── audio_processing.py   # Konwersja audio, chunking, VAD
│   │   ├── text_extraction.py    # Ekstrakcja tekstu z DOCX/PDF/TXT/MD
│   │   ├── llm.py                # Integracja z Ollama/PLLuM
│   │   ├── note_formatter.py     # Prompt engineering + formatowanie notatki
│   │   └── export.py             # Eksport do MD/PDF/DOCX
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py            # Pydantic modele (UploadRequest, JobStatus, etc.)
│   │
│   ├── templates/
│   │   └── index.html            # Główna strona — upload + progress + download
│   │
│   └── static/
│       ├── css/
│       │   └── style.css         # Style aplikacji
│       └── js/
│           └── app.js            # Logika frontendu (upload, SSE, download)
│
├── data/
│   ├── uploads/                  # Tymczasowe pliki uploadowane (czyszczone po przetworzeniu)
│   └── outputs/                  # Wygenerowane notatki (czyszczone okresowo)
│
└── tests/
    ├── __init__.py
    ├── test_transcription.py
    ├── test_llm.py
    ├── test_export.py
    └── test_api.py
```

---

## Kluczowe Decyzje Projektowe

### 1. Bezpieczeństwo danych (priorytet #1)
- **Zero komunikacji z zewnętrznymi API** — wszystkie modele lokalne
- Pliki tymczasowe usuwane po przetworzeniu
- Brak logowania treści przetwarzanych plików
- Aplikacja dostępna tylko z localhost

### 2. mlx-whisper zamiast faster-whisper
- faster-whisper (CTranslate2) **nie obsługuje GPU na Apple Silicon** — fallback na CPU
- mlx-whisper natywnie wykorzystuje GPU M4 Pro — **30-40% szybszy**
- Prostsze API, mniej zależności

### 3. Ollama jako runtime dla PLLuM
- Zarządza pamięcią modelu automatycznie
- Obsługuje quantyzację GGUF
- Prosty HTTP API (localhost:11434)
- Łatwy setup: `ollama pull PRIHLOP/PLLuM:12b`

### 4. SSE zamiast WebSocket do raportowania postępu
- Prostsze w implementacji (jednostronna komunikacja)
- Natywne wsparcie w przeglądarkach (EventSource API)
- Wystarczające dla naszego use case (serwer → klient)

### 5. Background tasks zamiast Celery
- Brak potrzeby Redis/RabbitMQ — mniejsza złożoność
- asyncio + FastAPI BackgroundTasks wystarczają
- Jeden użytkownik na raz — nie potrzebujemy kolejki zadań

---

## Prompt PLLuM — Strukturyzowanie Notatki

```
Jesteś asystentem specjalizującym się w tworzeniu ustandaryzowanych notatek.
Na podstawie poniższego tekstu stwórz strukturalną notatkę w następującym formacie:

## Tytuł
[Automatycznie wygenerowany tytuł na podstawie treści]

## Data
[Data przetworzenia]

## Podsumowanie
[2-3 zdania podsumowujące kluczowe punkty]

## Kluczowe Punkty
- [Punkt 1]
- [Punkt 2]
- [...]

## Szczegółowa Treść
[Pełna, uporządkowana treść z zachowaniem struktury logicznej.
Podzielona na sekcje tematyczne jeśli to uzasadnione.]

## Wnioski / Następne Kroki
[Jeśli wynikają z treści — wnioski, rekomendacje lub dalsze kroki]

---

Tekst źródłowy:
{transcription_or_text}
```

---

## Zależności (requirements.txt)

```
# Backend
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
python-multipart>=0.0.12
jinja2>=3.1.4
aiofiles>=24.1.0

# Transkrypcja
mlx-whisper>=0.4.0

# Audio processing
pydub>=0.25.1

# LLM
httpx>=0.27.0

# Eksport
python-docx>=1.1.0
weasyprint>=62.0
markdown>=3.7

# Ekstrakcja tekstu
PyPDF2>=3.0.0

# Utilities
uuid6>=2024.7.10
```

---

## Setup i Uruchomienie

### Wymagania wstępne
- macOS z Apple Silicon (M1/M2/M3/M4)
- Python 3.11+
- Homebrew

### Instalacja

```bash
# 1. Zainstaluj zależności systemowe
brew install ffmpeg ollama

# 2. Uruchom Ollama i pobierz model PLLuM
ollama serve &
ollama pull PRIHLOP/PLLuM:12b

# 3. Utwórz środowisko Python
python3 -m venv .venv
source .venv/bin/activate

# 4. Zainstaluj zależności Python
pip install -r requirements.txt

# 5. Uruchom aplikację
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Uruchomienie (po instalacji)

```bash
# Terminal 1: Ollama (jeśli nie działa jako daemon)
ollama serve

# Terminal 2: Aplikacja
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Aplikacja dostępna pod: **http://localhost:8000**

---

## Formaty plików

### Obsługiwane pliki wejściowe

| Typ | Formaty |
|-----|---------|
| Audio | .mp3, .wav, .m4a, .flac, .ogg, .webm, .wma, .aac |
| Tekst | .txt, .md, .docx, .pdf |

### Formaty wyjściowe notatek
- **Markdown** (.md) — lekki, czytelny
- **PDF** (.pdf) — gotowy do druku
- **DOCX** (.docx) — edytowalny w Word

---

## Planowane rozszerzenia (v2)
- Wysyłka notatki na email (SMTP)
- Detekcja mówców (speaker diarization)
- Historia przetworzonych plików
- Redukcja szumu audio
- Batch processing (wiele plików naraz)
- Wybór języka transkrypcji
