import logging
import re

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

NOTE_SYSTEM_PROMPT = """\
Jesteś asystentem Ministerstwa Cyfryzacji, który przetwarza transkrypcje spotkań w ustandaryzowane notatki służbowe. Tworzysz dokumenty przeznaczone do użytku wewnętrznego na szczeblu ministerialnym.

## STRUKTURA NOTATKI

Każda notatka ma następujący układ. Sekcje, które nie mają pokrycia w transkrypcji, pomiń bez komentarza.

### 1. METRYCZKA

Na początku notatki umieść tabelę z danymi podstawowymi:
- Data spotkania (jeśli wynika z transkrypcji lub nazwy pliku)
- Forma (stacjonarne / online / hybrydowe)
- Uczestnicy (imiona, nazwiska, funkcje, instytucje — tylko te, które faktycznie padają w transkrypcji)
- Temat główny (jedno zdanie)

### 2. STRESZCZENIE WYKONAWCZE

Krótki akapit (3–5 zdań) z najważniejszymi ustaleniami i wnioskami. Czytelnik po samym streszczeniu powinien wiedzieć, o czym było spotkanie i co z niego wynika. Nie powtarzaj tu szczegółów, które rozwijasz niżej.

### 3. SEKCJE TEMATYCZNE

Podziel treść spotkania na logiczne bloki tematyczne. Każdy blok to osobna sekcja z nagłówkiem. Nie kopiuj chronologicznego porządku rozmowy — grupuj wątki, które dotyczą tego samego tematu, nawet jeśli pojawiały się w różnych momentach.

Każda sekcja zawiera:
- Opis stanu faktycznego (co ustalono, co powiedziano)
- Konkretne dane: kwoty, terminy, nazwy instytucji, numery artykułów, nazwy projektów
- Cytaty w cudzysłowie — tylko gdy wypowiedź jest na tyle istotna, że jej sens zmienia się przy parafrazie. Zawsze z atrybucją (kto powiedział). Nie nadużywaj cytatów.

### 4. USTALENIA I DALSZE KROKI

Lista konkretnych ustaleń podjętych podczas spotkania. Każde ustalenie powinno zawierać:
- Co ma zostać zrobione
- Kto jest odpowiedzialny (jeśli wynika z transkrypcji)
- Termin (jeśli padł)

### 5. PYTANIA OTWARTE / DO WYJAŚNIENIA

Kwestie, które zostały poruszone, ale nie rozstrzygnięte. Tematy wymagające dalszej analizy lub decyzji.

---

## ZASADY REDAKCYJNE

### Język i styl
- Pisz po polsku, poprawną polszczyzną.
- Ton profesjonalny, rzeczowy, bez emocji i wartościowania.
- Unikaj konstrukcji potocznych, kolokwializmów i żargonu korporacyjnego.
- Nie używaj zwrotów typu „warto zauważyć", „co istotne", „należy podkreślić" — po prostu podaj informację.
- Nie używaj pauzy (—) ani dwukropka jako elementu stylistycznego.
- Zdania krótkie i jednoznaczne. Jedno zdanie = jedna informacja.

### Formatowanie
- Nagłówki sekcji tematycznych powinny być opisowe (np. „Budżet projektu OCEAR" zamiast „Punkt 3").
- Punkty w listach (ustalenia, kroki) powinny być pełnymi zdaniami, nie hasłami.
- Nie nadużywaj pogrubień. Pogrubiaj wyłącznie: nazwiska przy pierwszym wystąpieniu, kwoty, terminy, nazwy kluczowych projektów lub aktów prawnych.

### Rzetelność i precyzja
- Opieraj się WYŁĄCZNIE na tym, co jest w transkrypcji. Nie dodawaj wiedzy zewnętrznej, kontekstu, wyjaśnień ani interpretacji.
- Jeśli transkrypcja jest niejasna lub urwana, napisz wprost, że dany fragment jest nieczytelny — nie próbuj domyślać się treści.
- Nie spekuluj, nie wnioskuj, nie generalizuj ponad to, co zostało powiedziane.
- Jeśli ktoś wyraził opinię, zaznacz że to opinia konkretnej osoby, a nie ustalony fakt.
- Nazwy własne instytucji, projektów i aktów prawnych podawaj w pełnej formie przy pierwszym użyciu, potem możesz stosować skróty.

### Czego NIE robić
- Nie pisz wstępów typu „Poniżej przedstawiam notatkę z...".
- Nie pisz zakończeń typu „Notatka sporządzona na podstawie...".
- Nie komentuj jakości transkrypcji.
- Nie dodawaj rekomendacji, chyba że ktoś na spotkaniu je sformułował — wtedy podaj je jako rekomendację tej osoby.
- Nie powtarzaj tych samych informacji w różnych sekcjach.
- Nie używaj emoji, ozdobników, nagłówków w CAPSLOCK.

### Transkrypcje anglojęzyczne
Jeśli spotkanie było prowadzone po angielsku, notatka i tak jest po polsku. Cytaty z wypowiedzi anglojęzycznych uczestników podawaj w oryginale (po angielsku), w cudzysłowie, z polskim kontekstem wokół."""

CHUNK_NOTE_PROMPT = """\
Jesteś asystentem Ministerstwa Cyfryzacji. Poniżej znajduje się fragment transkrypcji spotkania \
(część {part_num} z {total_parts}). Na podstawie tego fragmentu stwórz częściową notatkę służbową \
w formacie Markdown. Uwzględnij WSZYSTKIE omawiane tematy i szczegóły.

Dla każdego tematu poruszanego w tym fragmencie napisz osobną sekcję z nagłówkiem (###). \
W każdej sekcji uwzględnij: kto co powiedział, konkretne dane (kwoty, terminy, nazwy), \
ustalenia i zadania do wykonania.

Zachowaj pełne nazwiska z funkcjami. Pisz po polsku, profesjonalnie. \
Nie dodawaj informacji spoza transkrypcji."""

MERGE_NOTES_PROMPT = """\
Jesteś asystentem Ministerstwa Cyfryzacji. Poniżej znajdują się częściowe notatki z kolejnych \
fragmentów tego samego spotkania. Połącz je w jedną spójną notatkę służbową w formacie Markdown.

Struktura wynikowej notatki:
### 1. METRYCZKA (tabela: data, forma, uczestnicy zebrani ze wszystkich części, temat główny)
### 2. STRESZCZENIE WYKONAWCZE (3-5 zdań z najważniejszymi ustaleniami)
### 3. SEKCJE TEMATYCZNE (osobna sekcja z nagłówkiem ### dla każdego tematu)
### 4. USTALENIA I DALSZE KROKI (lista: co, kto, kiedy — zebrane ze wszystkich części)
### 5. PYTANIA OTWARTE / DO WYJAŚNIENIA

Zasady:
- Grupuj wątki dotyczące tego samego tematu z różnych części w jedną sekcję.
- NIE powtarzaj informacji. Jeśli ten sam fakt pojawia się w kilku częściach, napisz go raz.
- Zachowaj WSZYSTKIE konkretne szczegóły: nazwiska, kwoty, terminy, nazwy projektów, artykuły prawne.
- Pisz po polsku, profesjonalnie. Nie dodawaj wstępów ani zakończeń. Zacznij od ### 1. METRYCZKA."""

# PLLuM-12B degrades on inputs longer than ~18K chars.
MAX_DIRECT_CHARS = 18000
CHUNK_SIZE = 15000


async def structure_note(text: str, on_progress=None) -> str:
    """Send text to PLLuM via Ollama and get a structured note back.

    Args:
        text: Transcription or extracted text to structure.
        on_progress: Optional callback(message) for progress reporting.
    """
    if len(text) <= MAX_DIRECT_CHARS:
        if on_progress:
            on_progress("PLLuM strukturyzuje notatkę...")
        logger.info("Sending text to PLLuM for structuring (%d chars)", len(text))
        raw = await _call_ollama(NOTE_SYSTEM_PROMPT, text, num_predict=4096)
        logger.info("PLLuM raw response (%d chars): %s", len(raw), raw[:500])
        cleaned = _clean_note_output(raw)
        logger.info("PLLuM response: %d chars raw -> %d chars cleaned", len(raw), len(cleaned))
        return cleaned

    # Map-reduce for long texts
    logger.info("Text too long (%d chars), using map-reduce", len(text))
    partial_notes = await _map_chunks_to_notes(text, on_progress)
    merged = await _reduce_notes(partial_notes, on_progress)
    cleaned = _clean_note_output(merged)
    logger.info("Map-reduce complete: %d chars input -> %d chars output", len(text), len(cleaned))
    return cleaned


def _split_into_chunks(text: str, max_size: int) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    chunks = []
    while len(text) > max_size:
        # Find last sentence end (. ! ?) before max_size
        cut = max_size
        for sep in ['. ', '? ', '! ']:
            pos = text.rfind(sep, 0, max_size)
            if pos > max_size * 0.5:  # Don't cut too early
                cut = pos + len(sep)
                break
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


async def _map_chunks_to_notes(text: str, on_progress=None) -> list[str]:
    """MAP phase: generate a partial note from each chunk."""
    chunks = _split_into_chunks(text, CHUNK_SIZE)
    total = len(chunks)
    logger.info("MAP phase: generating notes for %d chunks", total)
    notes = []
    for i, chunk in enumerate(chunks):
        if on_progress:
            on_progress(f"PLLuM analizuje część {i + 1}/{total}...")
        prompt = CHUNK_NOTE_PROMPT.format(part_num=i + 1, total_parts=total)
        logger.info("MAP chunk %d/%d (%d chars)", i + 1, total, len(chunk))
        note = await _call_ollama(prompt, chunk, num_predict=4096)
        notes.append(note.strip())
        logger.info("MAP chunk %d result: %d chars", i + 1, len(note))
    return notes


async def _reduce_notes(partial_notes: list[str], on_progress=None) -> str:
    """REDUCE phase: merge partial notes into one final note."""
    combined_input = ""
    for i, note in enumerate(partial_notes):
        combined_input += f"\n\n--- CZĘŚĆ {i + 1} ---\n\n{note}"

    if on_progress:
        on_progress("PLLuM scala notatki w całość...")
    logger.info("REDUCE phase: merging %d partial notes (%d chars total)",
                len(partial_notes), len(combined_input))

    # If merged input fits in context, do single reduce with ministerial format
    if len(combined_input) <= MAX_DIRECT_CHARS:
        result = await _call_ollama(
            MERGE_NOTES_PROMPT,
            combined_input,
            num_predict=4096,
        )
        logger.info("REDUCE result: %d chars", len(result))
        return result

    # If still too long, reduce in pairs
    logger.info("REDUCE: merged notes still too long (%d chars), reducing in pairs",
                len(combined_input))
    while len(partial_notes) > 1:
        merged = []
        for i in range(0, len(partial_notes), 2):
            if i + 1 < len(partial_notes):
                pair = f"--- CZĘŚĆ A ---\n\n{partial_notes[i]}\n\n--- CZĘŚĆ B ---\n\n{partial_notes[i+1]}"
                logger.info("REDUCE pair %d+%d (%d chars)", i + 1, i + 2, len(pair))
                result = await _call_ollama(MERGE_NOTES_PROMPT, pair, num_predict=4096)
                merged.append(result.strip())
            else:
                merged.append(partial_notes[i])
        partial_notes = merged

    # Final pass with ministerial format
    final = await _call_ollama(NOTE_SYSTEM_PROMPT, partial_notes[0], num_predict=4096)
    logger.info("REDUCE final: %d chars", len(final))
    return final


async def _call_ollama(system: str, user: str, num_predict: int = 4096) -> str:
    """Make a single call to Ollama."""
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": num_predict,
                    "num_ctx": 32768,
                    "top_p": 0.9,
                    "repeat_penalty": 1.3,
                    "repeat_last_n": 256,
                },
            },
        )
        response.raise_for_status()
        data = response.json()
    return data.get("message", {}).get("content", "").strip()


def _clean_note_output(text: str) -> str:
    """Strip preamble, trailing commentary, and repeated blocks."""
    # Strip preamble (hallucinated transcript continuation, [/INST] tags, etc.)
    match = re.search(r'^(#{2,3}\s)', text, re.MULTILINE)
    if match:
        text = text[match.start():]
    # Strip trailing meta-commentary (e.g. "Ta notatka zawiera...")
    text = re.sub(r'\n(?:Ta notatka|Powyższa notatka|Notatka sporządzona|Notatka została).*$',
                  '', text, flags=re.DOTALL)
    # Detect repeated note — cut at second occurrence of "Metryczka" or "METRYCZKA"
    parts = re.split(r'(?=\n.*Metryczka)', text, flags=re.IGNORECASE)
    if len(parts) > 1:
        text = parts[0]
        logger.warning("Detected repeated note blocks (%d repetitions removed)", len(parts) - 1)
    return text.strip()


async def check_ollama_health() -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            ok = any(OLLAMA_MODEL.lower() in name.lower() for name in model_names)
            if not ok:
                logger.warning("Ollama is running but model %s not found (available: %s)", OLLAMA_MODEL, model_names)
            return ok
    except Exception as e:
        logger.warning("Ollama health check failed: %s", e)
        return False
