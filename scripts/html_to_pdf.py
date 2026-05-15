"""Render an HTML report to a print-ready PDF using headless Chromium
(via Playwright), preserving the full visual identity (embedded fonts,
mermaid diagrams, base64 figures, page breaks).

Usage:
    python scripts/html_to_pdf.py path/to/file.html [path/to/file.html ...]
    python scripts/html_to_pdf.py --output-dir <dir> file1.html file2.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def render(html_path: Path, pdf_path: Path) -> Path:
    url = html_path.resolve().as_uri()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle")

        # Mermaid renders asynchronously after DOMContentLoaded; give it a
        # generous beat to settle before printing.
        page.wait_for_function(
            "document.fonts && document.fonts.ready",
            timeout=15000,
        )
        page.wait_for_timeout(2500)

        page.emulate_media(media="print")
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            # Margins are controlled by the @page CSS rules in the document
            # so that the cover can be full-bleed and the body has proper margins.
        )
        browser.close()
    return pdf_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="HTML file(s) to render")
    parser.add_argument("--output-dir", default=None,
                        help="If provided, PDFs go here; otherwise next to each HTML")
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir).resolve() if args.output_dir else None
    for html_str in args.inputs:
        html = Path(html_str).resolve()
        if not html.exists():
            print(f"!! No existe: {html}", file=sys.stderr)
            continue
        pdf = (out_dir / html.with_suffix(".pdf").name) if out_dir else html.with_suffix(".pdf")
        print(f"Rendering {html.name} → {pdf.name} ...")
        render(html, pdf)
        size_mb = pdf.stat().st_size / 1_000_000
        print(f"  OK · {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
