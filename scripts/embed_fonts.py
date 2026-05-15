"""Download the latin subset of the report fonts (Inter + Space Grotesk)
and emit a single self-contained CSS block with the WOFF2 files embedded
as base64 data URIs.

Output: ``wind_calculator/fonts_embedded.css`` (read at runtime by report.py).
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
GOOGLE_CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@300;400;500;600;700"
    "&family=Space+Grotesk:wght@500;600;700"
    "&display=swap"
)

# Only the 'latin' subset: covers U+0000-00FF (every Spanish accent + ñ + ¿¡)
# plus standard punctuation including em/en dashes.
LATIN_SUBSET_MARKERS = ["U+0000-00FF"]


def fetch_css() -> str:
    r = requests.get(GOOGLE_CSS_URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def parse_latin_blocks(css: str) -> list[dict]:
    pattern = re.compile(
        r"@font-face\s*\{[^}]*?font-family:\s*'([^']+)'"
        r"[^}]*?font-weight:\s*(\d+)"
        r"[^}]*?src:\s*url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\)"
        r"[^}]*?unicode-range:\s*([^;]+);[^}]*?\}",
        re.DOTALL,
    )
    blocks = []
    for m in pattern.finditer(css):
        family, weight, url, urange = m.group(1), m.group(2), m.group(3), m.group(4)
        if any(marker in urange for marker in LATIN_SUBSET_MARKERS):
            blocks.append({"family": family, "weight": int(weight), "url": url, "range": urange.strip()})
    return blocks


def download_woff2(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    return r.content


def build_css(blocks: list[dict]) -> str:
    out = ["/* Self-contained Latin subset of Inter + Space Grotesk (auto-generated) */"]
    for b in blocks:
        woff = download_woff2(b["url"])
        b64 = base64.b64encode(woff).decode("ascii")
        size_kb = len(woff) / 1024
        out.append(
            f"@font-face{{"
            f"font-family:'{b['family']}';"
            f"font-style:normal;"
            f"font-weight:{b['weight']};"
            f"font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
            f"unicode-range:{b['range']};"
            f"}}"
        )
        print(f"  {b['family']} {b['weight']} ({size_kb:.1f} KB)")
    return "\n".join(out) + "\n"


def main() -> int:
    print("Fetching Google Fonts CSS...")
    css = fetch_css()
    blocks = parse_latin_blocks(css)
    print(f"Found {len(blocks)} latin font-faces")
    print("Downloading and embedding WOFF2:")
    embedded = build_css(blocks)
    out_path = Path(__file__).resolve().parent.parent / "wind_calculator" / "fonts_embedded.css"
    out_path.write_text(embedded, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"\nWritten {out_path} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
