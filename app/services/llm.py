import logging
import re
from datetime import datetime

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

NOTE_SYSTEM_PROMPT = """Jesteś asystentem do tworzenia notatek. Odpowiadaj TYLKO w formacie Markdown. Nie dodawaj żadnych komentarzy ani wyjaśnień poza notatką. Pisz WYŁĄCZNIE po polsku."""

NOTE_TEMPLATE = """Przekształć poniższy tekst w ustandaryzowaną notatkę. Odpowiedz TYLKO notatką w formacie Markdown, bez żadnych dodatkowych komentarzy.

Użyj dokładnie tego formatu:

## Tytuł
(wygeneruj krótki tytuł)

## Data
{date}

## Podsumowanie
(2-3 zdania podsumowujące)

## Kluczowe Punkty
- (punkt 1)
- (punkt 2)

## Szczegółowa Treść
(uporządkowana treść)

## Wnioski / Następne Kroki
(jeśli wynikają z treści, w przeciwnym razie pomiń tę sekcję)

Zasady:
- Pisz po polsku
- NIE dodawaj informacji od siebie — używaj tylko tego, co jest w tekście
- Popraw błędy gramatyczne i interpunkcyjne

TEKST DO PRZETWORZENIA:

{text}"""


async def structure_note(text: str) -> str:
    """Send text to PLLuM via Ollama and get a structured note back."""
    today = datetime.now().strftime("%Y-%m-%d")
    user_message = NOTE_TEMPLATE.format(date=today, text=text)

    logger.info("Sending text to PLLuM (%d chars)", len(text))

    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": NOTE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 4096,
                    "top_p": 0.9,
                },
            },
        )
        response.raise_for_status()
        data = response.json()

    raw = data.get("message", {}).get("content", "").strip()
    cleaned = _clean_note_output(raw)
    logger.info("PLLuM response: %d chars raw -> %d chars cleaned", len(raw), len(cleaned))
    logger.debug("PLLuM raw output:\n%s", raw[:500])
    return cleaned


def _clean_note_output(text: str) -> str:
    """Strip any preamble before the first Markdown heading."""
    # Find the first ## or ### heading
    match = re.search(r'^(#{2,3}\s)', text, re.MULTILINE)
    if match:
        text = text[match.start():]
    # Normalize ### to ## for consistency
    text = re.sub(r'^###\s', '## ', text, flags=re.MULTILINE)
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
