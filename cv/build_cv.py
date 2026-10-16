#!/usr/bin/env python3
"""Build cv/P_Krishna_Chaitanya_CV.pdf (one A4 page) from cv/cv.md.

Run from anywhere:  python3 cv/build_cv.py
Needs:              pip install reportlab

The script reads cv.md, then tries slightly smaller type sizes until
everything fits on ONE page. Content is never cut.
"""
import re
import sys
from pathlib import Path

from reportlab.lib.colors import black
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

HERE = Path(__file__).resolve().parent
SRC = HERE / "cv.md"
OUT = HERE / "P_Krishna_Chaitanya_CV.pdf"

# Chemical formulas get real subscripts (Helvetica has no subscript characters).
SUBS = {
    "K0.5Na0.5NbO3": "K<sub>0.5</sub>Na<sub>0.5</sub>NbO<sub>3</sub>",
    "K2Nb4O11": "K<sub>2</sub>Nb<sub>4</sub>O<sub>11</sub>",
}


def inline(text: str) -> str:
    """Markdown inline (bold, italic) -> ReportLab mini-HTML."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for plain, rich in SUBS.items():
        text = text.replace(plain, rich)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text


def parse(md: str):
    """Return a list of (kind, text) tuples: h1, h2, p, li."""
    blocks = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            blocks.append(("gap", ""))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:]))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:]))
        elif line.startswith("- "):
            blocks.append(("li", line[2:]))
        else:
            blocks.append(("p", line))
    return blocks


def build(font: float, gap: float, margin_mm: float) -> int:
    lead = font * 1.25
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=font, leading=lead, alignment=TA_LEFT)
    name = ParagraphStyle("name", parent=body, fontName="Helvetica-Bold", fontSize=font * 2.0, leading=font * 2.2)
    contact = ParagraphStyle("contact", parent=body, fontSize=font * 0.95, spaceAfter=gap * 0.5)
    head = ParagraphStyle("head", parent=body, fontName="Helvetica-Bold", fontSize=font * 1.08, leading=font * 1.3,
                          spaceBefore=gap * 1.5, spaceAfter=0)
    item = ParagraphStyle("item", parent=body, spaceAfter=gap * 0.25)
    # lines holding chemical subscripts need a little extra height so they never touch the next line
    item_sub = ParagraphStyle("item_sub", parent=item, leading=font * 1.42)

    story, bullets, first_p_after_h1 = [], [], True

    def flush():
        nonlocal bullets
        if bullets:
            story.append(ListFlowable(
                [ListItem(Paragraph(inline(t), item_sub if "<sub>" in inline(t) else item), leftIndent=11, value="•") for t in bullets],
                bulletType="bullet", start="•", leftIndent=11, bulletFontSize=font * 0.9, bulletOffsetY=0,
            ))
            bullets = []

    for kind, text in parse(SRC.read_text(encoding="utf-8")):
        if kind == "li":
            bullets.append(text)
            continue
        flush()
        if kind == "h1":
            story.append(Paragraph(inline(text), name))
        elif kind == "h2":
            story.append(Paragraph(inline(text.upper()), head))
            story.append(HRFlowable(width="100%", thickness=0.5, color=black, spaceBefore=1.5, spaceAfter=gap * 0.7))
        elif kind == "p":
            style = contact if first_p_after_h1 else ParagraphStyle("p", parent=body, spaceAfter=gap * 0.15)
            first_p_after_h1 = False
            story.append(Paragraph(inline(text), style))
    flush()

    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4, title="P. Krishna Chaitanya - CV", author="P. Krishna Chaitanya",
        leftMargin=margin_mm * mm, rightMargin=margin_mm * mm, topMargin=margin_mm * mm, bottomMargin=margin_mm * mm,
    )
    doc.build(story)
    return doc.page  # number of the last page built = page count


def main():
    # Try the roomiest settings first, then tighten spacing, then type size.
    fonts = [round(10.0 - 0.1 * i, 1) for i in range(0, 21)]  # 10.0 pt down to 8.0 pt
    for font in fonts:
        for gap, margin in ((5.0, 15), (4.5, 14.5), (4.0, 14), (3.5, 13.5), (3.0, 13), (2.5, 12.5), (2.0, 12), (1.5, 11.5), (1.5, 11)):
            pages = build(font, gap, margin)
            if pages == 1:
                print(f"OK: 1 page (font {font} pt, gap {gap}, margin {margin} mm) -> {OUT}")
                return
    sys.exit("Could not fit on one page even at the smallest settings.")


if __name__ == "__main__":
    main()
