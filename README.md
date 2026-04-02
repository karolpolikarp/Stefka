# Stefka

**Lokalna aplikacja do transkrypcji audio i strukturyzowania notatek sluzbowych**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![mlx-whisper](https://img.shields.io/badge/mlx--whisper-large--v3--turbo-FF6F00?logo=apple&logoColor=white)](https://github.com/ml-explore/mlx-examples)
[![PLLuM](https://img.shields.io/badge/PLLuM-12B--instruct-1E88E5)](https://huggingface.co/CYFRAGOVPL/PLLuM-12B-nc-instruct)

Stefka przetwarza pliki audio i tekstowe na ustandaryzowane notatki sluzbowe. Wszystkie modele AI dzialaja lokalnie -- zadne dane nie opuszczaja maszyny uzytkownika.

Aplikacja zostala zaprojektowana na potrzeby Ministerstwa Cyfryzacji.

<!-- screenshot -->

---

## Funkcjonalnosci

- **Pelna prywatnosc danych** -- zero komunikacji z zewnetrznymi API, cale przetwarzanie na localhost
- **Transkrypcja audio** -- mlx-whisper zoptymalizowany pod Apple Silicon (10-15x szybciej niz real-time na M4 Pro)
- **Strukturyzowanie tekstu** -- polski model jezykowy PLLuM-12B generuje ustandaryzowane notatki sluzbowe
- **Przetwarzanie plikow tekstowych** -- import z TXT, MD, DOCX, PDF
- **Eksport wieloformatowy** -- zapis notatek do Markdown, PDF lub DOCX
- **Interfejs webowy** -- prosta strona z uploadem, paskiem postepu (SSE) i pobieraniem wyniku
- **Automatyczne czyszczenie** -- pliki tymczasowe usuwane po przetworzeniu, wyniki po 24h

---

## Architektura

```
+---------------------------------------------------------+
|                     PRZEGLADARKA                        |
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
| Backend | Python 3.11+ / FastAPI | Async, SSE do raportowania postepu |
| Transkrypcja | mlx-whisper (large-v3-turbo) | Natywna akceleracja GPU na Apple Silicon |
| Model jezykowy | PLLuM-12B-nc-instruct via Ollama | Oficjalny model z CYFRAGOVPL/HuggingFace, GGUF Q8 |
| Przetwarzanie audio | ffmpeg + pydub | Konwersja do WAV 16kHz, dzielenie na segmenty |
| Eksport PDF | WeasyPrint | Konwersja HTML/CSS na PDF |
| Eksport DOCX | python-docx | Generowanie dokumentow Word z zachowaniem formatowania |
| Ekstrakcja tekstu | PyPDF2, python-docx | Odczyt uploadowanych PDF i DOCX |
| Frontend | Vanilla HTML/CSS/JS + Jinja2 | Zero zaleznosci frontendowych |

### Wymagania sprzetowe

| Komponent | RAM | Uwagi |
|---|---|---|
| mlx-whisper large-v3-turbo | ~3-4 GB | Ladowany na czas transkrypcji |
| PLLuM-12B-instruct (Q8) | ~13 GB | Ollama zarzadza pamiecia |
| System + FastAPI | ~4-6 GB | macOS + Python runtime |
| **Lacznie** | **~20-23 GB** | Komfortowo przy 48 GB RAM |

---

## Szybki start

### Wymagania wstepne

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

1. Sprawdza i instaluje zaleznosci systemowe (ffmpeg, Ollama, pango, llama.cpp)
2. Tworzy srodowisko wirtualne Python i instaluje zaleznosci
3. Pobiera oficjalny model PLLuM-12B-nc-instruct z [CYFRAGOVPL/HuggingFace](https://huggingface.co/CYFRAGOVPL/PLLuM-12B-nc-instruct)
4. Konwertuje model do formatu GGUF Q8_0 i importuje do Ollama

Pierwsze uruchomienie `setup.sh` moze potrwac kilkanascie minut (pobranie ~24 GB + konwersja modelu).

### Uruchomienie

```bash
./run.sh
```

Aplikacja dostepna pod: **http://localhost:8000**

Skrypt `run.sh` uruchamia Ollama (jesli nie dziala) oraz serwer FastAPI na porcie 8000. Aplikacja nasluchuje wylacznie na `127.0.0.1` -- nie jest dostepna z sieci.

---

## Jak to dziala

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
Transkrypcja kazdego segmentu (mlx-whisper)
  + usuwanie halucynacji Whisper
  + deduplikacja overlappujacego tekstu
    |
    v
Strukturyzowanie przez PLLuM (chunk-summarize)
    |
    v
Eksport do wybranego formatu (MD / PDF / DOCX)
    |
    v
Pobranie wyniku z przegladarki
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
Pobranie wyniku z przegladarki
```

---

## Pipeline LLM

Stefka uzywa podejscia **chunk-summarize** do przetwarzania tekstu przez PLLuM-12B:

### Dzielenie na fragmenty

Tekst wejsciowy jest dzielony na fragmenty po ~6000 znakow (`CHUNK_SIZE`) z 400-znakowym nakladaniem (`CHUNK_OVERLAP`). Ciecie odbywa sie na granicach zdan. Ostatni fragment, jesli jest krotszy niz 40% docelowego rozmiaru, jest laczony z poprzednim.

### Streszczanie fragmentow
 
Kazdy fragment jest przetwarzany osobno przez PLLuM z promptem systemowym:

> *Strzesc ponizszy fragment spotkania w akapitach. Zachowaj imiona, nazwiska, daty, kwoty, nazwy. Nie anonimizuj. Nie pisz dialogu. Nie kopiuj surowego tekstu. Zacznij od tresci.*

### Parametry wywolania LLM

| Parametr | Wartosc | Uzasadnienie |
|---|---|---|
| `temperature` | 0.0 | Deterministyczny output, brak kreatywnosci |
| `num_predict` | 4096 | Maks. dlugosc odpowiedzi |
| `num_ctx` | 16384 | Okno kontekstu |
| `top_p` | 0.7 | Ograniczenie losowosci |
| `repeat_penalty` | 1.1 | Kara za powtorzenia |
| `repeat_last_n` | 128 | Zakres detekcji powtorzen |

### Post-processing

Odpowiedzi LLM przechodza przez rozbudowane czyszczenie:

- Usuwanie artefaktow `[INST]` / `[/INST]`
- Usuwanie preambul i meta-komentarzy
- Usuwanie formatu dialogowego (`[Osoba 1]: ...`)
- Usuwanie halucynowanych imion i nazwisk (porownanie z tekstem zrodlowym)
- Wykrywanie zdegenerowanych odpowiedzi (powtorzenia, garbage output)
- Wykrywanie surowych kopii wejscia (>60% overlap -> odrzucenie)
- Laczenie krotkich akapitow-sierot z poprzednimi

### Skladanie notatki

Streszczenia fragmentow sa laczone w kod (bez dodatkowego wywolania LLM) w ustandaryzowany format notatki sluzbowej z data przetworzenia.

---

## Konfiguracja

Parametry konfiguracyjne znajduja sie w `app/config.py`:

| Parametr | Wartosc domyslna | Opis |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Adres serwera Ollama |
| `OLLAMA_MODEL` | `pllum-12b-instruct` | Nazwa modelu w Ollama |
| `WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | Model Whisper (HuggingFace) |
| `MAX_UPLOAD_SIZE_MB` | `500` | Maks. rozmiar uploadu w MB |
| `AUDIO_CHUNK_SECONDS` | `30` | Dlugosc segmentu audio w sekundach |
| `AUDIO_OVERLAP_SECONDS` | `2` | Nakladanie miedzy segmentami |

Logi aplikacji zapisywane sa do `logs/stefka.log` (rotacja co 5 MB, 3 kopie zapasowe).

---

## Obslugiwane formaty

### Pliki wejsciowe

| Typ | Formaty |
|---|---|
| Audio | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.webm`, `.wma`, `.aac` |
| Tekst | `.txt`, `.md`, `.docx`, `.pdf` |

### Formaty wyjsciowe

| Format | Zastosowanie |
|---|---|
| Markdown (`.md`) | Lekki, czytelny, latwy do dalszej edycji |
| PDF (`.pdf`) | Gotowy do druku i archiwizacji |
| DOCX (`.docx`) | Edytowalny w Microsoft Word / LibreOffice |

---

## Struktura projektu

```
stefka/
|-- CLAUDE.md                        # Specyfikacja projektu
|-- README.md                        # Ten plik
|-- requirements.txt                 # Zaleznosci Python
|-- setup.sh                         # Skrypt instalacyjny
|-- run.sh                           # Skrypt uruchomieniowy
|-- Modelfile.pllum                  # Definicja modelu dla Ollama
|
|-- app/
|   |-- __init__.py
|   |-- main.py                      # FastAPI -- punkt wejscia
|   |-- config.py                    # Konfiguracja (modele, sciezki, limity)
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
|-- data/
|   |-- uploads/                     # Pliki tymczasowe (czyszczone po przetworzeniu)
|   +-- outputs/                     # Wygenerowane notatki (czyszczone po 24h)
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

- Model 12B parametrow moze generowac powtorzenia w dluzszych odpowiedziach -- aplikacja aktywnie je wykrywa i filtruje
- Zdarzaja sie halucynacje imion i nazwisk -- post-processing usuwa nazwiska nieobecne w tekscie zrodlowym
- Przy zlozonych tematach technicznych streszczenia moga byc uproszczone
- Okno kontekstu ograniczone do 16K tokenow na zapytanie (ograniczenie wydajnosciowe, nie modelowe)
- Brak kroku laczenia (merge) streszsczen -- notatka jest skladana w kodzie, nie przez LLM

### Whisper (mlx-whisper)

- Na cichych fragmentach audio model generuje halucynacje ("Dziekuje za ogladanie", "Subskrybuj" itp.) -- aplikacja je filtruje
- Powtarzajace sie slowa na granicach segmentow -- deduplikacja przez dopasowanie dokladne i rozmyte (SequenceMatcher)
- Transkrypcja ustawiona na jezyk polski (`language="pl"`) -- inne jezyki nie sa obslugiwane
- `condition_on_previous_text=False` zapobiega propagacji bledow miedzy segmentami kosztem wiekszej liczby powtorzen na granicach

### Ogolne

- Aplikacja obsluguje jednego uzytkownika na raz (brak kolejki zadan)
- Przetwarzanie dlugich nagran (>30 min) moze trwac kilka minut
- Eksport PDF wymaga zainstalowanego `pango` (instalowany przez `setup.sh`)
- Tylko macOS z Apple Silicon -- brak wsparcia dla Linux / Windows / Intel Mac

---

## API

| Endpoint | Metoda | Opis |
|---|---|---|
| `/` | GET | Interfejs webowy |
| `/api/upload` | POST | Upload pliku (multipart/form-data) |
| `/api/status/{job_id}` | GET | Status przetwarzania (SSE stream) |
| `/api/download/{job_id}` | GET | Pobranie wygenerowanej notatki |
| `/api/health` | GET | Sprawdzenie stanu Ollama i modelu |

---

## Licencja

<!-- TODO: dodac licencje -->
