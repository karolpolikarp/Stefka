import logging
import re
from collections import Counter
from datetime import date

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 400

SUMMARIZE_PROMPT = """\
Streść poniższy fragment spotkania w akapitach. \
Zachowaj imiona, nazwiska, daty, kwoty, nazwy. \
Nie anonimizuj. Nie pisz dialogu. Nie kopiuj surowego tekstu. Zacznij od treści."""


async def structure_note(text: str, on_progress=None) -> str:
    """Process text into a structured note.

    MVP approach: chunk → summarize each → assemble in code.
    No LLM merge step. No fancy parsing. Just simple summaries.
    """
    chunks = _split_into_chunks(text, CHUNK_SIZE)
    total = len(chunks)
    logger.info("Processing %d chars in %d chunks", len(text), total)

    # Merge small last chunk into previous one
    if len(chunks) > 1 and len(chunks[-1]) < CHUNK_SIZE * 0.4:
        chunks[-2] = chunks[-2] + " " + chunks[-1]
        chunks.pop()
        total = len(chunks)
        logger.info("Merged small last chunk, now %d chunks", total)

    summaries = []
    for i, chunk in enumerate(chunks):
        if on_progress:
            on_progress(f"PLLuM analizuje fragment {i + 1}/{total}...")
        logger.info("Summarizing chunk %d/%d (%d chars)", i + 1, total, len(chunk))

        summary = await _call_ollama(SUMMARIZE_PROMPT, chunk)
        summary = _clean_response(summary, input_text=chunk)
        logger.info("Chunk %d summary: %d chars", i + 1, len(summary))

        if summary:
            summaries.append(summary)

    if not summaries:
        return "_Nie udało się przetworzyć transkrypcji._"

    note = _assemble_note(summaries)
    logger.info("Note assembled: %d chars from %d chunk summaries", len(note), len(summaries))
    return note


def _split_into_chunks(text: str, max_size: int) -> list[str]:
    """Split text at sentence boundaries with overlap."""
    if len(text) <= max_size:
        return [text]

    chunks = []
    pos = 0
    while pos < len(text):
        end = pos + max_size
        if end >= len(text):
            chunks.append(text[pos:].strip())
            break

        cut = end
        for sep in ['. ', '? ', '! ']:
            found = text.rfind(sep, pos, end)
            if found > pos + max_size * 0.3:
                cut = found + len(sep)
                break

        chunks.append(text[pos:cut].strip())
        pos = max(cut - CHUNK_OVERLAP, pos + 1)

    return chunks


def _assemble_note(summaries: list[str]) -> str:
    """Assemble final note from chunk summaries. Pure code, no LLM."""
    today = date.today().strftime("%Y-%m-%d")
    parts = []

    parts.append(f"## NOTATKA SŁUŻBOWA\n\n**Data przetworzenia:** {today}")

    # Join all summaries as continuous content, separated by blank lines
    content = '\n\n'.join(summaries)

    # Collapse short single-sentence paragraphs into previous paragraph
    content = _collapse_short_paragraphs(content)

    parts.append(content)

    return '\n\n---\n\n'.join(parts)


def _collapse_short_paragraphs(text: str) -> str:
    """Merge orphan paragraphs (1 short sentence) into the preceding paragraph.

    A paragraph qualifies as "short orphan" when it:
    - is a single sentence (no sentence-ending punctuation except at the very end)
    - is at most 80 characters long
    - is not a heading (doesn't start with #)
    - is not a list item (doesn't start with - or *)
    """
    paragraphs = text.split('\n\n')
    if len(paragraphs) <= 1:
        return text

    merged: list[str] = [paragraphs[0]]

    for para in paragraphs[1:]:
        stripped = para.strip()
        if not stripped:
            continue

        is_short_single = (
            len(stripped) <= 80
            and not stripped.startswith('#')
            and not stripped.startswith('-')
            and not stripped.startswith('*')
            and not stripped.startswith('|')  # table rows
            # Single sentence: no mid-text sentence endings
            and not re.search(r'[.!?]\s+[A-ZĄĆĘŁŃÓŚŹŻ]', stripped)
        )

        if is_short_single and merged:
            # Append to previous paragraph with a space
            merged[-1] = merged[-1].rstrip() + ' ' + stripped
        else:
            merged.append(para)

    return '\n\n'.join(merged)


def _clean_response(text: str, input_text: str = "") -> str:
    """Clean LLM response: strip artifacts, dialogue format, raw copies."""
    text = re.sub(r'\[/?INST\]', '', text)

    # Strip preambles
    text = re.sub(
        r'^(Oto |Poniżej |Streszczenie|Podsumowanie|W trakcie spotkania)[^\n]*\n*',
        '', text, flags=re.IGNORECASE,
    )

    # Strip trailing meta-commentary
    text = re.sub(
        r'\n(?:Ta notatka|Powyższe|Notatka sporządzona|Notatka została|Powyższy tekst|'
        r'Ponadto,? uczestnicy).*$',
        '', text, flags=re.DOTALL,
    )

    # Remove dialogue format lines: [Osoba 1]: ..., [Imię]: ...
    text = re.sub(r'^\[(?:Osoba\s*\d*|Imię|Nieznane imię|osoba)\][:\s].*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # Remove [Osoba], [Osoba N], [Imię] inline
    text = re.sub(r'\[Osoba\s*\d*\]', '', text)
    text = re.sub(r'\[(?:Nieznane |nieznane )?[Ii]mię\]', '', text)
    text = re.sub(r'\[(?:Twoje |twoje )?imię[^]]*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[Podpis\]', '', text, flags=re.IGNORECASE)

    # Strip email/letter artifacts
    text = re.sub(r'^Dzień dobry[,!.]?\s*\n*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n(?:Z poważaniem|Pozdrawiam|Dziękuję za)[,.]?\s*\n.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'\n(?:Dziękuję za Twoją uwagę).*$', '', text, flags=re.DOTALL)

    # --- Strip repeated "W trakcie spotkania poruszono" preambles ---
    # Keep the first occurrence, remove subsequent paragraph-starting ones
    _preamble_pat = re.compile(
        r'(?:^|\n\n)W trakcie spotkania poruszono[^\n]*',
        flags=re.IGNORECASE,
    )
    _first_preamble_seen = False

    def _dedup_preamble(m: re.Match) -> str:
        nonlocal _first_preamble_seen
        if not _first_preamble_seen:
            _first_preamble_seen = True
            return m.group(0)
        return m.group(0)[:m.group(0).index('W')] if '\n' in m.group(0) else ''

    text = _preamble_pat.sub(_dedup_preamble, text)

    # --- Strip generic filler sentences ---
    _filler_patterns = [
        r'Podczas spotkania poruszono wiele tematów\.?',
        r'Wszystkie te tematy są istotne\.?',
        r'Powyższe tematy były szeroko dyskutowane\.?',
        r'Spotkanie dotyczyło wielu ważnych kwestii\.?',
        r'Omówiono szereg istotnych zagadnień\.?',
        r'Dyskusja dotyczyła wielu aspektów\.?',
        r'Poruszono wiele istotnych kwestii\.?',
        r'Tematy te są niezwykle ważne dla dalszych prac\.?',
    ]
    for pat in _filler_patterns:
        text = re.sub(r'(?:^|\n)\s*' + pat + r'\s*(?=\n|$)', '', text, flags=re.IGNORECASE)

    # --- Remove hallucinated names not present in input text ---
    if input_text:
        text = _remove_hallucinated_names(text, input_text)

    # Detect raw transcription copy — if >50% of output chars appear verbatim in input
    if input_text and len(text) > 200:
        # Check if output is just a copy of input
        overlap = _text_overlap_ratio(input_text, text)
        if overlap > 0.6:
            logger.warning("Output appears to be raw copy of input (%.0f%% overlap), discarding", overlap * 100)
            return ""

    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_names_from_text(text: str) -> set[str]:
    """Extract capitalized multi-word names (potential proper names) from text."""
    # Match sequences of 2-4 capitalized words that look like names
    # e.g. "Jan Kowalski", "Anna Maria Nowak"
    pattern = re.compile(r'\b([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+){1,3})\b')
    candidates = set()
    for m in pattern.finditer(text):
        name = m.group(1)
        # Filter out common Polish phrases that look like names but aren't
        words = name.split()
        if all(len(w) >= 2 for w in words):
            candidates.add(name)
    return candidates


def _remove_hallucinated_names(output: str, source: str) -> str:
    """Remove person names from output that don't appear in source text.

    Targets patterns like 'Jan Kowalski' — capitalized first + last name
    that the LLM invented. Single capitalized words (city names, common
    nouns) are left alone to avoid false positives.
    """
    source_lower = source.lower()
    source_names = _extract_names_from_text(source)
    source_names_lower = {n.lower() for n in source_names}

    output_names = _extract_names_from_text(output)

    for name in output_names:
        if name.lower() not in source_names_lower and name.lower() not in source_lower:
            # This name was hallucinated — remove it from output
            # Replace "Name" with empty string, clean up leftover artifacts
            logger.info("Removing hallucinated name: %s", name)
            output = output.replace(name, '')

    # Clean up artifacts from name removal: double spaces, orphaned commas, empty parens
    output = re.sub(r'  +', ' ', output)
    output = re.sub(r'\(\s*\)', '', output)
    output = re.sub(r',\s*,', ',', output)
    output = re.sub(r'^\s*,\s*', '', output, flags=re.MULTILINE)
    output = re.sub(r',\s*\.', '.', output)

    return output


def _text_overlap_ratio(source: str, output: str) -> float:
    """Estimate how much of output is verbatim from source."""
    # Quick check: compare 50-char windows
    if len(output) < 100:
        return 0.0
    window = 50
    matches = 0
    total = 0
    for i in range(0, len(output) - window, window):
        chunk = output[i:i + window]
        total += 1
        if chunk in source:
            matches += 1
    return matches / total if total > 0 else 0.0


async def _call_ollama(
    system: str,
    user: str,
    num_predict: int = 4096,
    temperature: float = 0.0,
) -> str:
    """Call Ollama. temperature=0 for deterministic output."""
    last_result = ""
    for attempt in range(1, MAX_RETRIES + 2):
        async with httpx.AsyncClient(timeout=300.0) as client:
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
                        "temperature": temperature,
                        "num_predict": num_predict,
                        "num_ctx": 16384,
                        "top_p": 0.7,
                        "repeat_penalty": 1.1,
                        "repeat_last_n": 128,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
        result = data.get("message", {}).get("content", "").strip()
        last_result = result

        if len(result) >= 50 and not _is_garbage(result):
            return result

        logger.warning("LLM attempt %d: poor response (%d chars)", attempt, len(result))
        temperature = min(temperature + 0.1, 0.3)

    return last_result


def _is_garbage(text: str) -> bool:
    """Detect degenerate output."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) >= 5:
        counts = Counter(lines)
        if counts.most_common(1)[0][1] > len(lines) * 0.5:
            return True
    if re.search(r'(.)\1{20,}', text):
        return True
    if re.search(r'(\b\w+\b)(?:\s+\1){5,}', text):
        return True
    return False


async def check_ollama_health() -> bool:
    """Check if Ollama is running and model available."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            names = [m.get("name", "") for m in models]
            ok = any(OLLAMA_MODEL.lower() in n.lower() for n in names)
            if not ok:
                logger.warning("Model %s not found (available: %s)", OLLAMA_MODEL, names)
            return ok
    except Exception as e:
        logger.warning("Ollama health check failed: %s", e)
        return False
