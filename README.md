# Stefka

**Lokalna aplikacja do transkrypcji audio i strukturyzowania treści**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![mlx-whisper](https://img.shields.io/badge/mlx--whisper-large--v3--turbo-FF6F00?logo=apple&logoColor=white)](https://github.com/ml-explore/mlx-examples)
[![PLLuM](https://img.shields.io/badge/PLLuM-12B--instruct-1E88E5)](https://huggingface.co/CYFRAGOVPL/PLLuM-12B-nc-instruct)

Stefka przetwarza pliki audio i tekstowe na uporządkowane, ustrukturyzowane treści. Wszystkie modele AI działają lokalnie — żadne dane nie opuszczają maszyny użytkownika.

> ℹ️ **Charakter projektu:** to prototyp / dowód koncepcji zbudowany w kilka godzin, a nie produkcyjny system. Działa i realizuje pełny pipeline (transkrypcja → strukturyzacja → eksport), ale ma świadome ograniczenia: jeden użytkownik na raz, brak kolejki zadań, niestabilna jakość outputu modelu 12B (szczegóły w sekcji *Znane ograniczenia*).

<!-- screenshot -->

---

## Funkcjonalności

- **Pełna prywatność danych** — zero komunikacji z zewnętrznymi API, całe przetwarzanie na localhost
- **Transkrypcja audio** — mlx-whisper zoptymalizowany pod Apple Silicon (10–15x szybciej niż real-time na M4 Pro)
- **Strukturyzowanie tekstu** — polski model językowy PLLuM-12B porządkuje i strukturyzuje treść
- **Przetwarzanie plików tekstowych** — import z TXT, MD, DOCX, PDF
- **Eksport wieloformatowy** — zapis wyniku do Markdown, PDF lub DOCX
- **Interfejs webowy** — prosta strona z uploadem, paskiem postępu (SSE) i pobieraniem wyniku
- **Automatyczne czyszczenie** — pliki tymczasowe usuwane po przetworzeniu, wyniki po 24h

---

## Architektura

```
+---------------------------------------------------------+
|                     PRZEGLĄDARKA                        |
|   Upload pliku (audio/tekst) -> Progress bar -> Download |
+----------------------------+----------------------------+
                             | HTTP / SSE
+----------------------------+----------------------------+
|                     FastAPI Backend                      |
|                                                         |
|   /api/upload          /api/status/{id}   /api/download |
|         |                                      ^        |
|   +-----v-----------+   +---------------------+--+     |
|   | Transkrypcja     |   | Eksport               |     |
|   | (mlx-whisper)    |   | (MD / PDF / DOCX)     |     |
|   +-----+------------+   +-----^-----------------+     |
|         |                      |                        |
|   +-----v----------------------+--+                     |
|   | Serwis LLM (Ollama / PLLuM)   |                    |
|   | chunk-summarize pipeline       |                    |
|   +--------------------------------+                    |
+---------------------------------------------------------+
                             |
+---------------------------------------------------------+
|                  Lokalne Modele AI                       |
|   mlx-whisper              Ollama                       |
|   large-v3-turbo           PLLuM-12B-instruct           |
|   (~809M param.)           (GGUF Q8, ~13GB)             |
+---------------------------------------------------------+
```

---

## Stos technologiczny

| Komponent | Technologia | Uwagi |
|---|---|---|
| Backend | Python 3.11+ / FastAPI | Async, SSE do raportowania postępu |
| Transkrypcja | mlx-whisper (large-v3-turbo) | Natywna akceleracja GPU na Apple Silicon |
| Model językowy | PLLuM-12B-nc-instruct via Ollama | Oficjalny model z CYFRAGOVPL/HuggingFace, GGUF Q8 |
| Przetwarzanie audio | ffmpeg + pydub | Konwersja do WAV 16kHz, dzielenie na segmenty |
| Eksport PDF | WeasyPrint | Konwersja HTML/CSS na PDF |
| Eksport DOCX | python-docx | Generowanie dokumentów Word z zachowaniem formatowania |
| Ekstrakcja tekstu | PyPDF2, python-docx | Odczyt uploadowanych PDF i DOCX |
| Frontend | Vanilla HTML/CSS/JS + Jinja2 | Zero zależności frontendowych |

### Wymagania sprzętowe

| Komponent | RAM | Uwagi |
|---|---|---|
| mlx-whisper large-v3-turbo | ~3-4 GB | Ładowany na czas transkrypcji |
| PLLuM-12B-instruct (Q8) | ~13 GB | Ollama zarządza pamięcią |
| System + FastAPI | ~4-6 GB | macOS + Python runtime |
| **Łącznie** | **~20-23 GB** | Komfortowo przy 48 GB RAM |

---

## Szybki start

### Wymagania wstępne

- macOS z Apple Silicon (M1 / M2 / M3 / M4)
- Python 3.11+
- [Homebrew](https://brew.sh)
- Min. 32 GB RAM (zalecane 48 GB)
- ~20 GB wolnego miejsca na dysku (modele AI)

### Instalacja

```bash
git clone <repo-url> stefka
cd stefka
chmod +x setup.sh run.sh
./setup.sh
```

Skrypt `setup.sh` automatycznie:

1. Sprawdza i instaluje zależności systemowe (ffmpeg, Ollama, pango, llama.cpp)
2. Tworzy środowisko wirtualne Python i instaluje zależności
3. Pobiera oficjalny model PLLuM-12B-nc-instruct z [CYFRAGOVPL/HuggingFace](https://huggingface.co/CYFRAGOVPL/PLLuM-12B-nc-instruct)
4. Konwertuje model do formatu GGUF Q8_0 i importuje do Ollama

Pierwsze uruchomienie `setup.sh` może potrwać kilkanaście minut (pobranie ~24 GB + konwersja modelu).

### Uruchomienie

```bash
./run.sh
```

Aplikacja dostępna pod: **http://localhost:8000**

Skrypt `run.sh` uruchamia Ollama (jeśli nie działa) oraz serwer FastAPI na porcie 8000. Aplikacja nasłuchuje wyłącznie na `127.0.0.1` — nie jest dostępna z sieci.

---

## Jak to działa

### Workflow A: Plik audio

```
Upload audio (.mp3, .wav, .m4a, ...)
    |
    v
Walidacja formatu i rozmiaru (max 500 MB)
    |
    v
Konwersja do WAV 16kHz mono (ffmpeg)
    |
    v
Dzielenie na segmenty ~30s z 2s overlap
    |
    v
Transkrypcja każdego segmentu (mlx-whisper)
  + usuwanie halucynacji Whisper
  + deduplikacja overlappującego tekstu
    |
    v
Strukturyzowanie przez PLLuM (chunk-summarize)
    |
    v
Eksport do wybranego formatu (MD / PDF / DOCX)
    |
    v
Pobranie wyniku z przeglądarki
```

### Workflow B: Plik tekstowy

```
Upload tekstu (.txt, .md, .docx, .pdf)
    |
    v
Ekstrakcja tekstu z pliku
    |
    v
Strukturyzowanie przez PLLuM (chunk-summarize)
    |
    v
Eksport do wybranego formatu
    |
    v
Pobranie wyniku z przeglądarki
```

---

## Pipeline LLM

Stefka używa podejścia **chunk-summarize** do przetwarzania tekstu przez PLLuM-12B:

### Dzielenie na fragmenty

Tekst wejściowy jest dzielony na fragmenty po ~6000 znaków (`CHUNK_SIZE`) z 400-znakowym nakładaniem (`CHUNK_OVERLAP`). Cięcie odbywa się na granicach zdań. Ostatni fragment, jeśli jest krótszy niż 40% docelowego rozmiaru, jest łączony z poprzednim.

### Streszczanie fragmentów

Każdy fragment jest przetwarzany osobno przez PLLuM z promptem systemowym:

> *Streść poniższy fragment spotkania w akapitach. Zachowaj imiona, nazwiska, daty, kwoty, nazwy. Nie anonimizuj. Nie pisz dialogu. Nie kopiuj surowego tekstu. Zacznij od treści.*

### Parametry wywołania LLM

| Parametr | Wartość | Uzasadnienie |
|---|---|---|
| `temperature` | 0.0 | Deterministyczny output, brak kreatywności |
| `num_predict` | 4096 | Maks. długość odpowiedzi |
| `num_ctx` | 16384 | Okno kontekstu |
| `top_p` | 0.7 | Ograniczenie losowości |
| `repeat_penalty` | 1.1 | Kara za powtórzenia |
| `repeat_last_n` | 128 | Zakres detekcji powtórzeń |

### Post-processing

Odpowiedzi LLM przechodzą przez rozbudowane czyszczenie:

- Usuwanie artefaktów `[INST]` / `[/INST]`
- Usuwanie preambuł i meta-komentarzy
- Usuwanie formatu dialogowego (`[Osoba 1]: ...`)
- Usuwanie halucynowanych imion i nazwisk (porównanie z tekstem źródłowym)
- Wykrywanie zdegenerowanych odpowiedzi (powtórzenia, garbage output)
- Wykrywanie surowych kopii wejścia (>60% overlap → odrzucenie)
- Łączenie krótkich akapitów-sierot z poprzednimi

### Składanie wyniku

Streszczenia fragmentów są łączone w kodzie (bez dodatkowego wywołania LLM) w ustandaryzowany, ustrukturyzowany dokument z datą przetworzenia.

---

## Konfiguracja

Parametry konfiguracyjne znajdują się w `app/config.py`:

| Parametr | Wartość domyślna | Opis |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Adres serwera Ollama |
| `OLLAMA_MODEL` | `pllum-12b-instruct` | Nazwa modelu w Ollama |
| `WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | Model Whisper (HuggingFace) |
| `MAX_UPLOAD_SIZE_MB` | `500` | Maks. rozmiar uploadu w MB |
| `AUDIO_CHUNK_SECONDS` | `30` | Długość segmentu audio w sekundach |
| `AUDIO_OVERLAP_SECONDS` | `2` | Nakładanie między segmentami |

Logi aplikacji zapisywane są do `logs/stefka.log` (rotacja co 5 MB, 3 kopie zapasowe). Poziom logowania można ustawić zmienną `LOG_LEVEL` (domyślnie `INFO`).

---

## Obsługiwane formaty

### Pliki wejściowe

| Typ | Formaty |
|---|---|
| Audio | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.webm`, `.wma`, `.aac` |
| Tekst | `.txt`, `.md`, `.docx`, `.pdf` |

### Formaty wyjściowe

| Format | Zastosowanie |
|---|---|
| Markdown (`.md`) | Lekki, czytelny, łatwy do dalszej edycji |
| PDF (`.pdf`) | Gotowy do druku i archiwizacji |
| DOCX (`.docx`) | Edytowalny w Microsoft Word / LibreOffice |

---

## Struktura projektu

```
stefka/
|-- CLAUDE.md                        # Specyfikacja projektu
|-- README.md                        # Ten plik
|-- requirements.txt                 # Zależności Python
|-- requirements-dev.txt             # Zależności deweloperskie (testy)
|-- setup.sh                         # Skrypt instalacyjny
|-- run.sh                           # Skrypt uruchomieniowy
|-- Modelfile.pllum                  # Definicja modelu dla Ollama
|
|-- app/
|   |-- __init__.py
|   |-- main.py                      # FastAPI — punkt wejścia
|   |-- config.py                    # Konfiguracja (modele, ścieżki, limity)
|   |
|   |-- routers/
|   |   |-- upload.py                # POST /api/upload
|   |   |-- status.py                # GET /api/status/{job_id} (SSE)
|   |   +-- download.py              # GET /api/download/{job_id}
|   |
|   |-- services/
|   |   |-- transcription.py         # Transkrypcja mlx-whisper + czyszczenie
|   |   |-- audio_processing.py      # Konwersja audio, chunking (ffmpeg)
|   |   |-- text_extraction.py       # Ekstrakcja tekstu z DOCX/PDF/TXT
|   |   |-- llm.py                   # Pipeline chunk-summarize (Ollama/PLLuM)
|   |   +-- export.py                # Eksport MD / PDF / DOCX
|   |
|   |-- models/
|   |   +-- schemas.py               # Modele Pydantic
|   |
|   |-- templates/
|   |   +-- index.html               # Interfejs webowy
|   |
|   +-- static/
|       |-- css/style.css
|       +-- js/app.js
|
|-- tests/
|   +-- test_smoke.py                # Smoke testy czystej logiki pipeline'u
|
|-- data/
|   |-- uploads/                     # Pliki tymczasowe (czyszczone po przetworzeniu)
|   +-- outputs/                     # Wygenerowane wyniki (czyszczone po 24h)
|
|-- logs/
|   +-- stefka.log                   # Logi aplikacji (rotacja 5 MB)
|
+-- models/
    +-- pllum-12b-nc-instruct-q8_0.gguf   # Model PLLuM (generowany przez setup.sh)
```

---

## Znane ograniczenia

### PLLuM-12B

- Model 12B parametrów może generować powtórzenia w dłuższych odpowiedziach — aplikacja aktywnie je wykrywa i filtruje
- Zdarzają się halucynacje imion i nazwisk — post-processing usuwa nazwiska nieobecne w tekście źródłowym (czasem zbyt agresywnie — może usunąć prawdziwe imię)
- Przy złożonych tematach technicznych streszczenia mogą być uproszczone
- Okno kontekstu ograniczone do 16K tokenów na zapytanie (ograniczenie wydajnościowe, nie modelowe)
- Brak kroku łączenia (merge) streszczeń — wynik jest składany w kodzie, nie przez LLM

### Whisper (mlx-whisper)

- Na cichych fragmentach audio model generuje halucynacje ("Dziękuję za oglądanie", "Subskrybuj" itp.) — aplikacja je filtruje
- Powtarzające się słowa na granicach segmentów — deduplikacja przez dopasowanie dokładne i rozmyte (SequenceMatcher)
- Transkrypcja ustawiona na język polski (`language="pl"`) — inne języki nie są obsługiwane
- `condition_on_previous_text=False` zapobiega propagacji błędów między segmentami kosztem większej liczby powtórzeń na granicach

### Ogólne

- Aplikacja obsługuje jednego użytkownika na raz (brak kolejki zadań)
- Przetwarzanie długich nagrań (>30 min) może trwać kilka minut
- Eksport PDF wymaga zainstalowanego `pango` (instalowany przez `setup.sh`)
- Tylko macOS z Apple Silicon — brak wsparcia dla Linux / Windows / Intel Mac

---

## API

| Endpoint | Metoda | Opis |
|---|---|---|
| `/` | GET | Interfejs webowy |
| `/api/upload` | POST | Upload pliku (multipart/form-data) |
| `/api/status/{job_id}` | GET | Status przetwarzania (SSE stream) |
| `/api/download/{job_id}` | GET | Pobranie wygenerowanego wyniku |
| `/api/health` | GET | Sprawdzenie stanu Ollama i modelu |

---

## Testy

Smoke testy obejmują czystą logikę pipeline'u (chunkowanie, detekcja zdegenerowanego
outputu, składanie noty) — nie wymagają uruchomionej Ollamy ani modeli.

```bash
pip install -r requirements-dev.txt
pytest
```

---

## Licencja

Kod aplikacji: **MIT** (patrz [LICENSE](LICENSE)).

> ⚠️ **Uwaga o modelu:** domyślny model językowy `CYFRAGOVPL/PLLuM-12B-nc-instruct`
> jest na licencji **CC-BY-NC-4.0 (niekomercyjnej)**. Użycie aplikacji z tym
> modelem do celów komercyjnych jest niedozwolone. Do zastosowań komercyjnych
> należy podmienić model na wariant permisywny (np. `CYFRAGOVPL/PLLuM-12B-instruct`,
> Apache-2.0). Szczegóły w pliku [NOTICE](NOTICE).
