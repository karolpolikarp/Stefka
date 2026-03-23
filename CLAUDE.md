# Stefka — Lokalna Aplikacja do Transkrypcji i Strukturyzowania Notatek

## Kontekst i Cel

Stefka to lokalna aplikacja webowa dla Ministerstwa Cyfryzacji, zaprojektowana z naciskiem na **bezpieczeństwo i prywatność danych**. Wszystkie modele AI działają lokalnie na MacBooku — żadne dane nie opuszczają maszyny.

Aplikacja przyjmuje pliki audio lub tekstowe i przetwarza je na notatki służbowe:
- **mlx-whisper** (transkrypcja mowy na tekst, natywnie Apple Silicon)
- **PLLuM-12B** (oficjalny polski model językowy CYFRAGOVPL do strukturyzowania treści)

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
│  │         Chunk-summarize + code assembly               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                    Lokalne Modele AI                         │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │  mlx-whisper         │  │  Ollama                     │  │
│  │  large-v3-turbo      │  │  pllum-12b-instruct         │  │
│  │  (natywne Apple Si.) │  │  (GGUF Q8_0, ~13GB)         │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Pipeline LLM — chunk-summarize MVP

PLLuM-12B jest modelem 12B parametrów — za słabym na generowanie pełnych notatek jednym promptem. Zamiast tego stosujemy **dekompozycję**:

### Podejście
1. **Chunk** — tekst dzielony na fragmenty po ~6000 znaków z 400-znakowym overlapem
2. **Summarize** — każdy chunk przetwarzany osobnym, krótkim promptem
3. **Assemble** — nota składana kodem (Python), nie LLM-em — deterministyczna struktura

### Prompt (celowo krótki — PLLuM lepiej reaguje na zwięzłe instrukcje)
```
Streść poniższy fragment spotkania w akapitach.
Zachowaj imiona, nazwiska, daty, kwoty, nazwy.
Nie anonimizuj. Nie pisz dialogu. Nie kopiuj surowego tekstu. Zacznij od treści.
```

### Parametry Ollama
| Parametr | Wartość | Uzasadnienie |
|----------|---------|--------------|
| temperature | 0.0 | Deterministyczny output — ten sam input = ta sama nota |
| repeat_penalty | 1.1 | Niski — nie karze za powtarzanie struktur w listach |
| num_ctx | 16384 | Wystarczający dla chunków 6K |
| top_p | 0.7 | Mniej losowych tokenów |
| num_predict | 4096 | Limit tokenów na chunk |

### Post-processing outputu PLLuM
PLLuM-12B ma tendencję do:
- **Anonimizacji** — zamienia imiona na `[Osoba 1]`, `[Imię]` (safety behavior modelu)
- **Formatu dialogu** — kopiuje Q&A z transkrypcji zamiast streszczać
- **Kopiowania surowego tekstu** — dosłownie przepisuje input
- **Filler sentences** — "Podczas spotkania poruszono wiele tematów"
- **Formatu listu** — "Dzień dobry", "Z poważaniem, [Podpis]"

Post-processing w `_clean_response()`:
1. Usuwanie tagów `[INST]`, `[/INST]`
2. Usuwanie preambuł ("Poniżej znajduje się...")
3. Usuwanie `[Osoba N]`, `[Imię]` i formatu dialogu
4. Usuwanie artefaktów formatu listu
5. Deduplikacja powtarzających się preambuł
6. Usuwanie filler sentences
7. Detekcja halucynowanych imion (dwuczłonowe nazwy nieobecne w transkrypcji)
8. Detekcja raw copy (>60% overlap z inputem → odrzucenie)
9. Scalanie osieroconych krótkich akapitów (<80 znaków)

### Kluczowy wniosek z iteracji
**Im krótszy prompt, tym lepszy output z PLLuM-12B.** Długie, złożone instrukcje są ignorowane. Model radzi sobie najlepiej z jednym prostym zdaniem per instrukcję.

---

## Transkrypcja (mlx-whisper)

### Model
- `mlx-community/whisper-large-v3-turbo` (~809M parametrów)
- Zoptymalizowany pod Apple Silicon (MLX framework)
- Na M4 Pro: ~10-15x szybciej niż real-time
- Język: polski (`language="pl"`)

### Parametry
| Parametr | Wartość | Uzasadnienie |
|----------|---------|--------------|
| condition_on_previous_text | False | Zapobiega zapętlaniu na ciszy |
| compression_ratio_threshold | 2.0 | Wykrywanie zdegenerowanego outputu |
| no_speech_threshold | 0.5 | Odrzucanie segmentów bez mowy |

### Chunking audio
- Segmenty ~30s z 2s overlap (ffmpeg)
- Overlap deduplication: exact match + fuzzy (SequenceMatcher)

### Post-processing transkrypcji
- 20+ wzorców halucynacji Whisper (polskojęzyczne): "Dziękuję za oglądanie", "Dzięki za oglądanie", "Napisy stworzone przez społeczność", "Subskrybuj", "[muzyka]", itp.
- Per-chunk filtering (halucynacje usuwane zanim trafią do łączenia)
- Kolapsowanie powtórzonych słów i fraz
- Normalizacja interpunkcji (brakujące spacje, podwójne kropki)

---

## Tech Stack

| Komponent | Technologia | Uzasadnienie |
|-----------|-------------|--------------|
| **Backend** | Python 3.11+ / FastAPI | Szybki, async, SSE support |
| **Transkrypcja** | mlx-whisper (large-v3-turbo) | Natywna optymalizacja Apple Silicon |
| **LLM** | Ollama + PLLuM-12B-instruct | Oficjalny model CYFRAGOVPL, GGUF Q8_0 |
| **Audio** | ffmpeg | Konwersja formatów, chunking |
| **Frontend** | Vanilla HTML/CSS/JS + Jinja2 | Zero zależności, glassmorphism 2026 |
| **Eksport** | weasyprint (PDF), python-docx (DOCX) | Generowanie dokumentów |
| **Ekstrakcja tekstu** | python-docx, PyPDF2 | Odczyt uploadowanych plików |

### Model PLLuM — setup
- Oficjalny: `CYFRAGOVPL/PLLuM-12B-nc-instruct` z HuggingFace
- Konwersja: `convert_hf_to_gguf.py` (llama.cpp) → Q8_0 GGUF
- Import: `ollama create pllum-12b-instruct -f Modelfile.pllum`
- Modelfile: template `[INST]...[/INST]` (Mistral-Nemo chat format)
- **NIE** używać community `PRIHLOP/PLLuM:12b` — brak chat template

### Wymagania sprzętowe (M4 Pro 48GB)

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
├── CLAUDE.md                     # Ten plik — instrukcje dla AI
├── README.md                     # Dokumentacja projektu
├── requirements.txt              # Zależności Python
├── Modelfile.pllum               # Ollama Modelfile dla PLLuM
├── setup.sh                      # Skrypt instalacyjny
├── run.sh                        # Skrypt uruchomieniowy
│
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI — punkt wejścia, health check
│   ├── config.py                 # Konfiguracja (ścieżki, modele, limity)
│   │
│   ├── routers/
│   │   ├── upload.py             # POST /api/upload + background processing
│   │   ├── status.py             # GET /api/status/{job_id} — SSE progress
│   │   └── download.py           # GET /api/download/{job_id}
│   │
│   ├── services/
│   │   ├── transcription.py      # mlx-whisper + post-processing halucynacji
│   │   ├── audio_processing.py   # ffmpeg: konwersja, chunking
│   │   ├── text_extraction.py    # DOCX/PDF/TXT/MD → tekst
│   │   ├── llm.py                # Chunk-summarize pipeline + Ollama client
│   │   └── export.py             # MD/PDF/DOCX eksport
│   │
│   ├── models/
│   │   └── schemas.py            # Pydantic: JobInfo, ExportFormat, etc.
│   │
│   ├── templates/
│   │   └── index.html            # Główna strona (glassmorphism 2026)
│   │
│   └── static/
│       ├── css/style.css         # Design system MC
│       └── js/app.js             # Upload, SSE, download logic
│
├── data/
│   ├── uploads/                  # Tymczasowe (czyszczone po przetworzeniu)
│   └── outputs/                  # Notatki + transkrypcje (TTL 24h)
│
├── models/                       # GGUF modelu PLLuM (po setup.sh)
└── logs/                         # Logi aplikacji (rotacja 5MB x 3)
```

---

## Kluczowe Decyzje Projektowe

### 1. Bezpieczeństwo danych (priorytet #1)
- Zero komunikacji z zewnętrznymi API
- Pliki tymczasowe usuwane po przetworzeniu (uploads) i po 24h (outputs)
- Brak logowania treści przetwarzanych plików
- Aplikacja dostępna tylko z localhost
- Walidacja path traversal w download endpoint
- Health check Ollama przed przyjęciem pliku (503 jeśli niedostępna)

### 2. Chunk-summarize zamiast single-prompt
- PLLuM-12B nie daje rady z jednym promptem na długi tekst (>8K znaków)
- Produkuje krótki, halucynacyjny, niedeterministyczny output
- Rozwiązanie: chunki po 6K → prosty prompt per chunk → składanie kodem
- temperature=0 zapewnia powtarzalność

### 3. Post-processing zamiast prompt engineering
- PLLuM-12B ignoruje złożone instrukcje
- Zamiast walczyć z modelem w prompcie, czyścimy output kodem
- Detekcja i usuwanie: anonimizacji, dialogu, raw copy, fillera, halucynowanych imion

### 4. Oficjalny PLLuM z CYFRAGOVPL
- Model: `CYFRAGOVPL/PLLuM-12B-nc-instruct` (HuggingFace)
- Konwersja do GGUF Q8_0 przez llama.cpp
- Importowany do Ollama z własnym Modelfile (template [INST])
- Community model `PRIHLOP/PLLuM:12b` nie nadawał się (brak chat template)

### 5. SSE do raportowania postępu
- Prostsze niż WebSocket (jednostronna komunikacja)
- Natywne wsparcie w przeglądarkach (EventSource API)
- Fallback na polling jeśli SSE się zerwie

### 6. Jobs cleanup
- In-memory job store z TTL (1h dla jobów, 24h dla plików output)
- Cleanup triggerowany przy każdym nowym uploadzie
- Double-submit guard w frontend (isSubmitting flag)

---

## Formaty plików

### Obsługiwane pliki wejściowe

| Typ | Formaty |
|-----|---------|
| Audio | .mp3, .wav, .m4a, .flac, .ogg, .webm, .wma, .aac |
| Tekst | .txt, .md, .docx, .pdf |

### Formaty wyjściowe notatek
- **Markdown** (.md)
- **PDF** (.pdf) — weasyprint
- **DOCX** (.docx) — python-docx z obsługą tabel i pogrubień

---

## Setup i Uruchomienie

### Wymagania wstępne
- macOS z Apple Silicon (M1/M2/M3/M4)
- Python 3.11+
- Homebrew

### Instalacja
```bash
./setup.sh    # Instaluje ffmpeg, Ollama, pango, pobiera i konwertuje PLLuM
```

### Uruchomienie
```bash
./run.sh      # Startuje Ollama (jeśli nie działa) + uvicorn
```

Aplikacja dostępna pod: **http://localhost:8000**

---

## Znane ograniczenia PLLuM-12B

1. **Anonimizacja** — model ma tendencję do zamieniania imion na `[Osoba]` (safety behavior). Częściowo łapane przez post-processing, ale nie w 100%.
2. **Halucynacje** — przy dłuższych inputach wymyśla fakty, imiona, nazwy projektów. Chunk-summarize minimalizuje ten problem.
3. **Niestabilna jakość** — różne chunki tego samego spotkania mogą dać różną jakość outputu. temperature=0 zapewnia powtarzalność, ale nie gwarantuje jakości.
4. **Brak tematycznego grupowania** — model nie potrafi niezawodnie grupować wątków tematycznie. Nota jest chronologiczna (chunk po chunku).
5. **Krótki prompt = lepszy output** — długie, złożone instrukcje są ignorowane.

## Planowane rozszerzenia
- Wysyłka notatki na email (SMTP)
- Detekcja mówców (speaker diarization)
- Historia przetworzonych plików
- Batch processing (wiele plików naraz)
- Wybór języka transkrypcji
- Lepszy model LLM (gdy dostępny większy polski model lokalny)
