import logging
from pathlib import Path

import docx
import markdown
import weasyprint

logger = logging.getLogger(__name__)


def export_markdown(note_text: str, output_path: Path) -> Path:
    """Save note as Markdown file."""
    output_path = output_path.with_suffix(".md")
    output_path.write_text(note_text, encoding="utf-8")
    return output_path


def export_pdf(note_text: str, output_path: Path) -> Path:
    """Convert Markdown note to PDF."""
    output_path = output_path.with_suffix(".pdf")
    html_content = markdown.markdown(note_text, extensions=["extra", "sane_lists"])
    full_html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        max-width: 800px;
        margin: 40px auto;
        padding: 0 20px;
        line-height: 1.6;
        color: #1a1a1a;
        font-size: 14px;
    }}
    h1, h2, h3 {{ color: #2c3e50; margin-top: 1.5em; }}
    h2 {{ border-bottom: 1px solid #eee; padding-bottom: 0.3em; }}
    ul {{ padding-left: 1.5em; }}
    li {{ margin-bottom: 0.3em; }}
    code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
</style>
</head>
<body>{html_content}</body>
</html>"""
    weasyprint.HTML(string=full_html).write_pdf(str(output_path))
    return output_path


def export_docx(note_text: str, output_path: Path) -> Path:
    """Convert Markdown note to DOCX."""
    output_path = output_path.with_suffix(".docx")
    doc = docx.Document()

    for line in note_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith("- "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        elif stripped.startswith("* "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        else:
            doc.add_paragraph(stripped)

    doc.save(str(output_path))
    return output_path


EXPORTERS = {
    "md": export_markdown,
    "pdf": export_pdf,
    "docx": export_docx,
}


def export_note(note_text: str, output_path: Path, fmt: str) -> Path:
    """Export note to the specified format."""
    exporter = EXPORTERS.get(fmt)
    if not exporter:
        raise ValueError(f"Unsupported export format: {fmt}. Use: {list(EXPORTERS.keys())}")
    result = exporter(note_text, output_path)
    logger.info("Exported note to %s (%d bytes)", result.name, result.stat().st_size)
    return result
