"""
Renders a report context (from app.reporting.builder) to HTML and PDF.

Uses xhtml2pdf as the HTML->PDF backend, not WeasyPrint: WeasyPrint
needs the GTK3 native runtime (Pango/Cairo/GObject) which isn't present
on this machine and would require a system-level installer to add -
not something to pull in unprompted, especially when the brief already
flagged this exact swap as acceptable ("WeasyPrint, or similar").
xhtml2pdf is pure Python, no native dependency, and keeps the same
Jinja2-template-driven architecture the brief asked for.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


def render_html(context: dict, template_name: str = "report.html") -> str:
    template = _env.get_template(template_name)
    return template.render(**context)


def render_pdf(html: str, output_path: str | Path) -> tuple[bool, list[str]]:
    """Returns (success, error_log). A PDF generation failure is
    reported, not silently swallowed - the caller decides whether an
    HTML-only fallback is acceptable for that run."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    errors = [f"xhtml2pdf reported {result.err} error(s) during PDF generation"] if result.err else []
    return (not result.err, errors)


def render_report(context: dict, output_basename: str | Path) -> dict:
    """Writes both <basename>.html and <basename>.pdf. Returns a small
    status dict rather than raising on a PDF failure, so a broken PDF
    backend never silently costs you the HTML version too."""
    output_basename = Path(output_basename)
    html = render_html(context)

    html_path = output_basename.with_suffix(".html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")

    pdf_path = output_basename.with_suffix(".pdf")
    pdf_ok, pdf_errors = render_pdf(html, pdf_path)

    return {
        "html_path": str(html_path),
        "pdf_path": str(pdf_path) if pdf_ok else None,
        "pdf_errors": pdf_errors,
    }
