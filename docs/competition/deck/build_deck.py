#!/usr/bin/env python3
"""Build the tyche competition deck (34 slides, 16:9) as an editable .pptx.

    C:/Users/alois/deck-venv/Scripts/python.exe docs/competition/deck/build_deck.py

Writes only `tyche-competition-deck.pptx` next to this file. Every number and claim is
taken from repository documents (docs/competition/rules.md, documentation/PRD.md,
docs/agent-engineering.md, docs/risk-card.md, playbook/, docs/validation/,
docs/performance/2026-11-23-metrics.md, desk-site/web/data/state.json). A fact that the
record does not carry is printed as "not recorded" rather than estimated.

The script also runs a text-fit audit while it builds (see FIT) and prints the result, so
a slide whose text cannot fit its box fails loudly instead of shipping clipped words.
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

OUT = Path(__file__).with_name("tyche-competition-deck.pptx")

# ---------------------------------------------------------------- design tokens
DARK = RGBColor(0x1E, 0x3A, 0x2F)      # title / divider / closing background
DARK_PANEL = RGBColor(0x2A, 0x4C, 0x3E)  # card fill on a dark slide
DARK_EDGE = RGBColor(0x3F, 0x66, 0x57)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x2E, 0x7D, 0x5B)
AMBER = RGBColor(0xC9, 0x8A, 0x1B)
BLUE = RGBColor(0x3C, 0x6E, 0x9E)
BRICK = RGBColor(0xB0, 0x4A, 0x3C)
INK = RGBColor(0x1C, 0x28, 0x22)        # body text on white
MUT = RGBColor(0x5B, 0x6B, 0x63)        # secondary text
LINE = RGBColor(0xD8, 0xDF, 0xDA)
T_GREEN = RGBColor(0xEC, 0xF4, 0xF0)
T_AMBER = RGBColor(0xFC, 0xF4, 0xE4)
T_BLUE = RGBColor(0xEC, 0xF2, 0xF8)
T_BRICK = RGBColor(0xFA, 0xEE, 0xEB)
T_GRAY = RGBColor(0xF3, 0xF5, 0xF4)
OFFWHITE = RGBColor(0xE8, 0xEF, 0xEA)

HEAD = "Cambria"
BODY = "Calibri"

SW, SH = 13.333, 7.5      # slide size, inches (16:9)
M = 0.5                   # page margin
CW = SW - 2 * M           # content width

# Text metrics for the fit audit: average glyph width as a fraction of the font size.
_GLYPH = {BODY: 0.492, HEAD: 0.535, "Consolas": 0.55}
LINE_H = 1.22             # single-spaced line height as a fraction of the font size

FIT: list[str] = []
_CTX = {"slide": 0}
SIZED: list[list] = []        # [slide number, shape, height the text actually needs]


# ---------------------------------------------------------------- small helpers
def _lines(text: str, w_in: float, pt: float, bold: bool = False, font: str = BODY) -> int:
    """Greedy word-wrap line count for `text` inside a box `w_in` inches wide."""
    if text is None or str(text) == "":
        return 1
    cw = pt * _GLYPH.get(font, 0.5) / 72.0 * (1.03 if bold else 1.0)
    per = max(int((w_in - 0.14) / cw), 3)
    n, cur = 1, 0
    for word in str(text).split():
        ln = len(word)
        if cur == 0:
            cur = ln
        elif cur + 1 + ln <= per:
            cur += 1 + ln
        else:
            n += 1
            cur = ln
    return n


def _fit(tag: str, needed: float, have: float) -> None:
    if needed > have + 0.005:
        FIT.append(f"slide {_CTX['slide']:>2}  {tag:<34} needs {needed:5.2f}in, box {have:5.2f}in")


def para_height(paras: list[dict], w_in: float) -> float:
    h = 0.0
    for p in paras:
        n = _lines(p["t"], w_in, p["size"], p.get("bold", False), p.get("font", BODY))
        h += n * p["size"] * LINE_H * p.get("line", 1.0) / 72.0
        h += p.get("before", 0.0) / 72.0 + p.get("after", 0.0) / 72.0
    return h


def _fill_paras(tf, paras: list[dict], w_in: float, anchor=MSO_ANCHOR.TOP) -> None:
    tf.word_wrap = True
    tf.margin_left = Inches(0.02)
    tf.margin_right = Inches(0.02)
    tf.margin_top = Inches(0.01)
    tf.margin_bottom = Inches(0.01)
    tf.vertical_anchor = anchor
    first = True
    for p in paras:
        par = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        par.alignment = p.get("align", PP_ALIGN.LEFT)
        par.line_spacing = p.get("line", 1.0)
        if p.get("before"):
            par.space_before = Pt(p["before"])
        if p.get("after"):
            par.space_after = Pt(p["after"])
        run = par.add_run()
        run.text = str(p["t"])
        f = run.font
        f.size = Pt(p["size"])
        f.bold = p.get("bold", False)
        f.italic = p.get("italic", False)
        f.name = p.get("font", BODY)
        f.color.rgb = p.get("color", INK)


def txt(slide, x, y, w, h, paras, tag="", anchor=MSO_ANCHOR.TOP) -> float:
    """Free text box. `paras` is a list of dicts (t, size, color, bold, font, align, ...)."""
    if isinstance(paras, dict):
        paras = [paras]
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    _fill_paras(box.text_frame, paras, w, anchor)
    needed = sum(
        _lines(p["t"], w, p["size"], p.get("bold", False), p.get("font", BODY))
        * p["size"] * LINE_H * p.get("line", 1.0) / 72.0
        + p.get("before", 0.0) / 72.0 + p.get("after", 0.0) / 72.0
        for p in paras
    )
    _fit(tag or "txt", needed, h)
    return y + max(needed, h)


def P(t, size=11, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT, line=1.06,
      before=0.0, after=0.0, italic=False) -> dict:
    # body copy is specced at 10-13 pt; the monospace code block on slide 30 is the one
    # exception, and table cells and chart labels set their own sizes elsewhere
    if font in (BODY, HEAD):
        size = max(size, 10.0)
    return {"t": t, "size": size, "color": color, "bold": bold, "font": font,
            "align": align, "line": line, "before": before, "after": after, "italic": italic}


def shape(slide, kind, x, y, w, h, fill=None, line=None, line_w=0.75, radius=None, shadow=False):
    sp = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    if radius is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            sp.adjustments[0] = radius
        except Exception:
            pass
    return sp


def box(slide, x, y, w, h, paras, fill=WHITE, line=LINE, radius=0.05, tag="", anchor=MSO_ANCHOR.TOP,
        pad=0.09, line_w=0.75):
    """Rounded card with text inside it. Text area = box minus horizontal/vertical padding."""
    sp = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill=fill, line=line, line_w=line_w,
               radius=radius)
    tf = sp.text_frame
    _fill_paras(tf, paras if isinstance(paras, list) else [paras], w - 2 * pad, anchor)
    tf.margin_left = Inches(pad)
    tf.margin_right = Inches(pad)
    tf.margin_top = Inches(pad * 0.7)
    tf.margin_bottom = Inches(pad * 0.7)
    needed = para_height(paras if isinstance(paras, list) else [paras], w - 2 * pad) + 2 * pad * 0.7
    _fit(tag or "box", needed, h)
    SIZED.append([_CTX["slide"], sp, needed])
    return sp


def arrow_r(slide, x, y, w=0.30, h=0.20, color=GREEN):
    return shape(slide, MSO_SHAPE.RIGHT_ARROW, x, y, w, h, fill=color)


def arrow_d(slide, x, y, w=0.26, h=0.30, color=GREEN):
    return shape(slide, MSO_SHAPE.DOWN_ARROW, x, y, w, h, fill=color)


NO_STYLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # "No Style, No Grid"


def table(slide, x, y, w, headers, rows, widths, font=10.0, head_font=10.0, tag="",
          aligns=None, row_pad=0.10, head_fill=DARK, zebra=True, bold_col0=False,
          max_h=None, cell_colors=None):
    """Plain-styled table with explicit fills. Returns the height actually needed."""
    ncol = len(headers)
    scale = w / sum(widths)
    col_w = [c * scale for c in widths]
    aligns = aligns or [PP_ALIGN.LEFT] * ncol

    def row_h(cells, size):
        return max(
            _lines(c, col_w[i] - 0.16, size, bold=(i == 0 and bold_col0)) * size * LINE_H / 72.0
            for i, c in enumerate(cells)
        ) + row_pad

    h_head = row_h(headers, head_font)
    heights = [h_head] + [row_h(r, font) for r in rows]
    need = sum(heights)
    if max_h and need > max_h:
        _fit(tag or "table", need, max_h)

    shp = slide.shapes.add_table(len(rows) + 1, ncol, Inches(x), Inches(y), Inches(w), Inches(need))
    tbl = shp.table
    tblPr = tbl._tbl.find(qn("a:tblPr"))
    if tblPr is not None:
        for e in tblPr.findall(qn("a:tableStyleId")):
            tblPr.remove(e)
        el = etree.SubElement(tblPr, qn("a:tableStyleId"))
        el.text = NO_STYLE
        for a in ("firstRow", "bandRow"):
            tblPr.set(a, "0")
    tbl.first_row = False
    tbl.horz_banding = False
    for i, cwid in enumerate(col_w):
        tbl.columns[i].width = Inches(cwid)
    for i, ht in enumerate(heights):
        tbl.rows[i].height = Inches(ht)

    def put(r, c, text, size, bold, color, fill, align):
        cell = tbl.cell(r, c)
        cell.margin_left = Inches(0.07)
        cell.margin_right = Inches(0.06)
        cell.margin_top = Inches(row_pad * 0.35)
        cell.margin_bottom = Inches(row_pad * 0.35)
        cell.vertical_anchor = MSO_ANCHOR.TOP
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
        tf = cell.text_frame
        tf.word_wrap = True
        par = tf.paragraphs[0]
        par.alignment = align
        par.line_spacing = 1.0
        run = par.add_run()
        run.text = str(text)
        f = run.font
        f.size = Pt(size)
        f.bold = bold
        f.name = BODY
        f.color.rgb = color

    for c, htext in enumerate(headers):
        put(0, c, htext, head_font, True, WHITE, head_fill, aligns[c])
    for r, row in enumerate(rows, start=1):
        base = WHITE if (not zebra or r % 2) else T_GRAY
        for c, val in enumerate(row):
            color = INK
            if cell_colors:
                color = cell_colors(r - 1, c, val) or INK
            put(r, c, val, font, bold_col0 and c == 0, color, base, aligns[c])
    return need


def notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def add_slide(prs, dark=False, bg=None):
    _CTX["slide"] += 1
    s = prs.slides.add_slide(prs.slide_layouts[6])
    fill = bg if bg is not None else (DARK if dark else WHITE)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = fill
    return s


def title(slide, text, sub=None, color=INK, sub_color=MUT, size=28):
    """Left-aligned slide title; returns the y where content may start."""
    box = slide.shapes.add_textbox(Inches(M), Inches(0.24), Inches(CW), Inches(0.62))
    _fill_paras(box.text_frame, [P(text, size=size, color=color, font=HEAD, bold=True, line=1.0)], CW)
    _fit("title", _lines(text, CW, size, True, HEAD) * size * LINE_H / 72.0, 0.62)
    y = 0.92
    if sub:
        sub_p = P(sub, size=11.5, color=sub_color, line=1.05)
        y = txt(slide, M, 0.86, CW, max(0.34, para_height([sub_p], CW)), [sub_p],
                tag="subtitle") + 0.06
    return y


def kicker(slide, text, color=OFFWHITE, size=11):
    txt(slide, M, 0.42, CW, 0.3, [P(text, size=size, color=color, bold=True, line=1.0)], tag="kicker")


def page_no(slide, n, dark=False):
    txt(slide, SW - M - 0.9, SH - 0.42, 0.9, 0.26,
        [P(str(n), size=10, color=(OFFWHITE if dark else MUT), align=PP_ALIGN.RIGHT, line=1.0)],
        tag="pageno")


def card(slide, x, y, w, h, head, lines, accent=GREEN, fill=T_GRAY, head_size=11.5,
         body_size=10.0, tag="", num=None, head_color=None, line_w=0.9, pad=0.11):
    """Small titled card: a heading line plus 1-4 short body lines."""
    paras = []
    if num is not None:
        paras.append(P(f"{num}", size=head_size, color=head_color or accent, bold=True,
                       font=HEAD, after=1.5, line=1.03))
    if head:
        paras.append(P(head, size=head_size, color=head_color or DARK, bold=True, font=HEAD,
                       after=1.5, line=1.05))
    for i, ln in enumerate(lines):
        if isinstance(ln, dict):
            paras.append(ln)
        else:
            paras.append(P(ln, size=body_size, color=INK, line=1.07,
                           after=0 if i == len(lines) - 1 else 1.5))
    sp = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill=fill, line=accent, line_w=line_w,
               radius=0.05)
    tf = sp.text_frame
    _fill_paras(tf, paras, w - 2 * pad)
    tf.margin_left = Inches(pad)
    tf.margin_right = Inches(pad)
    tf.margin_top = Inches(0.08)
    tf.margin_bottom = Inches(0.08)
    need = para_height(paras, w - 2 * pad) + 0.16
    _fit(tag or f"card:{(head or num or 'x')[:16]}", need, h)
    SIZED.append([_CTX["slide"], sp, need])
    return sp


def chart_base(ch, font=9.5, legend=False, legend_pos=XL_LEGEND_POSITION.BOTTOM):
    ch.has_title = False
    ch.has_legend = legend
    if legend:
        ch.legend.position = legend_pos
        ch.legend.include_in_layout = False
    ch.font.size = Pt(font)
    ch.font.name = BODY
    ch.font.color.rgb = INK


def axis_style(ch, val_fmt=None, vmin=None, vmax=None, grid=True, cat_size=None, cat_low=False):
    cat, val = ch.category_axis, ch.value_axis
    cat.has_major_gridlines = False
    cat.format.line.color.rgb = LINE
    cat.tick_labels.font.size = Pt(cat_size or 9.5)
    cat.tick_labels.font.color.rgb = INK
    if cat_low:
        # a value axis that spans zero puts the category labels on the axis itself; keep them at the
        # floor. python-pptx 1.0 has no TickLabels.position, so the c:tickLblPos attribute is set here
        pos = cat._element.find(qn("c:tickLblPos"))
        if pos is not None:
            pos.set("val", "low")
    val.has_major_gridlines = grid
    if grid:
        val.major_gridlines.format.line.color.rgb = RGBColor(0xE6, 0xEA, 0xE7)
        val.major_gridlines.format.line.width = Pt(0.5)
    val.tick_labels.font.size = Pt(9)
    val.tick_labels.font.color.rgb = MUT
    if val_fmt:
        val.tick_labels.number_format = val_fmt
        val.tick_labels.number_format_is_linked = False
    if vmin is not None:
        val.minimum_scale = vmin
    if vmax is not None:
        val.maximum_scale = vmax
    return val


def line_marker(ser, color, size=6):
    """python-pptx exposes markers only on xy series; a line series needs the XML by hand."""
    ser_el = ser._element
    for old in ser_el.findall(qn("c:marker")):
        ser_el.remove(old)
    mk = etree.SubElement(ser_el, qn("c:marker"))
    sym = etree.SubElement(mk, qn("c:symbol"))
    sym.set("val", "circle")
    sz = etree.SubElement(mk, qn("c:size"))
    sz.set("val", str(size))
    sp = etree.SubElement(mk, qn("c:spPr"))
    fill = etree.SubElement(sp, qn("a:solidFill"))
    clr = etree.SubElement(fill, qn("a:srgbClr"))
    clr.set("val", str(color))
    ln = etree.SubElement(sp, qn("a:ln"))
    lnfill = etree.SubElement(ln, qn("a:solidFill"))
    lnclr = etree.SubElement(lnfill, qn("a:srgbClr"))
    lnclr.set("val", str(color))
    sp_pr = ser_el.find(qn("c:spPr"))
    ser_el.remove(mk)
    if sp_pr is not None:
        sp_pr.addnext(mk)
    else:
        ser_el.insert(0, mk)


# ---------------------------------------------------------------- layout post-pass
def tighten(prs) -> int:
    """Cards are laid out on a fixed grid, which leaves a half-empty box whenever the text
    runs short. Shrink each row of cards to the tallest text in that row and lift what sits
    below it by half the space freed, so the boxes read as full and the slide keeps its frame.

    Two shapes are left alone: a container that has other shapes laid inside it, and a card
    that stands beside a different column of content - its height belongs to that row's
    structure, so shrinking it would open a hole next to its neighbour."""
    slides = list(prs.slides)
    bands: dict[tuple, list] = {}
    for n, sp, need in SIZED:
        if need < 0.25:
            continue
        key = (n, round(sp.top / 914400, 2), round(sp.height / 914400, 2))
        bands.setdefault(key, []).append((sp, need))

    def span(items):
        x0 = min(sp.left / 914400 for sp, _ in items)
        x1 = max(sp.left / 914400 + sp.width / 914400 for sp, _ in items)
        return x0, x1

    moved = 0
    for n in range(1, len(slides) + 1):
        sl = slides[n - 1]
        mine = sorted([(k[1:], v) for k, v in bands.items() if k[0] == n])
        rows = []
        for (top, h), items in mine:
            ids = {sp.shape_id for sp, _ in items}
            x0, x1 = span(items)
            blocked = False
            for o in sl.shapes:                       # a container, or a shape laid inside it
                if o.shape_id in ids or o.left is None:
                    continue
                ox0, oy0 = o.left / 914400, o.top / 914400
                ox1, oy1 = ox0 + o.width / 914400, oy0 + o.height / 914400
                if (ox0 > x0 - 0.06 and oy0 > top - 0.06
                        and ox1 < x1 + 0.06 and oy1 < top + h + 0.06):
                    blocked = True
            for (t2, h2), it2 in mine:                # a card that shares a row with a column
                if (t2, h2) == (top, h):
                    continue
                b0, b1 = span(it2)
                if (min(t2 + h2, top + h) - max(t2, top) > 0.15
                        and (x1 <= b0 + 0.05 or b1 <= x0 + 0.05)):
                    blocked = True
            new_h = max(need for _, need in items) + 0.10
            delta = 0.0 if blocked or h - new_h < 0.28 else h - new_h
            rows.append((top, h, items, new_h, delta))
        for top, h, items, new_h, delta in rows:
            shift = 0.5 * sum(r[4] for r in rows if r[0] + r[1] <= top - 0.02)
            for sp, _ in items:
                sp.top = Inches(top - shift)
                if delta:
                    sp.height = Inches(new_h)
                    moved += 1
        banded = {sp.shape_id for _, _, it, _, _ in rows for sp, _ in it}
        for o in sl.shapes:
            if o.shape_id in banded or o.top is None:
                continue
            y0 = o.top / 914400
            shift = 0.5 * sum(r[4] for r in rows if r[0] + r[1] <= y0 - 0.02)
            if shift:
                o.top = Inches(y0 - shift)
                moved += 1
    return moved


# ---------------------------------------------------------------- slide builders
def s01_title(prs):
    s = add_slide(prs, dark=True)
    txt(s, M + 0.35, 1.02, CW - 0.7, 0.32,
        [P("MOOMOO x QODER AI AGENT PAPER TRADING CHALLENGE", size=12, color=OFFWHITE, bold=True,
           line=1.0)], tag="s1 kicker")
    txt(s, M + 0.35, 1.42, CW - 0.7, 1.35,
        [P("Tyche", size=54, color=WHITE, bold=True, font=HEAD, line=1.0, after=6),
         P("A paper-trading desk where the AI advises, the code decides, and a human says yes.",
           size=17, color=OFFWHITE, line=1.12)], tag="s1 title")
    txt(s, M + 0.35, 3.30, 7.6, 1.9,
        [P("Agents research, critique and audit. They never size or send an order.", size=12.5,
           color=WHITE, line=1.14, after=6),
         P("Every order passes the same fixed risk kernel, then an approval written by a person.",
           size=12.5, color=WHITE, line=1.14, after=6),
         P("Every decision - including the ones refused - lands in a tamper-evident journal.",
           size=12.5, color=WHITE, line=1.14)], tag="s1 bullets")
    box(s, 8.7, 3.30, 4.13, 1.9,
        [P("This deck", size=11.5, color=WHITE, bold=True, font=HEAD, after=3),
         P("34 slides, built by code (python-pptx) from the files in the repository. "
           "Numbers come from the journal, the published desk data and the performance pack. "
           "A fact the record does not carry is printed as \"not recorded\".",
           size=10.5, color=OFFWHITE, line=1.1)], fill=DARK_PANEL, line=DARK_EDGE, tag="s1 side")
    txt(s, M + 0.35, 6.28, CW - 0.7, 0.62,
        [P("Competition window 17-28 Nov 2026   ·   deadline 30 Nov 2026 23:59 SGT   ·   "
           "github.com/aloisohzh/tyche   ·   Operator: Alois", size=11, color=OFFWHITE, line=1.1,
           after=3),
         P("Generated by Qoder.", size=11, color=AMBER, bold=True, line=1.05)], tag="s1 footer")
    notes(s, "This is Tyche, my entry for the Moomoo x Qoder AI Agent Paper Trading Challenge. "
             "One sentence describes the whole design: artificial intelligence advises, deterministic "
             "code decides, and a human approves. The agents write research, critiques and reports. "
             "They do not touch order sizing or submission, because that path is a Python program with "
             "fixed limits. Everything the desk decides, including the trades it refused, is written to "
             "a chain of journal records that cannot be edited quietly. The numbers in this deck come "
             "from files in the repository, so any judge can check them. If a number is missing from the "
             "record, the slide says so instead of guessing.")


def s02_one_minute(prs):
    s = add_slide(prs)
    y = title(s, "The one-minute version",
              "Four claims, weighted the way the rules weight them. Each claim has a slide and a file "
              "a judge can open.")
    tiles = [
        ("30%", "Qoder and Cloud Agent usage", GREEN, T_GREEN,
         ["One scheduled cloud card runs four agents three times a day.",
          "Eleven reusable skills, a hosted desk, and a Telegram approval step.",
          "Slides 5-17"]),
        ("30%", "Strategy and risk design", BLUE, T_BLUE,
         ["Five playbook lanes, each with a thesis, an edge and a written invalidation.",
          "One shared risk kernel: 20+ named limits, each proven by a test.",
          "Slides 18-24"]),
        ("25%", "Risk-adjusted return", AMBER, T_AMBER,
         ["Fee-net marks against an SPY buy-and-hold baseline.",
          "Four marks so far: desk -1.25% against SPY -5.82%. Small sample, labelled.",
          "Slides 25-28"]),
        ("15%", "Reusability and documentation", BRICK, T_BRICK,
         ["607 tests in CI, 18 architecture records, 56 lessons, 11 skills.",
          "Runs with demo data and no credentials.",
          "Slides 29-33"]),
    ]
    w, gap = (CW - 3 * 0.16) / 4, 0.16
    for i, (pct, head, acc, tint, lines) in enumerate(tiles):
        x = M + i * (w + gap)
        paras = [P(pct, size=26, color=acc, bold=True, font=HEAD, line=1.0, after=2),
                 P(head, size=12, color=DARK, bold=True, font=HEAD, line=1.05, after=6)]
        for ln in lines:
            last = ln.startswith("Slides")
            paras.append(P(ln, size=9.9, color=(MUT if last else INK), bold=last, line=1.08, after=4))
        card(s, x, y, w, 3.34, None, paras, accent=acc, fill=tint, head_size=12, body_size=9.9,
             tag=f"s2 tile {i}")
    txt(s, M, y + 3.52, CW, 0.72,
        [P("The rule that holds the four together: no model output can reach the broker. "
           "An order needs a passing risk verdict, a valid authorization written by the operator, "
           "and a reservation the kernel itself re-validated one second before it submitted.",
           size=11, color=INK, line=1.12)], tag="s2 bottom")
    notes(s, "If you remember one slide, remember this one. The competition scores four things, and I "
             "built the desk against those four weights rather than around a single trading idea. The "
             "biggest two are how the agents are used and how the strategy and risk are designed. The "
             "return number is honestly small so far, because the desk has only four daily marks, and I "
             "show it that way instead of dressing it up. The last tile is the part that is easy to skip: "
             "tests, records and lessons that let somebody else run this. The sentence at the bottom is "
             "the safety property behind all four, and slides 4 and 24 show where it is enforced.")


def s03_mapping(prs):
    s = add_slide(prs)
    y = title(s, "How this deck maps to the judging rubric",
              "The weights and wording are quoted from docs/competition/rules.md; the evidence paths are "
              "from docs/competition/scoring-map.md.")
    h = table(s, M, y, CW,
              ["Criterion (rules.md)", "Weight", "What the rules ask for", "Slides",
               "Where to check it in the repo"],
              [["Qoder and Cloud Agent usage", "30%",
                "Multi-agent topology, automation, dashboards, reports, reusable skills", "5-17",
                "docs/agent-engineering.md, scripts/deploy_two_fire_automation.py, skills/, desk-site/"],
               ["Strategy and risk design", "30%",
                "Thesis, edge, invalidation conditions, position limits, drawdown responses, kill switches",
                "18-24", "playbook/, config/risk.yaml, docs/risk-card.md, docs/validation/"],
               ["Risk-adjusted return", "25%",
                "Results after costs against a baseline, honestly labelled", "25-28",
                "docs/performance/2026-11-23-metrics.md, desk-site/web/data/state.json"],
               ["Reusability and documentation", "15%",
                "Reference-ready templates, skills and scripts, slides or report", "29-33",
                "README.md, documentation/PRD.md, docs/runbooks/, docs/lessons/LESSONS.md"]],
              [2.5, 0.75, 3.9, 0.8, 4.4], font=10, head_font=10.5, tag="s3 table",
              aligns=[PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.LEFT],
              bold_col0=True, max_h=2.9)
    y2 = y + h + 0.18
    txt(s, M, y2, CW, 0.28,
        [P("What the handbook asks a submission to contain, and where it is", size=12.5, color=DARK,
           bold=True, font=HEAD, line=1.0)], tag="s3 h2")
    items = [
        ("Qoder-generated deck", "this file, built by build_deck.py"),
        ("Runnable agent package", "slide 30"),
        ("Strategy explanation", "slides 19-21"),
        ("Risk limits", "slides 20 and 22"),
        ("Log of decisions, including rejections", "slides 16 and 28"),
        ("Fills and results", "slides 26-28"),
        ("What worked, what failed, and why", "slides 31-32"),
        ("Dashboard of the run", "slides 14-15"),
    ]
    cw = (CW - 3 * 0.14) / 4
    for i, (a, b) in enumerate(items):
        x = M + (i % 4) * (cw + 0.14)
        yy = y2 + 0.34 + (i // 4) * 0.62
        box(s, x, yy, cw, 0.56,
            [P(a, size=10, color=DARK, bold=True, line=1.05),
             P(b, size=9.8, color=MUT, line=1.05)], fill=T_GRAY, line=LINE, tag=f"s3 req {i}",
            pad=0.08)
    txt(s, M, y2 + 1.66, CW, 0.4,
        [P("Deadline 30 Nov 2026, 23:59 SGT. Early submission is allowed; the repo is public while the "
           "window runs and goes private after it (docs/competition/bonus-tips.md, section 4).",
           size=10, color=MUT, line=1.1)], tag="s3 foot")
    notes(s, "This table is the map for everything that follows. The first column is the criterion exactly "
             "as the rules state it, with the weight the handbook gives it. The third column is what the "
             "rules say they are looking for, so you can hold each slide against it. The last column is "
             "not a promise, it is a path: a judge can open those files in the repository and read them. "
             "Under the table I listed the eight things the handbook asks a submission to contain and "
             "pointed at the slide that answers each one. The deadline note is at the bottom. If a claim "
             "later in the deck is not backed by a file, I mark it as planned rather than done.")


def s04_one_rule(prs):
    s = add_slide(prs)
    y = title(s, "The one rule the whole system is built on",
              "\"Money decisions are made by deterministic code. An LLM may read state, write prose, "
              "critique a plan and be ignored - it may never size an order, approve a risk breach, or "
              "submit.\" (documentation/architecture.md, ADR 0001 and ADR 0006)")
    col_w, gap = (CW - 2 * 0.55) / 3, 0.28
    cols = [
        ("LLM agents", "words only", GREEN, T_GREEN,
         ["Research, critique, audit, narrative.",
          "No sizing. No submission. No risk override.",
          "Their output is an input to code, never a trade."]),
        ("Deterministic kernel", "the only path to a trade", BLUE, T_BLUE,
         ["risk.py: fixed limits, named breaches.",
          "approvals.py: operator bounds, same-day only.",
          "lifecycle.py: re-validate, then reserve.",
          "journal.py: SHA-256 hash chain."]),
        ("The operator", "says yes, or says nothing", AMBER, T_AMBER,
         ["An approval typed on Telegram, or an armed envelope.",
          "One click to halt: buys stop, sells stay possible.",
          "No human yes, no order."]),
    ]
    for i, (head, sub, acc, tint, lines) in enumerate(cols):
        x = M + i * (col_w + gap)
        card(s, x, y, col_w, 1.72, head,
             [P(sub, size=10.5, color=acc, bold=True, line=1.06, after=3)]
             + [P(ln, size=10.2, color=INK, line=1.08, after=2) for ln in lines],
             accent=acc, fill=tint, head_size=12.5, tag=f"s4 col {i}")
        if i < 2:
            arrow_r(s, x + col_w + 0.02, y + 0.72, 0.24, 0.28, color=MUT)
    yy = y + 1.92
    txt(s, M, yy, CW, 0.28,
        [P("Seven invariants the PRD treats as requirements, not preferences (documentation/PRD.md, "
           "section 4)", size=12, color=DARK, bold=True, font=HEAD, line=1.0)], tag="s4 h2")
    inv = [
        ("1 Determinism", "Same inputs, same plan, same hashes."),
        ("2 The LLM cannot trade", "No agent output reaches the broker."),
        ("3 Paper only, provably", "Four conditions must all hold, and live ids are hard-blocked."),
        ("4 Nothing trades silently", "Every verdict, submission, fill, halt and wait is a journal event."),
        ("5 A submit is not a fill", "Positions are reconciled from broker state, never from a reply."),
        ("6 A gate that always blocks is not a gate", "Checks must be provably computing, not swallowing errors."),
        ("7 No secrets in the record", "No credentials or full account ids in tracked files or journal rows."),
    ]
    iw = (CW - 6 * 0.12) / 7
    for i, (a, b) in enumerate(inv):
        card(s, M + i * (iw + 0.12), yy + 0.34, iw, 1.72, a, [b], accent=BRICK, fill=WHITE,
             head_size=10, body_size=9.6, tag=f"s4 inv {i}")
    txt(s, M, yy + 2.2, CW, 0.5,
        [P("Two of these are load-bearing for the demo: a live account is refused by code before any order "
           "call is built, and the hash chain is verified inside the reservation step, so an edited journal "
           "stops the desk rather than passing quietly.", size=10.4, color=MUT, line=1.1)], tag="s4 foot")
    notes(s, "This is the single most important slide, and it is also the simplest. On the left are the "
             "AI agents: they produce text. In the middle is a Python program with fixed rules: it produces "
             "orders. On the right is a person: they produce the yes. Underneath are the seven invariants "
             "the product requirements document treats as requirements rather than preferences. Determinism "
             "means the same input gives the same output and the same hash. The fourth one means the desk "
             "cannot make a quiet trade. The sixth is one I would draw attention to: a safety check that "
             "always returns the same answer is not a check, so each gate has to prove it computed - and every one "
             "of them has a test behind it, listed on slide 22.")


def s05_divider(prs):
    s = add_slide(prs, dark=True)
    kicker(s, "SECTION 1 OF 4")
    txt(s, M + 0.35, 2.05, CW - 0.7, 1.1,
        [P("Qoder and Cloud Agent usage", size=40, color=WHITE, bold=True, font=HEAD, line=1.0, after=6),
         P("30% of the score: multi-agent topology, automation, dashboards, reports and reusable skills",
           size=15, color=OFFWHITE, line=1.12)], tag="s5 title")
    txt(s, M + 0.35, 3.9, 8.9, 2.3,
        [P("What this section claims, and where each claim is checked", size=12, color=AMBER, bold=True,
           line=1.05, after=8),
         P("One permanent scheduled card, three decision and watch fires a day, four pinned agents, "
           "eleven skills, a Telegram approval step inside the run, a local desk, a hosted desk fed by "
           "the run itself, and a hash-chained journal that records the refusals as well as the fills.",
           size=12, color=OFFWHITE, line=1.16, after=8),
         P("Slides 6-17. Evidence: docs/agent-engineering.md, scripts/deploy_two_fire_automation.py, "
           "skills/*/*/SKILL.md, docs/runbooks/sentinel-telegram.md, desk-site/.",
           size=10.5, color=AMBER, line=1.1)], tag="s5 body")
    notes(s, "This section is worth thirty percent of the score, so it is the longest part of the deck. "
             "The handbook asks for more than one agent, automation that runs without me at the keyboard, "
             "a dashboard, written reports, and skills that somebody else could reuse. I will show each "
             "of those as it is actually deployed, including the parts that are still only built and not "
             "yet scheduled. Where something is partial, the slide says partial. The next twelve slides "
             "are the machine: how a day runs, who does what, and how I can prove that what is running is "
             "what the documentation describes.")


def s06_architecture(prs):
    s = add_slide(prs)
    y = title(s, "How it is wired: agents advise, code decides",
              "documentation/architecture.md, drawn as it runs today. There is one boundary and one "
              "direction across it.")
    # Control plane row
    box(s, M, y, 6.2, 0.88,
        [P("CONTROL PLANE", size=9.6, color=GREEN, bold=True, line=1.0, after=1),
         P("One permanent card, cron 5 8,12,15 * * 1-5 (America/New_York) - 08:05, 12:05, 15:05 ET, "
           "a new session each fire", size=9.8, color=INK, line=1.05)],
        fill=T_GREEN, line=GREEN, tag="s6 control")
    box(s, M + 6.34, y, 3.3, 0.88,
        [P("OPERATOR DESK", size=9.6, color=BLUE, bold=True, line=1.0, after=1),
         P("Local dashboard: arm bounds, halt, switch a lane. Writes commit and push, which is how the "
           "cloud mount sees intent", size=9.8, color=INK, line=1.05)],
        fill=T_BLUE, line=BLUE, tag="s6 desk")
    box(s, M + 9.78, y, CW - 9.78, 4.72,
        [P("SIDE CHANNELS", size=9.6, color=BRICK, bold=True, line=1.0, after=2),
         P("Observe and alert. Never a control path.", size=9.8, color=BRICK, bold=True, line=1.05,
           after=5),
         P("Telegram sentinel", size=10, color=INK, bold=True, line=1.05),
         P("digest + /approve inside the fire", size=9.6, color=MUT, line=1.05, after=4),
         P("Qoder Drive locker", size=10, color=INK, bold=True, line=1.05),
         P("raw run evidence, one journal the desk reads", size=9.6, color=MUT, line=1.05, after=4),
         P("Hosted desk (Qoder Sites)", size=10, color=INK, bold=True, line=1.05),
         P("fed by the last step of every fire", size=9.6, color=MUT, line=1.05, after=4),
         P("GitHub and CI", size=10, color=INK, bold=True, line=1.05),
         P("607 tests; a red pipeline blocks the merge", size=9.6, color=MUT, line=1.05, after=4),
         P("No channel can place, cancel or widen an order. The desk can halt through a file that the "
           "kernel reads, and nothing else.", size=9.6, color=INK, line=1.08)],
        fill=T_BRICK, line=BRICK, tag="s6 side")
    arrow_d(s, M + 2.7, y + 0.88, 0.24, 0.26, color=MUT)
    # LLM perimeter
    py = y + 1.20
    box(s, M, py, 9.64, 1.78,
        [P("LLM PERIMETER - four Qoder Cloud Agents, pinned versions, least privilege", size=9.6,
           color=GREEN, bold=True, line=1.0, after=3)], fill=WHITE, line=GREEN, tag="s6 perim")
    agents = [
        ("Coordinator", "9 built-in tools, no MCP server. Delegates, narrates, writes the digest."),
        ("Researcher", "25 read-only Moomoo tools + 6 built-ins. Catalysts, quotes, order book."),
        ("Risk auditor", "4 built-in tools, no MCP. Reads the plan and the journal, writes a verdict."),
        ("Executor", "14 of 15 Moomoo tools + 6 built-ins, quote_rt_data off. Broker reads and paper submit."),
    ]
    aw = (9.64 - 0.30 - 3 * 0.12) / 4
    for i, (nm, d) in enumerate(agents):
        card(s, M + 0.15 + i * (aw + 0.12), py + 0.44, aw, 1.20, nm, [d], accent=GREEN, fill=T_GREEN,
             head_size=10.5, body_size=9.4, tag=f"s6 agent {i}")
    arrow_d(s, M + 4.4, py + 1.80, 0.30, 0.34, color=GREEN)
    txt(s, M + 4.85, py + 1.82, 4.6, 0.34,
        [P("advisory only: text, proposals, audit verdicts", size=9.6, color=GREEN, bold=True, line=1.05)],
        tag="s6 adv")
    # Kernel
    ky = py + 2.22
    box(s, M, ky, 9.64, 1.42,
        [P("DETERMINISTIC KERNEL - src/tyche, Python 3.13. The only path to a trade.", size=9.6,
           color=BLUE, bold=True, line=1.0, after=3)], fill=WHITE, line=BLUE, tag="s6 kernel")
    steps = [
        ("5 strategy lanes", "each emits an OrderIntent"),
        ("risk.py", "named limits, named breaches"),
        ("approvals.py", "envelope or Telegram yes"),
        ("lifecycle.py", "re-validate, then reserve"),
        ("journal.py", "SHA-256 hash chain"),
    ]
    sw = (9.64 - 0.30 - 4 * 0.26) / 5
    for i, (nm, d) in enumerate(steps):
        x = M + 0.15 + i * (sw + 0.26)
        box(s, x, ky + 0.44, sw, 0.86,
            [P(nm, size=10, color=DARK, bold=True, font=HEAD, line=1.03, after=1),
             P(d, size=9.4, color=MUT, line=1.03)], fill=T_BLUE, line=BLUE, tag=f"s6 step {i}",
            pad=0.07)
        if i < 4:
            arrow_r(s, x + sw + 0.02, ky + 0.76, 0.20, 0.20, color=BLUE)
    arrow_d(s, M + 4.4, ky + 1.36, 0.30, 0.26, color=AMBER)
    box(s, M, ky + 1.66, 9.64, 0.72,
        [P("MOOMOO PAPER ACCOUNT", size=9.6, color=AMBER, bold=True, line=1.0, after=1),
         P("env == paper   and   id in the vault allowlist   and   account_type in {1,2}   and   "
           "market_id == 100. All four must hold; a live account is blocked in code.",
           size=9.6, color=INK, line=1.05)], fill=T_AMBER, line=AMBER, tag="s6 paper")
    notes(s, "Read this from the top down. The control plane is one scheduled card: it wakes the desk "
             "three times a weekday and nothing else does. The blue row underneath is the AI perimeter: "
             "four agents, each with a fixed version and a tool list I control, and the counts on each box "
             "come from reading the live agent objects rather than from the prompts. The thick green arrow "
             "is the only thing that crosses the boundary, and it carries text. Below the line is the "
             "Python kernel, where an order is actually built, sized, checked, reserved and written down. "
             "On the far right is the honest caveat: Telegram, Drive, the hosted desk and CI all observe "
             "and report, but none of them can place a trade. The amber box at the bottom is the account "
             "guard, and it is a conjunction: four conditions, all required.")


def s07_one_day(prs):
    s = add_slide(prs)
    y = title(s, "One trading day, three fires",
              "One card, cron 5 8,12,15 * * 1-5 in America/New_York. Each fire is a new session with a "
              "self-contained brief, so nothing carries over from yesterday.")
    cy = y + 0.04
    fires = [
        ("08:05 ET", "21:05 SGT", "Decide", GREEN, T_GREEN,
         ["tyche calendar gate first: weekend, holiday or outside 04:00-20:00 ET ends the run read-only.",
          "Researcher gathers catalysts and quotes; executor captures the broker book.",
          "Kernel builds the plan: lane, intents, risk verdict, plan file, journal row.",
          "Auditor reviews every approved order in its own thread.",
          "Exits are handled before entries. Proposals go to Telegram for a yes."]),
        ("12:05 ET", "01:05 SGT", "Watch and shout only", AMBER, T_AMBER,
         ["Opens, changes and closes nothing. No scan for new entries.",
          "Checks the journaled protection levels against the book.",
          "Messages only on a breach, or on a lot that has no exit written down.",
          "Two of the three fires are decision fires; this one is protection."]),
        ("15:05 ET", "04:05 SGT", "Decide and reconcile", BLUE, T_BLUE,
         ["Reconciles fills from broker order state, never from the submit reply.",
          "Runs expectancy, writes the end-of-day narrative.",
          "On a 13:00 ET early close this fire is after hours: reconcile only, never submit.",
          "Last step of every fire: publish the desk feed, so the hosted page moves with the run."]),
    ]
    w = (CW - 2 * 0.18) / 3
    for i, (et, sgt, head, acc, tint, lines) in enumerate(fires):
        x = M + i * (w + 0.18)
        card(s, x, cy, w, 3.28, head,
             [P(f"{et}   ·   {sgt}", size=10.5, color=acc, bold=True, font=HEAD, line=1.05, after=4)]
             + [P(ln, size=10.0, color=INK, line=1.08, after=3) for ln in lines],
             accent=acc, fill=tint, head_size=12, tag=f"s7 fire {i}")
    by = cy + 3.44
    facts = [
        ("Holiday filter lives in the run", "The cron carries no holiday list on purpose. "
         "`tyche calendar --json` inside the fire is the filter, so a holiday costs one read-only session."),
        ("Secrets stay server-side", "The Telegram token, the chat id and the account allowlist are card "
         "environment variables, referenced by name. No value is in a prompt, a file or this deck."),
        ("Cadence is a pin, not a tweak", "Every cadence change means rebuilding the card and re-pinning, "
         "with the prompt, cron and initial-events hash asserted unchanged."),
    ]
    fw = (CW - 2 * 0.16) / 3
    for i, (a, b) in enumerate(facts):
        card(s, M + i * (fw + 0.16), by, fw, 1.14, a, [b], accent=MUT, fill=WHITE, head_size=10,
             body_size=9.6, tag=f"s7 fact {i}", line_w=0.75)
    notes(s, "This is what the desk actually does on a weekday, and the times are printed twice because "
             "the operator is in Singapore. At 08:05 Eastern, which is 21:05 SGT, the desk does the "
             "research, the plan, the audit and the approval wait. At 01:05 SGT, which is midday in New "
             "York, it is deliberately forbidden from trading and only checks protection levels. At 04:05 "
             "SGT it reconciles fills and writes the end-of-day narrative. The first thing every fire does "
             "is ask the calendar whether the market is open, so a holiday fire costs one read-only session "
             "instead of a bad trade. The three notes at the bottom are the parts a judge usually asks "
             "about: how holidays are filtered, where the secrets live, and how the schedule itself is "
             "controlled.")


def s08_team(prs):
    s = add_slide(prs)
    y = title(s, "The desk team, and what each member may touch",
              "The topology the handbook asks for: researcher, executor and a risk auditor that cannot be "
              "talked into agreeing. Grants were re-read from the live agents, not from the prompts.")
    ow = 2.9
    box(s, M + (CW - ow) / 2, y, ow, 0.70,
        [P("Coordinator (desk head)", size=11, color=DARK, bold=True, font=HEAD, line=1.02, after=1),
         P("9 built-in tools · no MCP server · no vault", size=9.6, color=GREEN, line=1.02)],
        fill=T_GREEN, line=GREEN, tag="s8 coord")
    cw4 = (CW - 3 * 0.20) / 4
    cy = y + 1.06
    for i in range(4):
        arrow_d(s, M + cw4 * i + cw4 / 2 - 0.11 + 0.03, y + 0.74, 0.22, 0.28, color=MUT)
    members = [
        ("Researcher", "25 read-only Moomoo tools + 6 built-ins", "reports/<date>-research.md",
         "Submit, journal write"),
        ("Risk auditor", "4 built-in tools, no MCP server", "reports/<date>-audit.md",
         "Agree under pressure, submit"),
        ("Advisor", "model-only consult, no tools", "advice in the coordinator context",
         "Tools, files"),
        ("Executor", "sim trade tools + Moomoo MCP + vault", "plans/, journal/ (single writer)",
         "Act without an approved plan and a human arm"),
    ]
    for i, (nm, tools, owns, may_not) in enumerate(members):
        acc = BLUE if nm != "Executor" else AMBER
        card(s, M + i * (cw4 + 0.20), cy, cw4, 1.52, nm,
             [P("Tools: " + tools, size=9.6, color=INK, line=1.06, after=2),
              P("Owns: " + owns, size=9.6, color=INK, line=1.06, after=2),
              P("May not: " + may_not, size=9.6, color=acc, line=1.06)],
             accent=acc, fill=T_BLUE if nm != "Executor" else T_AMBER, head_size=10.8,
             tag=f"s8 member {i}")
    ty = cy + 1.68
    h = table(s, M, ty, CW,
              ["Role", "Vault / credentials", "Files it owns", "What it is never allowed to do"],
              [["Coordinator", "none", "reports/ narrative, delegation",
                "size an order, submit, hold trade tools"],
               ["Researcher", "none", "reports/<date>-research.md", "submit, write the journal"],
               ["Risk auditor", "none", "reports/<date>-audit.md, drawdown report",
                "be talked into agreeing; it runs in its own thread"],
               ["Executor", "Moomoo vault (the only role that holds it)", "plans/, journal/ as single writer",
                "act without the auditor's approval and a human arm"],
               ["Advisor", "none", "advice only, in the coordinator's context", "hold tools or write files"]],
              [1.5, 2.6, 3.0, 5.2], font=9.8, head_font=10, tag="s8 table", bold_col0=True, max_h=2.45)
    txt(s, M, ty + h + 0.10, CW, 0.5,
        [P("The coordinator prompt carries the handbook sentence verbatim: \"never let the executor act "
           "on the researcher's output without the auditor's approval.\" The auditor is separated on "
           "purpose - a model that can be argued with is not a control.", size=10.2, color=DARK,
           line=1.1)], tag="s8 quote")
    notes(s, "Five roles, and the point of the split is that nobody grades their own homework. The "
             "researcher finds a reason to act, the auditor checks the plan in a separate thread, and the "
             "executor is the only role that can reach the broker. The credentials column matters most: "
             "only the executor holds the Moomoo vault, and only one role writes the journal, which is why "
             "the record cannot be edited from two places. The tool counts are not copied from a prompt. "
             "They were read back from the live agent objects, which found a real problem: a template grant "
             "that had never been active on the running version materialised on recompile, so it was taken "
             "back out. One honest caveat for later: the coordinator pins its children at latest today, "
             "not at a number, and slide 9 explains what that means.")


def s09_planes(prs):
    s = add_slide(prs)
    y = title(s, "Why one plane, and what that cost us",
              "The desk used to be authored in two places at once. Retiring one of them taught three "
              "lessons worth showing, because each one changed a rule.")
    steps = [
        ("1", "Two surfaces, one desk", "Four agents and their prompts were authored on Managed, but the "
         "schedules, cadence and grants lived on Forward templates. Nobody could read the running "
         "configuration in one place."),
        ("2", "Eight schedules archived", "One reviewed POST each on 21 Nov, the Managed projection re-read "
         "after every call. An archived schedule still reports paused, so the retirement was verified by "
         "reading each object by id (L-053)."),
        ("3", "Four agents recreated", "A template archive turns out to archive the Managed agent compiled "
         "from it, with no restore (L-054). All four were rebuilt field-for-field as plain Managed agents, "
         "byte-compared, before anything was archived (L-055)."),
        ("4", "One writer, fenced", "The desk is authored on Managed only. tests/test_forward_fence.py "
         "fails if anything under scripts/ imports forward or names /templates, and the hosted desk now "
         "reads the same plane."),
    ]
    w = (CW - 3 * 0.16) / 4
    for i, (n, head, body) in enumerate(steps):
        card(s, M + i * (w + 0.16), y, w, 1.86, f"{n} · {head}", [body], accent=GREEN, fill=T_GREEN,
             head_size=11, body_size=9.8, tag=f"s9 step {i}")
        if i < 3:
            arrow_r(s, M + (i + 1) * w + i * 0.16 + 0.01, y + 0.86, 0.14, 0.16, color=MUT)
    cy = y + 2.04
    cards = [
        ("A re-pin is a capability review", BRICK, T_BRICK,
         "Reading a re-pin as a prompt edit nearly handed the desk ten always-allow platform tools - "
         "including schedule writers - that its running version never had (L-046). Now the compiled "
         "agent's capability surface is asserted, not the template's."),
        ("A rebuild can delete rows", AMBER, T_AMBER,
         "Rebuilding the roster from only the rows a script cared about silently dropped the model-only "
         "advisor (L-045). Deep-copy the whole object, mutate named fields, assert the untouched rows "
         "survive byte-identically."),
        ("The honest edges, stated", BLUE, T_BLUE,
         "On the executor pin only cancel and modify are always_ask; the paper submit is always_allow, "
         "because the preview-and-confirm protocol is what gates it. The coordinator also still pins its "
         "three children at latest (a documented exception, PRD section 7)."),
    ]
    cw3 = (CW - 2 * 0.16) / 3
    for i, (head, acc, tint, body) in enumerate(cards):
        card(s, M + i * (cw3 + 0.16), cy, cw3, 1.86, head, [body], accent=acc, fill=tint,
             head_size=11, body_size=9.8, tag=f"s9 card {i}")
    txt(s, M, cy + 2.02, CW, 0.4,
        [P("What is on each plane today: four Managed agents and one permanent Managed card; four archived "
           "templates, eight archived schedules, one archived environment and one Forward identity that the "
           "journal lineage depends on. The archive is history, not a second control path.",
           size=10.2, color=MUT, line=1.1)], tag="s9 foot")
    notes(s, "This slide is about the platform decision that changed my rules, and I am showing it because "
             "the rubric rewards an operator who can explain a failure. The desk was being authored on two "
             "planes at once, and one of them was the only place the schedule lived. Retiring that plane "
             "revealed that archiving a template also archives the live agent built from it, with no "
             "restore - so the four agents had to be rebuilt before anything could be cleaned up. That "
             "became a rule: never archive under a live pin. A second rule came from a re-pin that quietly "
             "added ten powerful tools the running version never had. And the honest caveat: the submit "
             "tool is set to always-allow rather than always-ask, because the human approval is enforced "
             "one layer down, in the preview-and-confirm protocol and the kernel gate.")


def s10_skills(prs):
    s = add_slide(prs)
    y = title(s, "Eleven reusable skills, pinned by version",
              "Procedures live in skills/<role>/<name>/SKILL.md in the repo. The prompts keep permissions "
              "and hard rules only, so a cap cannot go stale in two places (L-033, L-048).")
    groups = [
        ("Coordinator", GREEN, T_GREEN, ["sentinel-digest", "midday-watch", "proposal-approval"]),
        ("Researcher", BLUE, T_BLUE, ["scout-data-suite", "event-discovery", "youtube-inbox"]),
        ("Risk auditor", AMBER, T_AMBER, ["exact-order-audit", "lifecycle-review"]),
        ("Executor", BRICK, T_BRICK, ["broker-capture", "paper-submit-protocol"]),
        ("Shared", MUT, T_GRAY, ["lifecycle-contract"]),
    ]
    gw = (CW - 4 * 0.14) / 5
    for i, (role, acc, tint, names) in enumerate(groups):
        paras = [P(role, size=11, color=acc, bold=True, font=HEAD, line=1.03, after=4)]
        for nm in names:
            paras.append(P(nm, size=9.8, color=INK, line=1.05, after=3))
        card(s, M + i * (gw + 0.14), y, gw, 1.62, None, paras, accent=acc, fill=tint,
             tag=f"s10 group {i}")
    fy = y + 1.80
    txt(s, M, fy, CW, 0.28,
        [P("Two steps, on purpose: a body is published, then a version is pinned on an agent",
           size=11.5, color=DARK, bold=True, font=HEAD, line=1.0)], tag="s10 h2")
    flow = [
        ("publish-skill", "Multipart zip to the platform; mints one immutable version. Nothing is pinned "
         "by this call."),
        ("attach", "An ordinary agent write: skills: [{skill_id, version, enabled}]. Content and "
         "attachment are two different surfaces."),
        ("pin", "latest_version is an epoch-microsecond string, pinned verbatim. There is no latest for a "
         "skill, and a change means a new version plus a re-pin."),
        ("verify", "Read the agent back and assert the pin, the prompt and the tool list. Deleting a skill "
         "deletes all of its versions (L-021, L-047)."),
    ]
    fw = (CW - 3 * 0.24) / 4
    for i, (nm, d) in enumerate(flow):
        x = M + i * (fw + 0.24)
        box(s, x, fy + 0.36, fw, 1.32,
            [P(nm, size=10.6, color=DARK, bold=True, font=HEAD, line=1.03, after=2),
             P(d, size=9.7, color=INK, line=1.07)], fill=WHITE, line=GREEN, tag=f"s10 flow {i}")
        if i < 3:
            arrow_r(s, x + fw + 0.03, fy + 0.90, 0.18, 0.18, color=GREEN)
    ny = fy + 1.82
    card(s, M, ny, 6.05, 1.16, "What is on the platform today",
         ["Three skills are created and pinned on a live agent: sentinel-digest on the coordinator, "
          "exact-order-audit on the auditor, paper-submit-protocol on the executor. The other eight are "
          "written, tested and ready; their create step is one reviewed command each."],
         accent=AMBER, fill=T_AMBER, head_size=10.6, body_size=9.8, tag="s10 now")
    card(s, M + 6.21, ny, CW - 6.21, 1.16, "The rule a skill has to obey",
         ["An agent reads a skill only when it decides it applies, so a rule that must hold on every turn "
          "stays verbatim in the prompt. Before a trim, the skill body is diffed against the file that "
          "enforces it - two skills were wrong about the kernel (L-048)."],
         accent=BLUE, fill=T_BLUE, head_size=10.6, body_size=9.8, tag="s10 rule")
    notes(s, "Skills are how the procedures get reused instead of retyped. Each one is a markdown file in "
             "the repository, guarded by tests, and published to the platform as an immutable version that "
             "an agent pins by number. Publishing and pinning are deliberately two calls, so promoting a "
             "procedure is an explicit act. The four boxes show that path and the honest note underneath it "
             "says what is actually live: three skills are pinned today, the other eight exist in the repo "
             "and are created one command each. Why bother splitting the text out of the prompt? Because a "
             "number quoted in two places drifts, and a stale cap inside an auditor prompt reads as "
             "authority. That specific failure is lesson L-033, and it is on slide 31.")


def s11_telegram(prs):
    s = add_slide(prs)
    y = title(s, "The human yes: a proposal, a preview, a reply",
              "scripts/telegram.py wait-for-reply, live on the permanent card since 22 Nov. Runbook: "
              "docs/runbooks/sentinel-telegram.md. This is the only inbound path an operator has, and it "
              "cannot widen a position.")
    steps = [
        "The desk builds a proposal file: entry, size, value, stop, target, exit-by, thesis, invalidation. "
        "A file missing any exit field is rejected before anything is sent.",
        "One numbered preview arrives in the operator's chat with the full exit plan, the deadline in UTC "
        "and SGT, and a content reference.",
        "The window is 10 minutes by default and 15 at most. No reply is a no, never a maybe.",
        "The operator replies /approve N or /deny N with a reason. Plain text is a question or a change "
        "request: the proposal stays unapproved and a rebuild gets a new number.",
        "On approve, the desk journals one approval.telegram event per order, and only those orders become "
        "authorizable. An approval without an order block authorizes nothing.",
        "The normal path continues unchanged: risk verdict, exact-order audit, reserve, one submit.",
        "The command returns one of decided, reply, timeout or conflict. Conflict means a second listener "
        "is reading the bot, and it decides nothing.",
    ]
    lw = 7.55
    for i, st in enumerate(steps):
        card(s, M, y + i * 0.63, lw, 0.58, None,
             [P(f"{i+1}", size=10.2, color=GREEN, bold=True, font=HEAD, line=1.03), ],
             accent=LINE, fill=T_GRAY, tag=f"s11 num {i}", pad=0.06)
        txt(s, M + 0.42, y + i * 0.63 + 0.04, lw - 0.52, 0.5,
            [P(st, size=9.9, color=INK, line=1.07)], tag=f"s11 step {i}")
    rx = M + lw + 0.20
    card(s, rx, y, CW - lw - 0.20, 2.32, "Everything else is a no",
         ["Silence. A timeout is recorded as a no.",
          "Free text. It never authorizes; it becomes a question.",
          "Another chat. Only the allowlisted chat id counts.",
          "Yesterday's approval. Messages older than the preview are ignored.",
          "A second listener. Telegram answers 409 and nothing is decided.",
          "A failed send. Any non-zero exit is treated as a no."],
         accent=BRICK, fill=T_BRICK, head_size=11.5, body_size=9.8, tag="s11 no")
    card(s, rx, y + 2.46, CW - lw - 0.20, 1.62, "What /approve does not do",
         ["It never cancels or modifies a resting order: those stay always_ask, and an envelope does not "
          "approve them.",
          "It cannot arm an envelope. The arm click on the desk is the only writer of the bounds file.",
          "It does not survive the day: an envelope dated yesterday protects yesterday's book, so arming "
          "it is refused."],
         accent=BLUE, fill=T_BLUE, head_size=11.5, body_size=9.8, tag="s11 not")
    card(s, rx, y + 4.22, CW - lw - 0.20, 1.34, "Proven by",
         ["tests/test_telegram_approval.py (decisions, allowlist, stale, resume, conflict, timeout bounds) "
          "and tests/test_desk_card_prompt.py, which pins the clause in the card brief. No new secret, no "
          "new token: it reuses the sentinel bot already on the card."],
         accent=MUT, fill=WHITE, head_size=10.6, body_size=9.6, tag="s11 proof")
    notes(s, "This is where the human is in the loop, and it is worth walking through slowly. The desk "
             "sends a numbered preview of one specific order with its stop, target and exit deadline, then "
             "waits ten minutes. An approval authorizes exactly that order and nothing else; a rejection "
             "or a silence authorizes nothing. The red card is the part I would emphasize: six different "
             "ways to be ambiguous, and all six resolve to no. That matters because the alternative is a "
             "desk that trades when it was not told to. The blue card states what the approval cannot do: "
             "it never cancels or modifies a live order, and it never arms the daily bounds. The grey card "
             "names the tests. This path went live on the permanent card on 22 November, so the first real "
             "proposal is the proof rather than the test suite.")


def s12_modes(prs):
    s = add_slide(prs)
    y = title(s, "Two trading modes, one fact each (ADR 0018)",
              "The desk had three operator modes and produced a two-yes gap nobody could reason about. "
              "Two modes, decided by one fact: does a same-day envelope exist at the fire?")
    mw = (CW - 0.30) / 2
    card(s, M, y, mw, 2.34, "ASK ME   ·   no envelope (the default)",
         ["Every entry waits for its own Telegram /approve during the fire. That approve is the whole yes.",
          "The preview prints what the approve authorizes: symbol, side, quantity, limit, exit floor, "
          "setup hash where the lane binds one.",
          "Nothing is written to data/approvals.json. Authority comes from today's journaled approvals.",
          "One yes per entry, never two. Used on the days the operator is awake."],
         accent=GREEN, fill=T_GREEN, head_size=11.6, body_size=10, tag="s12 ask")
    card(s, M + mw + 0.30, y, mw, 2.34, "WITHIN MY BOUNDS   ·   same-day envelope armed",
         ["The operator arms bounds from the desk in one click: re-arm the last bounds, define fresh ones, "
          "or arm a drafted exit note.",
          "The desk submits inside them with no Telegram ask, which is what makes the 15:05 ET fire usable "
          "while the operator sleeps.",
          "The envelope is dated, bounded and git-tracked. Removing it is one click or one halt.",
          "It never authorizes a cancel or a modify."],
         accent=AMBER, fill=T_AMBER, head_size=11.6, body_size=10, tag="s12 bounds")
    gy = y + 2.52
    box(s, M, gy, CW, 0.72,
        [P("ONE CHOOSER, ONE OVERRIDE", size=9.8, color=BLUE, bold=True, line=1.0, after=1),
         P("resolve_batch() is the single decision point: a valid same-day envelope wins, otherwise today's "
           "Telegram approvals, otherwise nothing is authorized. The kill switch overrides both. A run may "
           "read the envelope and never write it, so only the operator can change the mode.",
           size=9.9, color=INK, line=1.06)], fill=T_BLUE, line=BLUE, tag="s12 chooser")
    by = gy + 0.88
    facts = [
        ("What the envelope actually agrees to", GREEN,
         "The only number the operator sets on that path is the exit collar: a drafted sell sits 5% below "
         "the stop the plan journaled. Symbols, quantities and stops come from the journal and the broker "
         "book, and anything the kernel cannot ground is refused with a reason rather than guessed."),
        ("Why the old third mode went", BLUE,
         "Manual and Pre-approve were two views of the same file, and from a phone they looked identical. "
         "A Telegram yes could not become an envelope either, because the cloud desk cannot push that file "
         "back (403). The gap was structural, not cosmetic."),
        ("Today, as published", AMBER,
         "The desk feed for 22 Nov reports Ask me: the 19 Nov bounds had expired, so entries wait for a "
         "reply. The draft exit note for the open lot is visible and marked not armed - a proposal, "
         "awaiting one click."),
    ]
    fw = (CW - 2 * 0.16) / 3
    for i, (head, acc, body) in enumerate(facts):
        card(s, M + i * (fw + 0.16), by, fw, 1.52, head, [body], accent=acc,
             fill=T_GRAY if i else T_GRAY, head_size=10.6, body_size=9.7, tag=f"s12 fact {i}")
    notes(s, "This slide answers the question a judge always asks about autonomy: what exactly is the human "
             "agreeing to? There are two modes, and the desk picks between them on one fact at the moment "
             "it runs. If bounds exist for today, it trades inside them without asking. If they do not, "
             "nothing is authorized without a reply on Telegram. The single chooser matters because the "
             "old design had three modes over one file and produced a state where a yes on the phone did "
             "nothing. The green card is the honest answer to what the operator signs: one number, the "
             "collar, which is how far below the journaled stop a proposed exit may go. As of the last "
             "published feed, the desk is in Ask me mode, because the bounds from the 19th expired.")


def s13_rungs(prs):
    s = add_slide(prs)
    y = title(s, "How much autonomy the desk has earned",
              "The ladder the operator agreed to on 21 Nov (docs/runbooks/intraday-protection-monitor.md "
              "§0), ordered by what a position may do on its own. Rung 1 - an urgent Telegram bark - sits "
              "between the first two and is not built: routing is a separate approval.")
    bands = [
        ("RUNG 0", "Detect and record", GREEN, T_GREEN, "BUILT 21 NOV - NOT SCHEDULED", 0.0,
         ["`tyche monitor tick` decides in plain Python whether a price crossed a level the journal already "
          "holds, and writes monitor.heartbeat / .breach / .clear / .gap. Nothing else.",
          "Fail-closed: a stale, missing or untradable quote exits 2 as NO-GO, never as \"no breaches\". "
          "No clock runs it yet, so detection today is still the three fires."]),
        ("RUNG 1.5", "Exit on a note the human signed in advance", BLUE, T_BLUE, "BUILT - ONE CLICK TO ARM",
         0.55,
         ["`src/tyche/envelope.py` drafts one sell line per open lot from the book the desk shows and the "
          "stop each plan journaled. The operator owns exactly one number: the collar, 5% under that stop.",
          "Only the Arm click writes the bounds file, and a draft not dated today is refused. Anything the "
          "kernel cannot ground - no journaled stop, no verified option contract - is a reported refusal."]),
        ("RUNG 2", "Decide and submit alone", BRICK, T_BRICK, "DECLINED", 1.10,
         ["Not built, not scheduled, not on the roadmap for this challenge.",
          "The simulator holds Limit and Market orders only, so an automatic exit is an automatic market "
          "order - and the platform's own rule is that a submit is not a fill."]),
    ]
    bh = 1.18
    for i, (rung, name, acc, tint, status, indent, lines_) in enumerate(bands):
        by = y + i * (bh + 0.16)
        bx, bw = M + indent, CW - indent
        box(s, bx, by, bw, bh, [], fill=tint, line=acc, tag=f"s13 band {i}", pad=0.0)
        txt(s, bx + 0.16, by + 0.11, 2.45, 0.30,
            [P(rung, size=12.4, color=acc, bold=True, font=HEAD, line=1.02)], tag=f"s13 rung {i}")
        txt(s, bx + 0.16, by + 0.44, 2.45, 0.26,
            [P(status, size=9.2, color=DARK, bold=True, line=1.02)], tag=f"s13 status {i}")
        txt(s, bx + 0.16, by + 0.72, 2.45, bh - 0.80,
            [P(name, size=10.2, color=INK, line=1.10)], tag=f"s13 name {i}")
        paras = []
        for ln in lines_:
            paras.append(P(ln.replace("`", ""), size=9.9, color=INK, line=1.09,
                           after=0 if ln is lines_[-1] else 5))
        txt(s, bx + 2.75, by + 0.13, bw - 2.91, bh - 0.26, paras, tag=f"s13 text {i}")
        if i:
            arrow_r(s, bx - 0.30, by + bh / 2 - 0.10, 0.26, 0.20, color=acc)
    cy = y + 3 * (bh + 0.16) + 0.06
    ch = 6.92 - cy
    cw3 = (CW - 2 * 0.18) / 3
    cards = [
        ("What protects a lot right now", GREEN, T_GREEN,
         ["The three fires: 08:05, 12:05 (watch and shout only) and 15:05 ET check every open position "
          "against its journaled stop, target and deadline.",
          "Between fires nothing watches. The gap is up to about 4 hours intraday and 17 overnight."]),
        ("Why the line sits here", AMBER, T_AMBER,
         ["Rung 2 needs an order no human approved. Cancel and modify stay always_ask even inside an "
          "envelope, and only the arm click writes the bounds file.",
          "A monitor-queued exit still passes risk.py, the auditor and the gate: it widens nothing."]),
        ("Rung 1, and what is owed", BRICK, T_BRICK,
         ["The urgent bark renders but is never sent: per-tick routing needs its own approval, and it was "
          "not given.",
          "PB-003 options stay off until the monitor is scheduled and passes a live-session drill."]),
    ]
    for i, (head, acc, tint, lines_) in enumerate(cards):
        card(s, M + i * (cw3 + 0.18), cy, cw3, ch, head,
             [P(ln.replace("`", ""), size=9.6, color=INK, line=1.08, after=4) for ln in lines_],
             accent=acc, fill=tint, head_size=11.0, tag=f"s13 card {i}")
    notes(s, "This slide answers the question a judge usually asks last: how much does it do without you? "
             "The ladder came out of a real conversation with the operator on 21 November. The bottom rung "
             "only detects and writes: a Python command decides whether a price crossed a level the journal "
             "already recorded, and it is deliberately not scheduled, because a card that fires outside the "
             "session would judge overnight holds on stale quotes. The middle rung is the compromise the "
             "operator picked: the desk drafts the exit note from numbers it can ground, and one human "
             "click arms it for the day. The top rung - the system submitting on its own - was declined, "
             "because the simulator has no native stops, so an automatic exit is an automatic market order. "
             "The three cards at the bottom state what actually protects the book today, why the line sits "
             "where it does, and the two pieces still owed.")


def s14_dashboard(prs):
    s = add_slide(prs)
    y = title(s, "The operator desk: five views, five reads, five writes",
              "dashboard/ is stdlib Python on 127.0.0.1:8765 (UI v0.16.1). The handbook asks for a "
              "dashboard; this one shows positions, P&L, the equity curve, open orders, drawdown and the "
              "decision log, and it is also the only place a control can be changed.")
    views = [
        ("Overview", "How am I doing?", GREEN,
         ["Account value over time, cash, gross exposure and drawdown.",
          "Banked profit and win rate, with the finished trades behind them.",
          "What is open now, and what the desk has refused."]),
        ("Trade ideas", "Every idea and its five checks", BLUE,
         ["One row per idea, tagged with its playbook id and its written thesis - or \"no written thesis\".",
          "Is the plan working: closed trades by sleeve, R multiple, expectancy.",
          "How complete the paperwork is for each lane."]),
        ("Safety & orders", "The rules, checked live", AMBER,
         ["One box per risk rule, evaluated against the latest numbers.",
          "\"Not measurable\" means the desk lacks the data, not that the rule is off.",
          "Only orders actually sent to the broker, with the price the broker gave back."]),
        ("Schedule", "The clock, as it really is", BRICK,
         ["Fire times derived from the card's own cron expression, not a hand-kept list.",
          "Recent runs with their errors, and the next run times.",
          "What each fire is allowed to do: plan, monitor, or act."]),
        ("Controls", "The only place a switch moves", DARK,
         ["Trading mode: Ask me, or Within my bounds.",
          "Arm or disarm the day's bounds, switch a lane, halt, run Scout.",
          "Unlocked by an operator passphrase held in memory; each write commits and pushes."]),
    ]
    vw = (CW - 4 * 0.16) / 5
    vh = 2.94
    for i, (nm, sub, acc, lines) in enumerate(views):
        paras = [P(nm, size=12, color=acc, bold=True, font=HEAD, line=1.03, after=1),
                 P(sub, size=9.6, color=MUT, italic=True, line=1.05, after=6)]
        for ln in lines:
            paras.append(P(ln, size=9.7, color=INK, line=1.08, after=5))
        box(s, M + i * (vw + 0.16), y, vw, vh, paras, fill=T_GRAY if i % 2 else WHITE, line=acc,
            tag=f"s14 view {i}", pad=0.12)
    cy = y + vh + 0.20
    cw3 = (CW - 2 * 0.18) / 3
    facts = [
        ("Every number has a source", GREEN,
         ["The page is built from the hash-chained journal plus a broker capture written by the executor. "
          "It never invents a field: a gap renders as \"not recorded\", and the account ids in it are "
          "masked."]),
        ("Writes are files, and files are auditable", BLUE,
         ["A control change writes one JSON path, commits it and pushes, which is how the cloud mount sees "
          "operator intent without a shared database. A cadence write is re-read afterwards and reports "
          "verified: false if the platform did not apply it."]),
        ("No screenshot on this slide, on purpose", AMBER,
         ["The hosted copy is private: its gateway answers 401 to an automated browser, so nothing here was "
          "captured from it. A screen recording of the desk in action is on the submission list and is "
          "still to be made (tip H1)."]),
    ]
    for i, (head, acc, lines) in enumerate(facts):
        card(s, M + i * (cw3 + 0.18), cy, cw3, 1.66, head,
             [P(ln, size=9.8, color=INK, line=1.09, after=4) for ln in lines],
             accent=acc, fill=WHITE, head_size=11.2, tag=f"s14 fact {i}", line_w=0.85)
    notes(s, "This is the desk, and it is the part the handbook explicitly rewards. Five views: the "
             "account's state, every trade idea with the checks it passed or failed, the risk rules as "
             "live boxes rather than a policy document, the schedule as the cloud card actually expresses "
             "it, and the controls. One design decision matters most: the page is a reader of the same "
             "journal the kernel writes, so the operator and the machine cannot disagree about the book. "
             "The Controls view is the only writer, and each write is a commit and a push, which is how an "
             "ephemeral cloud session sees a decision made on a laptop. I have not pasted a screenshot: the "
             "hosted site is private and an automated browser gets a 401, so I would be showing you a "
             "picture I cannot verify. The recording is on the submission list, and I would rather tell you "
             "it is owed than fake it.")


def s15_hosted_feed(prs):
    s = add_slide(prs)
    y = title(s, "The hosted desk feeds itself",
              "scripts/publish_desk_data.py became the last step of every card run on 23 Nov. Before that "
              "the published numbers went stale for three days, because a person had to remember to run it.")
    steps = [
        ("1 · A fire ends", "The 08:05, 12:05 or 15:05 ET run has journaled its work and reconciled what it "
         "can. Nothing is pushed yet."),
        ("2 · Build the feed", "`export_dashboard.py --data-only` rebuilds state, automation and schedule "
         "JSON from the journal and the broker capture."),
        ("3 · Refuse, then write", "The exporter stops if a secret, a full account id or a token appears in "
         "the output. Only whitelisted views survive."),
        ("4 · Commit and push", "Exactly the files the Function reads, pushed with the card's own repo "
         "token handed to git through GIT_ASKPASS. The mount is read-only."),
        ("5 · Function serves it", "`desk-site/functions/` reads the committed JSON from the repo and "
         "projects every cloud row before a browser sees it."),
    ]
    sw = (CW - 4 * 0.30) / 5
    for i, (nm, d) in enumerate(steps):
        box(s, M + i * (sw + 0.30), y, sw, 1.62,
            [P(nm.replace("`", ""), size=10.6, color=DARK, bold=True, font=HEAD, line=1.04, after=4),
             P(d.replace("`", ""), size=9.6, color=INK, line=1.09)],
            fill=T_BLUE, line=BLUE, tag=f"s15 step {i}", pad=0.11)
        if i < 4:
            arrow_r(s, M + (i + 1) * sw + i * 0.30 + 0.04, y + 0.66, 0.22, 0.22, color=GREEN)
    cy = y + 1.82
    cw3 = (CW - 2 * 0.18) / 3
    cards = [
        ("One switch, one writer", GREEN, T_GREEN,
         ["The hosted page serves /schedule from the committed schedule.json and holds no cadence write "
          "path: two ways to change a schedule is how a schedule drifts.",
          "The Function's cloud credential is spent on GETs only.",
          "Buttons that need Python and a journal - propose an envelope, arm it - do not appear on the "
          "hosted console at all."]),
        ("Proven by the suite, not by eye", BLUE, T_BLUE,
         ["`test_every_feed_file_the_hosted_function_reads_is_published` fails if a route reads a file the "
          "publisher does not stage.",
          "`test_hosted_desk_assets_have_sources_that_survive_a_full_export` fails if a derived copy "
          "diverges from its source.",
          "`node --check` runs on the desk script, because one raw newline in a JS string blanked the whole "
          "page while every Python test stayed green (L-040)."]),
        ("What is still true", AMBER, T_AMBER,
         ["The feed advances three times a trading day from 23 Nov; the first unattended publish is today's "
          "08:05 ET fire and is to be verified.",
          "The pages themselves move only on a republish from the IDE, and the 23 Nov desk changes await "
          "one.",
          "A clone's data/*.json is a snapshot of whenever the publisher last ran, which reads as live "
          "state to anyone who finds it (PRD §7 item 6)."]),
    ]
    widths = [3.62, 4.85, 3.62]
    xs, acc_x = [], M
    for wd in widths:
        xs.append(acc_x)
        acc_x += wd + 0.12
    for i, (head, acc, tint, lines) in enumerate(cards):
        card(s, xs[i], cy, widths[i], 2.94, head,
             [P(ln.replace("`", ""), size=9.8, color=INK, line=1.09, after=5) for ln in lines],
             accent=acc, fill=tint, head_size=11.2, tag=f"s15 card {i}")
    notes(s, "The dashboard is worth something to a judge only if it stays true without me. This is the "
             "path that makes it so: the run itself publishes a sanitized feed, the repository carries it, "
             "and a hosted function serves it. Two things are worth calling out. First, the publisher "
             "refuses to write when it finds a secret, a full account id or a token in the output - the "
             "guard is in the exporter, not in my memory. Second, the hosted page can read the schedule but "
             "cannot change it, so there is exactly one place where the clock is set. The amber card is the "
             "honest limit: the numbers move with every fire as of today, but the page layout still needs a "
             "manual republish, and I have not seen the hosted console while signed in, so that acceptance "
             "check is listed as not done rather than assumed.")


def s16_evidence(prs):
    s = add_slide(prs)
    y = title(s, "Evidence, not memory: a chain you can check",
              "Every plan, verdict, submission, fill, halt, refusal and config change is one append-only "
              "line in journal/events.jsonl. Each line's SHA-256 covers the line before it, so editing "
              "history breaks the chain out loud (ADR 0005, ADR 0009).")
    bw = 2.72
    by = y
    labels = [
        ("row k-1", "plan.created", ["hash  a1f4..."], True),
        ("row k", "risk.verdict", ["prev  a1f4...", "hash  7d20..."], False),
        ("row k+1", "order.filled", ["prev  7d20...", "hash  c9b3..."], False),
    ]
    for i, (row, kind, hsh, first) in enumerate(labels):
        x = M + i * (bw + 0.62)
        paras = [P(row, size=9.6, color=MUT, bold=True, line=1.02, after=2),
                 P(kind, size=10.8, color=DARK, bold=True, font=HEAD, line=1.04, after=3)]
        for k, hline in enumerate(hsh):
            paras.append(P(hline, size=9.4, color=(GREEN if first else BLUE), line=1.12,
                           after=0 if k == len(hsh) - 1 else 1))
        box(s, x, by, bw, 1.22, paras, fill=(T_GRAY if first else T_BLUE),
            line=LINE if first else BLUE, tag=f"s16 row {i}", pad=0.11)
        if i:
            arrow_r(s, x - 0.56, by + 0.46, 0.50, 0.24, color=GREEN)
    box(s, M + 3 * (bw + 0.62), by, CW - 3 * (bw + 0.62), 1.22,
        [P("tyche journal-verify", size=10.6, color=DARK, bold=True, font=HEAD, line=1.04, after=3),
         P("Runs in CI, at the start of every reserve, and by hand. Today: OK on the 93-event chain.",
           size=9.6, color=INK, line=1.09)],
        fill=T_GREEN, line=GREEN, tag="s16 verify", pad=0.11)
    cy = by + 1.40
    cw2 = (CW - 0.20) / 2
    ch = 2.22
    card(s, M, cy, cw2, ch, "ADR 0009: two kinds of evidence, two homes",
         ["Raw run payloads go to the Qoder Drive locker (/data/drive/tyche-raw/<run>/); sanitized "
          "summaries go to git. The cloud sandbox is ephemeral, so a run that is not written out is "
          "worthless as proof (L-025).",
          "Account ids are masked at journal write time, and the masking is a test rather than a habit "
          "(L-031). Nothing in this deck carries a full id, a token or a chat id.",
          "A halt can be set from either the journal directory or the repo, and the kernel merges both "
          "flags, so a halt from one place stops buys in the other."],
         accent=GREEN, fill=T_GREEN, head_size=11.2, tag="s16 adr9")
    card(s, M + cw2 + 0.20, cy, cw2, ch, "ADR 0014: the rules a trade was taken under, hashed",
         ["`tyche rules-freeze` puts three claims about one lane in a table: the bytes the kernel hashes, "
          "the hash the playbook declares, the hash the chain last recorded.",
          "Current per-lane hash from the published feed (23 Nov): PB-001 819ad06e35f0 · PB-002 and PB-003 "
          "d5ef9567c736 (one file, one hash) · PB-004 72077d5d4808 · PB-007 e26f006da28a.",
          "A lane whose document disagrees with the kernel blocks the run. `old_hash` is read only from the "
          "chain, so a freeze row cannot launder a previous value (L-035)."],
         accent=BLUE, fill=T_BLUE, head_size=11.2, tag="s16 adr14")
    cy2 = cy + ch + 0.18
    card(s, M, cy2, cw2, 6.62 - cy2, "Decisions and refusals are first-class rows",
         ["The published feed carries 13 rejections: account.paper_only 4, halt.active 3, turnover.daily 3, "
          "portfolio.gross 1, portfolio.min_cash 1. The performance pack adds 6 gate.wait rows.",
          "A rejection names the rule id, the symbol, the quantity and the reason, which is the log the "
          "handbook asks for: what failed, and against what."],
         accent=AMBER, fill=T_AMBER, head_size=11.2, tag="s16 rejections")
    card(s, M + cw2 + 0.20, cy2, cw2, 6.62 - cy2, "The honest wrinkle: two chains",
         ["The 93-event chain verified above is the laptop's copy. The ledger the desk card reads is the "
          "Drive one - 41 events after the 23 Nov re-freeze - and the two shared zero events until it was "
          "re-recorded (L-056).",
          "`rules-freeze --record` now refuses a journal inside a repo checkout unless --drill is passed, "
          "and stamps every row ledger or drill. The 23 Nov performance pack was built from the drill copy "
          "and says so on its first line."],
         accent=BRICK, fill=T_BRICK, head_size=11.2, tag="s16 tw_chains")
    notes(s, "This is the slide I would spend the most time on if a judge doubts anything else. The journal "
             "is a plain text file where each line contains the hash of the line before it, so changing "
             "history changes every hash after it and the verify command fails. That is what makes the "
             "numbers in the rest of this deck checkable rather than asserted. The blue card is about a "
             "second kind of proof: the frozen hash of the rules themselves, so a result can be tied to the "
             "exact strategy file that produced it. The orange card is the rejections - the trades that "
             "never happened, with the rule that stopped them. And the red card is me admitting a real "
             "problem: there were two journals, and the older provenance rows were written to the one the "
             "desk does not read. That was found, fixed with a guard, and it is why the performance pack "
             "carries a note about which copy it came from.")


def s17_checks(prs):
    s = add_slide(prs)
    y = title(s, "How we checked it",
              "Nine checks, what each one proves, and what the record actually says. The last row is a "
              "claim I am not allowed to make yet.")
    rows = [
        ["pytest -q", "The gates behave: sizing, caps, envelopes, desk controls, journal math",
         "616 pass locally (README). PRD's CI row says 607, the 22 Nov entry 651: the suite grew during "
         "the window",
         "GitHub Actions on every push: ruff check src scripts tests, then pytest"],
        ["tyche journal-verify", "No journal row was edited, removed or reordered",
         "OK, 93 events on the laptop chain (published feed, 23 Nov)",
         "journal.py, CI, and inside every lifecycle reserve"],
        ["test_docs_consistency.py", "Roster, playbook front matter, config and document versions agree",
         "Passes; it also refuses a doc link to a gitignored runtime file (L-042)",
         "tests/test_docs_consistency.py"],
        ["tyche rules-freeze", "Each lane's frozen rules hash on the chain equals the bytes it trades now",
         "Five lanes on the chain; hashes on slide 16",
         "src/tyche/freeze.py, 18 tests"],
        ["Kill-switch drill, 18 Nov", "Halt blocks buys, allows sells, leaves an intact trail",
         "PASS, 5 of 5 criteria, on the personal paper account",
         "docs/validation/2026-11-18-kill-switch-drill.md"],
        ["Synthetic-breach drill, 21 Nov", "A breach is detected once, an exit is reserved and not sent, "
         "nothing reaches the broker",
         "PASS on a pinned clock, 11 of 13 criteria; delivery and operator confirmation NOT RUN",
         "docs/validation/2026-11-21-synthetic-breach-drill.md"],
        ["Calendar drift check", "The pinned NYSE session tables still match the published calendar",
         "Wired into the live card brief 21 Nov; first unattended run Mon 23 Nov 13:05Z; alert-only",
         "src/tyche/nyse_calendar.py, scripts/refresh_calendar.py"],
        ["deploy_managed_agents.py verify", "The live cloud agents match the repo: pins, prompt hashes, "
         "tool lists, skill versions",
         "Run after every re-pin; it caught a latent 10-tool grant the template had never applied (L-046)",
         "scripts/deploy_managed_agents.py"],
        ["Tuning versus evaluation", "A change made the desk better, not merely different",
         "Pins and diffs: done. A fixed set of evaluation prompts re-run after each change: not recorded, "
         "still owed",
         "docs/competition/bonus-tips.md tip H6"],
    ]
    h = table(s, M, y, CW,
              ["Check", "What it proves", "What the record says", "Where it lives"],
              rows, [2.0, 3.3, 4.3, 2.7], font=9.4, head_font=9.8, tag="s17 table", bold_col0=True,
              max_h=5.10)
    fy = y + h + 0.14
    txt(s, M, fy, CW, 6.98 - fy,
        [P("Still owed, stated as owed: the fixed evaluation-prompt suite (H6), a live-session breach drill "
           "with the operator present, and the performance pack rebuilt from the Drive ledger rather than "
           "the laptop's drill copy. Every one of them is in PRD §7 or the bonus-tips table with a closing "
           "condition, not in a footnote I hope nobody reads.", size=10.4, color=DARK, line=1.12)],
        tag="s17 foot")
    notes(s, "The handbook rewards verification, and a judge cannot audit a trading system by watching it "
             "trade. So this table is the audit menu: the automated suite, the journal chain check, the "
             "documentation consistency tests, the rules-freeze comparison, two recorded drills, the "
             "calendar drift check, and a command that re-reads the live cloud agents against the "
             "repository. Two entries deserve attention. The 21 November drill passes eleven criteria and "
             "explicitly marks two as not run, because the alert routing was never approved and I was not "
             "sitting at the desk. The last row is the one I am not allowed to claim: I pin and diff every "
             "change, but I have not built the fixed evaluation-prompt suite that would prove a prompt edit "
             "improved behavior. The test counts differ between documents because the suite is growing "
             "daily; I list all three numbers rather than picking the flattering one.")


def divider(prs, section, name, pct, claim_head, claims, evidence, note):
    s = add_slide(prs, dark=True)
    kicker(s, section)
    txt(s, M + 0.35, 2.05, CW - 0.7, 1.1,
        [P(name, size=40, color=WHITE, bold=True, font=HEAD, line=1.0, after=6),
         P(pct, size=15, color=OFFWHITE, line=1.12)], tag="div title")
    paras = [P(claim_head, size=12, color=AMBER, bold=True, line=1.05, after=8)]
    for c in claims:
        paras.append(P(c, size=12, color=WHITE, line=1.16, after=6))
    paras.append(P(evidence, size=10.5, color=AMBER, line=1.1, before=6))
    txt(s, M + 0.35, 3.9, 8.9, 2.6, paras, tag="div body")
    notes(s, note)
    return s


def s18_divider_strategy(prs):
    divider(prs, "SECTION 2 OF 4", "Strategy and risk design",
            "30% of the score: thesis, edge, invalidation conditions, position limits, drawdown "
            "responses and kill switches",
            "What this section claims",
            ["Five strategy ids with a written thesis and a frozen rules hash each; three of them are "
             "allowed to buy today, and the switch that decides which is an operator click, not a "
             "code change.",
             "Every lane states, in its own document, the condition that makes its trade wrong - not just "
             "the condition that makes it right.",
             "Named limits in one YAML file, each with a rule id and a test that names it back, and two "
             "recorded drills that shut the desk down on purpose."],
            "Slides 19-24. Evidence: playbook/, config/risk.yaml, docs/risk-card.md, "
            "src/tyche/risk.py, docs/validation/.",
            "The second thirty percent. This is the part a trading judge reads hardest, because an agent "
            "framework with no idea is just a scheduler. I will show the five strategies as they are "
            "registered - including the ones that are switched off - the invalidation condition for each, "
            "the numeric limits the kernel enforces, and two drills where I broke the desk deliberately "
            "and recorded what happened. The handbook asks specifically for invalidation conditions and "
            "kill switches, and those get their own slides.")


def s19_book(prs):
    s = add_slide(prs)
    y = title(s, "The strategy book, as registered",
              "playbook/INDEX.yaml is the authority on what exists. An id is claimed once and kept forever "
              "(L-029), and a row without a thesis file cannot be called live.")
    rows = [
        ["PB-001\nRegime rotation (ETFs)",
         "Holds a basket of broad ETFs. Four market checks set a risk gate (SPY above its 200-day average, "
         "golden cross, calm volatility, credit trend). Lean into the strongest sleeves; go to cash when "
         "the gate turns risk-off.",
         "Weeks", "25%", "ON", "PB-001 page\n819ad06e35f0"],
        ["PB-002\nTactical stocks",
         "Single stocks from a short approved list the operator picks: Microsoft plus five staples "
         "(KO, PG, JNJ, PEP, MCD). Every trade needs its own written reason, a stop, and a target worth at "
         "least 1.5 times the risk.",
         "Days", "45%", "ON", "PB-002 page (23 Nov)\nd5ef9567c736"],
        ["PB-003\nTactical options",
         "The same picks bought as one long call or one long put instead of shares, closed the same day. "
         "Defined risk: the most that can be lost is the premium paid. No shorts on the platform at all.",
         "Same day", "25%", "OFF", "No page - planned\nshares d5ef9567c736"],
        ["PB-004\nIntraday breakout (scalp)",
         "Five chip stocks on one-minute bars. Buy the break above the last five bars, stop 0.25% below "
         "entry, target twice the risk, out within 20 minutes, flat before the close.",
         "Minutes", "20%", "OFF", "PB-004 page\n72077d5d4808"],
        ["PB-007\nFib 50% pullback",
         "In a stock already trending up, buy the halfway retracement of the last leg up with a limit "
         "order, stop under the deeper pullback level, aim at the prior high. One entry per leg, no "
         "scaling, no re-entry.",
         "1-10 sessions", "20%", "ON", "PB-007 page\ne26f006da28a"],
    ]

    def col(r, c, val):
        if c == 4:
            return GREEN if val == "ON" else BRICK
        return INK

    h = table(s, M, y, CW,
              ["Lane", "What it believes, in plain English", "Holds", "Cap of NAV", "Today", "Thesis + rules hash"],
              rows, [1.95, 5.25, 1.0, 0.95, 0.75, 1.95], font=9.5, head_font=9.8, tag="s19 table",
              bold_col0=True, max_h=4.05, cell_colors=col,
              aligns=[PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.RIGHT, PP_ALIGN.CENTER,
                      PP_ALIGN.LEFT])
    cy = y + h + 0.16
    cw3 = (CW - 2 * 0.18) / 3
    cards = [
        ("One lane, two ids", GREEN, T_GREEN,
         ["PB-002 and PB-003 are one code path with one parameter file, so they freeze to the same hash: "
          "editing config/tactical.yaml re-registers the pair (ADR 0014)."]),
        ("Off is a real state", BRICK, T_BRICK,
         ["PB-004 was switched off by the operator on 23 Nov, PB-003 never switched on. A switch lives in "
          "data/strategies.json so flipping it blocks new entries without moving any rules hash (L-037)."]),
        ("PB-005 parked, PB-006 planned", AMBER, T_AMBER,
         ["They hold an id and nothing else. A roster row without a file cannot be marked live, which is "
          "what keeps an undocumented lane from being called a strategy."]),
    ]
    for i, (head, acc, tint, lines_) in enumerate(cards):
        card(s, M + i * (cw3 + 0.18), cy, cw3, 6.90 - cy, head,
             [P(ln, size=9.6, color=INK, line=1.09, after=4) for ln in lines_],
             accent=acc, fill=tint, head_size=10.8, tag=f"s19 card {i}")
    notes(s, "Five strategy ids, and only three of them can buy today. The plain-English column is the "
             "thesis: what has to be true in the market for the trade to work. The cap column is the "
             "lane's share of the account, and the sum of the caps is checked at load time - that check "
             "has a hole I show on the next slide. The last column matters most for judging: every lane "
             "has a written page and a frozen hash of the exact rules file it trades under, so a result "
             "can be tied to a document rather than to a memory. PB-004 is genuinely off as of this "
             "morning - the operator switched it - and PB-003 has never been on, because options are "
             "blocked behind the protection monitor. I am not claiming five live strategies.")


def s20_allocation(prs):
    s = add_slide(prs)
    y = title(s, "Where the money is allowed to go",
              "config/strategies/*.yaml plus config/tactical.yaml, read through src/tyche/lanes.py and "
              "mirrored in the desk's allocation table. Caps, not positions: a cap blocks new buys, it "
              "never forces a sale.")
    # --- native horizontal bar chart of lane caps
    labels = ["PB-007\nFib pullback", "PB-004\nScalp", "PB-003\nOptions", "PB-002\nTactical stocks",
              "PB-001\nETF rotation"]
    caps = [20.0, 20.0, 25.0, 45.0, 25.0]
    on = [True, False, False, True, True]
    cd = CategoryChartData()
    cd.categories = labels
    cd.add_series("Cap as a share of account value (%)", caps)
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(M), Inches(y), Inches(6.35),
                           Inches(3.42), cd)
    ch = gf.chart
    chart_base(ch, font=9.2, legend=False)
    plot = ch.plots[0]
    plot.gap_width = 46
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = '0"%"'
    dl.number_format_is_linked = False
    dl.font.size = Pt(9.6)
    dl.font.bold = True
    dl.font.color.rgb = INK
    ser = plot.series[0]
    for i, is_on in enumerate(on):
        pt = ser.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = GREEN if is_on else RGBColor(0xB4, 0xC2, 0xB9)
    axis_style(ch, val_fmt='0"%"', vmin=0, vmax=50, cat_size=8.8)
    txt(s, M, y + 3.50, 6.35, 0.52,
        [P("Green = the lane may buy today. Grey = switched off (PB-003 also sits behind "
           "options_enabled: false).", size=9.4, color=MUT, line=1.08)], tag="s20 chart note")
    # --- stat tiles
    tx = M + 6.62
    tw = CW - 6.62
    th = 0.87
    tiles = [
        ("95%", "portfolio gross cap: the book may hold 95% of NAV in positions, 5% must stay cash",
         GREEN),
        ("90%", "caps on the lanes that can buy today: 25 + 45 + 20. Inside the gross cap.", GREEN),
        ("115%", "if every switch were on. The cap-sum guard reads yaml only, so an operator switch bypasses "
         "it (PRD §7 item 15)", BRICK),
        ("34%", "PB-001's actual weight against its own 25% cap - cut on 19 Nov after the buys; a cap "
         "blocks new buys, never forces a sale", AMBER),
    ]
    for i, (big, small, acc) in enumerate(tiles):
        ty = y + i * (th + 0.10)
        box(s, tx, ty, tw, th,
            [P(big, size=19, color=acc, bold=True, font=HEAD, line=1.0, after=1),
             P(small, size=9.3, color=INK, line=1.06)], fill=T_GRAY, line=acc, tag=f"s20 tile {i}",
            pad=0.10)
    cy = y + 4.06
    box(s, M, cy, CW, 6.90 - cy,
        [P("The current book, from the published feed (20 Nov broker capture, challenge account)",
           size=10.6, color=DARK, bold=True, font=HEAD, line=1.04, after=4),
         P("SPY 28 shares at 20.2% of NAV   ·   MSFT 39 shares at 19.5%   ·   EFA 142 shares at 14.1%   ·   "
           "cash 46.3%   ·   account value 98,754.20 against a 100,000.00 start.   "
           "Route to change a cap: pull request + both playbook hash lines + `tyche rules-freeze --record` "
           "from a console session + the card's BUDGET line. Planned next weekend: cut PB-002 from 45% to 25%.",
           size=9.6, color=INK, line=1.10)],
        fill=T_BLUE, line=BLUE, tag="s20 book", pad=0.12)
    notes(s, "These are the caps, not the positions: a cap says how much room a lane may take, and it "
             "blocks new buys rather than forcing a sale. Three of the five lanes can buy today, and their "
             "caps add to 90% against a 95% portfolio limit, which is deliberate. The 115% tile is an "
             "honest defect: the config loader refuses to start when the caps in the YAML files add past "
             "the gross limit, but PB-007 was switched on through the operator's switch file, which needs "
             "no re-hash and so does not pass that check. The per-order gross test still holds, so it is a "
             "fairness problem - the first lane to buy takes the room - not a safety hole, and the fix is "
             "planned for next weekend. The bottom strip is the real book from the published feed: about "
             "half cash, three ETF-and-stock positions, and the account value that the return section "
             "measures.")


def s21_invalidation(prs):
    s = add_slide(prs)
    y = title(s, "What would prove each trade wrong",
              "The handbook asks for invalidation conditions, so each lane carries its own list in its own "
              "document. Every entry also carries them in the journal, so the auditor and the exit path "
              "read the same list the thesis wrote.")
    lanes = [
        ("PB-001  ballast", GREEN, T_GREEN,
         ["Momentum for a holding falls to zero, or the risk gate flips to risk-off (fewer than 2 of the 4 "
          "market checks pass) - exit at the next rebalance.",
          "Protection type is rebalance, not stop: an alert on ballast is never read as an exit.",
          "No broker-native stop exists on the simulator."]),
        ("PB-002  tactical stocks", BLUE, T_BLUE,
         ["The price trades at or through the stop; the researcher marks the setup invalidated; the exit "
          "deadline arrives; the setup's expiry date passes. Any one produces a limit sell at the bid.",
          "One entry attempt per setup, ever. Fresh invalidation can tighten protection, never move a stop "
          "away."]),
        ("PB-004  scalp", AMBER, T_AMBER,
         ["Last price at or below limit x 0.9975 - a fixed 0.25% stop; or the 20-minute clock; or the "
          "flatten time 10 minutes before the close.",
          "There is no chart-level \"thesis dead\" condition beyond those, and the stop is fixed at request "
          "time, so there is nothing to widen."]),
        ("PB-007  fib pullback", BRICK, T_BRICK,
         ["Before a fill: a daily close below the 0.618 retracement, or the regime filter failing, cancels "
          "the plan with no re-arm on that leg.",
          "After a fill: stop hit, a daily close below the 200-day average, the 10-session deadline, or a "
          "sourced material event marked invalidated. All five land in the plan's invalidation_rules."]),
    ]
    cw = (CW - 3 * 0.18) / 4
    for i, (nm, acc, tint, lines_) in enumerate(lanes):
        paras = [P(nm, size=11.4, color=acc, bold=True, font=HEAD, line=1.04, after=6)]
        for ln in lines_:
            paras.append(P(ln, size=9.6, color=INK, line=1.09, after=5))
        box(s, M + i * (cw + 0.18), y, cw, 2.86, paras, fill=tint, line=acc, tag=f"s21 lane {i}", pad=0.12)
    cy = y + 3.04
    cw2 = (CW - 0.20) / 2
    card(s, M, cy, cw2, 6.88 - cy, "When a lane itself gets retired",
         [P("PB-002: two consecutive weeks of negative realized R with at least ten closed trades, or one "
            "loss that exceeds its planned stop risk by more than the fee model allows - the lane goes back "
            "to Off until the thesis page is revised and re-registered.", size=9.6, color=INK, line=1.09,
            after=5),
          P("PB-007: after 30 or more closed trades, expected R at or below zero, profit factor under 1.2, "
            "or sleeve drawdown over 4% - retire it with `tyche strategy-score` (ADR 0016). Inside the "
            "window, 6 consecutive full-R losses disable the lane for review.", size=9.6, color=INK,
            line=1.09)],
         accent=BRICK, fill=T_BRICK, head_size=11.2, tag="s21 retire")
    card(s, M + cw2 + 0.20, cy, cw2, 6.88 - cy, "And the rules that override a lane",
         [P("config/risk.yaml is the same for all five lanes: a halt blocks buys and never blocks a "
            "protective sell; a 2.5% daily loss blocks buys; drawdown of 4% halves new buy size and 6% "
            "blocks buys outright.", size=9.6, color=INK, line=1.09, after=5),
          P("This is the part the LLM cannot negotiate: an agent can argue with a plan, not with risk.py. "
            "The verdict names the rule id and the number it tripped on.", size=9.6, color=INK, line=1.09)],
         accent=GREEN, fill=T_GREEN, head_size=11.2, tag="s21 kernel")
    notes(s, "A thesis says what has to be true. Invalidation says what would prove it wrong, and the "
             "handbook weights that explicitly, because most paper-trading entries describe only the first "
             "half. Each of the four live-ish lanes has its own list, in its own playbook page, and each "
             "entry writes those rules into the journal so the auditor reviews the exit plan rather than "
             "the entry story. The two cards at the bottom are the layer below: a lane gets retired when "
             "its realized results say so, and the shared risk kernel overrides everything on a bad day - "
             "a halt stops buys while still allowing exits, because a desk that cannot sell during a "
             "problem is a desk that makes the problem bigger. Note the honesty in PB-001: its protection "
             "type is rebalance, so a warning on ballast is not an exit.")


def s22_gates(prs):
    s = add_slide(prs)
    y = title(s, "The gates every order passes",
              "Three checkpoints in code, in this order. An agent can propose, but only these decide - and "
              "each one refuses with a rule id that lands in the journal.")
    gates = [
        ("GATE 1  risk.py  -  the numbers", GREEN, T_GREEN,
         ["Every limit lives in config/risk.yaml and is checked before an order is sent: size, risk, weights, "
          "cash, loss, turnover.",
          "The verdict is ALLOW, BLOCK or REQUIRE_APPROVAL, and a refusal names the rule and the number."]),
        ("GATE 2  approvals.py  -  the human", AMBER, T_AMBER,
         ["Live mode asks a person for that exact order and waits. Nothing is sent on a general or stale "
          "approval.",
          "Paper mode has no human step, but every decision still runs through the same function: one path "
          "to audit, not two."]),
        ("GATE 3  lifecycle reserve  -  the way out", BLUE, T_BLUE,
         ["Before a buy is sent the exit is paid for: a hold of 2% of NAV per open order, plus a journal row "
          "for the exit.",
          "No reserve, no buy. A position is never owned without a written plan to leave it."]),
    ]
    lw = 4.75
    for i, (nm, acc, tint, lines_) in enumerate(gates):
        gy = y + i * 1.48
        paras = [P(nm, size=11.6, color=acc, bold=True, font=HEAD, line=1.02, after=4)]
        for ln in lines_:
            paras.append(P(ln, size=9.6, color=INK, line=1.09, after=4))
        box(s, M, gy, lw, 1.34, paras, fill=tint, line=acc, tag=f"s22 gate {i}", pad=0.11)
        if i < 2:
            arrow_d(s, M + lw / 2 - 0.13, gy + 1.38, 0.26, 0.08, color=acc)
    ny = y + 3 * 1.48 - 0.14 + 0.14
    box(s, M, ny, lw, 1.18,
        [P("Deliberately not a fourth gate", size=11.2, color=BRICK, bold=True, font=HEAD, line=1.02,
           after=4),
         P("The protection monitor can only raise a flag that leads to a human-approved exit. It has no "
           "order path and no trading authority of its own (ADR 0013). The scheduler adds its own rule: an "
           "order already recorded as sent is never sent twice.", size=9.6, color=INK, line=1.08)],
        fill=T_BRICK, line=BRICK, tag="s22 monitor", pad=0.11)
    rx = M + lw + 0.24
    rw = CW - lw - 0.24
    rows = [
        ["One order", "30% of NAV ceiling, $500 floor unless closing",
         "order.max_notional and order.min_notional. A buy that large is refused; so is a token order."],
        ["Risk per buy", "1% of NAV (quantity x distance to stop)",
         "trade.risk_budget. The stop decides the size, never the other way round."],
        ["One asset", "40% of NAV, +0.25% tolerance",
         "position.max_weight. Same ceiling as the competition rules; sizing aims under 38%."],
        ["Whole book", "95% gross, 5% cash floor",
         "portfolio.gross and portfolio.min_cash block buys. De-risking sells are exempt, so the way out "
         "stays open. Both fired once in the real log."],
        ["Price sanity", "last >= $1.00, limit within 3% of last",
         "market.allowed, universe.membership, price.minimum, price.limit_deviation. US only, universe "
         "only, $1 is the competition floor."],
        ["The day", "-2.5% loss blocks buys; 300% turnover; 120 orders",
         "loss.daily_limit, turnover.daily (3 rows in the feed), orders.daily_count. The competition "
         "ceiling is 200 orders a day."],
        ["Drawdown ladder", "4% halves new buy size, 6% blocks buys",
         "soft_drawdown_pct and drawdown.hard. A bad stretch shrinks the desk before it stops it."],
        ["Kill switch", "halt.json, written by a person",
         "halt.active blocks every buy and passes every sell. Desk button, CLI, Telegram /halt and the "
         "scheduler stopper all write the same file."],
        ["The one exit number", "5% collar below the journaled stop",
         "exit_collar_pct is the only operator-set number in the exit path. Anything the kernel cannot "
         "ground is refused with a reason, never filled in with a guess."],
    ]
    th_ = table(s, rx, y - 0.10, rw, ["Guard", "Number in config/risk.yaml", "What happens when it trips"],
                rows, [1.30, 2.24, 3.54], font=9.1, head_font=9.5, tag="s22 table", bold_col0=True,
                max_h=5.30)
    txt(s, rx, y - 0.10 + th_ + 0.08, rw, 0.52,
        [P("Every row above is a config key with a rule id and at least one named test in "
           "tests/test_risk.py. The card that lists them all is docs/risk-card.md.",
           size=9.2, color=MUT, line=1.07)], tag="s22 table note")
    notes(s, "Three gates, and they are code, not policy language. The first one is arithmetic: the limits "
             "live in one YAML file, are checked before an order leaves, and a refusal names the rule id and "
             "the number it tripped on. The second is the human - in live mode a person clicks approve for "
             "that exact order, and in paper mode the same function runs with no human step, which is why "
             "one audit trail covers both accounts. The third is the one I would point a judge at: before a "
             "buy is sent, the desk reserves the cash its exit will need and writes the exit plan to the "
             "journal first, so a position cannot exist without a way out. The red card matters too: the "
             "protection monitor is deliberately not a fourth gate, it has no order path, by ADR 0013. On "
             "the right is the table the risk card carries, with the real numbers, including the one the "
             "operator owns - a drafted exit may sit 5% below the journaled stop, and that is the only "
             "discretion in the path. De-risking sells are exempt from the buy-side limits, which is on "
             "purpose: a desk that cannot sell during a problem makes the problem bigger.")


def s23_drills(prs):
    s = add_slide(prs)
    y = title(s, "We broke it on purpose, twice",
              "A safety story is only worth its drill record. Two exist, both written by the operator, both "
              "naming what they did not prove.")
    dw = (CW - 0.22) / 2
    # left: kill switch
    box(s, M, y, dw, 3.44,
        [P("KILL SWITCH DRILL - 18 Nov 2026, paper", size=12.6, color=GREEN, bold=True, font=HEAD,
           line=1.03, after=2),
         P("Result: PASS, 5 of 5 criteria. Runtime 14:54-15:06 UTC, personal paper account.", size=10.2,
           color=INK, bold=True, line=1.05, after=6),
         P("1. Wrote halt.json by hand; readback confirmed active=true and a real ISO timestamp. 14:54.",
           size=9.7, color=INK, line=1.1, after=4),
         P("2. Ran the 14:55Z intraday prompt: the coordinator read the card, saw the halt, bought nothing, "
           "and reported it. No order call.", size=9.7, color=INK, line=1.1, after=4),
         P("3. The desk showed an amber banner and disabled every buy control while sells stayed available.",
           size=9.7, color=INK, line=1.1, after=4),
         P("4. Cleared by hand; the 15:05Z run traded normally again. 15:06.", size=9.7, color=INK,
           line=1.1, after=4),
         P("5. A refusal row was recorded before the halt on purpose, so the log path is proven to carry a "
           "rejection with a reason.", size=9.7, color=INK, line=1.1, after=7),
         P("The drill's own gaps, quoted: one refusal row proves the write path, not that the kernel refuses "
           "every class of order; the desk was checked against the renderer, not the UI running on the "
           "deployed URL.", size=9.6, color=BRICK, line=1.1)],
        fill=T_GREEN, line=GREEN, tag="s23 kill", pad=0.13)
    # right: synthetic breach
    bx = M + dw + 0.22
    box(s, bx, y, dw, 3.44,
        [P("SYNTHETIC BREACH DRILL - 21 Nov 2026, pinned clock", size=12.6, color=BLUE, bold=True,
           font=HEAD, line=1.03, after=2),
         P("Result: PASS on 11 of 13 criteria. Delivery and operator confirmation: NOT RUN.", size=10.2,
           color=INK, bold=True, line=1.05, after=6),
         P("Setup: 2 open orders, a fake loss past the per-lane trigger and past the 6% account drawdown, a "
           "journal with no existing exit row, clock pinned to Sat 21 Nov 03:00Z.", size=9.7, color=INK,
           line=1.1, after=4),
         P("Latency to detection: 0.03s from the state files and 0.05s through the API. An immediate exit "
           "reserved 0.07s, the deferred one 0.05s - the desk is not slow when it matters.", size=9.7,
           color=INK, line=1.1, after=4),
         P("One exit per order, the exit written before the alert, the alert exactly once, a second scan "
           "quiet, the live guard returning no_order, and nothing sent to any broker.", size=9.7, color=INK,
           line=1.1, after=4),
         P("The two not-run rows say the alert routing was never approved and nobody was at the desk. Not "
           "skipped quietly - marked NOT RUN in the record.", size=9.6, color=BRICK, line=1.1)],
        fill=T_BLUE, line=BLUE, tag="s23 breach", pad=0.13)
    cy = y + 3.62
    cw3 = (CW - 2 * 0.20) / 3
    card(s, M, cy, cw3, 6.90 - cy, "Both used fixtures, by choice",
         [P("The 18 Nov halt was set by hand and the refusal row was planted; the 21 Nov loss was injected. "
            "No natural breach happened in the window, and the record says so on its face.",
            size=9.6, color=INK, line=1.09, after=5),
          P("Re-running the 18 Nov drill on the challenge account is planned, not done.",
            size=9.6, color=INK, line=1.09)],
         accent=AMBER, fill=T_AMBER, head_size=10.9, tag="s23 fixture")
    card(s, M + cw3 + 0.20, cy, cw3, 6.90 - cy, "What the breaches were built from",
         [P("The 21 Nov fixtures were copied from the published feed, not invented: 85.8% gross exposure "
            "against a 95% cap, a 2.46% cash buffer against a 2% floor, and 3 open orders against a 2-order "
            "reserve - so the trigger had to be the injected loss, which is what the record states.",
            size=9.6, color=INK, line=1.09)],
         accent=GREEN, fill=T_GREEN, head_size=10.9, tag="s23 real")
    card(s, M + 2 * (cw3 + 0.20), cy, cw3, 6.90 - cy, "The part we have not drilled",
         [P("Nothing has ever tripped on its own at 03:00 with nobody watching. The unattended path is built "
            "and unit-tested, and the exit is deliberately queued rather than sent.", size=9.6, color=INK,
            line=1.09, after=5),
          P("So this deck says the response is reserved and gated, never that it is autonomous.",
            size=9.6, color=INK, line=1.09)],
         accent=BRICK, fill=T_BRICK, head_size=10.9, tag="s23 notdrilled")
    notes(s, "These two files are the reason I can talk about safety instead of promising it. On the 18th I "
             "set the halt by hand, ran the real scheduled task against it, watched the coordinator buy "
             "nothing, watched the desk refuse the buy button and keep the sell button, then cleared it and "
             "watched trading resume - all inside twelve minutes, all timestamped. On the 21st I pinned the "
             "clock, injected a loss past both triggers, and checked thirteen things: how fast detection "
             "was, that exactly one exit got reserved, that the exit was journaled before the alert, that a "
             "second scan stayed quiet, and that nothing reached a broker. Two rows say NOT RUN because the "
             "alert routing was never approved and nobody was at the desk - I left them visible rather than "
             "reporting thirteen of thirteen. Both drills use injected fixtures, and the right card shows "
             "they were built from the real published feed. What we have not done is a live unattended "
             "breach, so this deck never claims the desk acts alone at night.")


def s24_lifecycle(prs):
    s = add_slide(prs)
    y = title(s, "From an idea to a fill, and back out again",
              "Seven stages. The machine writes the plan and the numbers; a person writes the reason. Four "
              "rules keep the two from being confused.")
    stages = [
        ("1  IDEA", "One human writes a falsifiable reason, not a summary. The agent is forbidden from "
         "generating the entry reason."),
        ("2  PLAN", "The agent prices real quotes, sizes the trade and emits the full envelope: stop, "
         "target, expiry, invalidation."),
        ("3  GATE", "risk.py checks the numbers; approvals.py checks the human. A refusal ends the story "
         "here, as a journal row."),
        ("4  FILL", "The order goes to the paper account; the fill comes back and becomes an event."),
        ("5  MONITOR", "The tick loop and the protection monitor compare price with plan. Alerts, no "
         "orders."),
        ("6  EXIT", "Stop, target, deadline or invalidation. A pre-armed exit fires within its stated "
         "bounds without a person."),
        ("7  LEDGER", "Realized R goes into the expectancy table; the journal row is chained; the feed is "
         "republished."),
    ]
    sw = (CW - 6 * 0.26) / 7
    for i, (head, body) in enumerate(stages):
        sx = M + i * (sw + 0.26)
        acc = GREEN if i < 3 else (BLUE if i < 6 else AMBER)
        box(s, sx, y, sw, 1.90,
            [P(head, size=11.4, color=acc, bold=True, font=HEAD, line=1.0, after=5),
             P(body, size=9.2, color=INK, line=1.08)], fill=T_GRAY, line=acc, tag=f"s24 stage {i}",
            pad=0.10)
        if i < 6:
            arrow_r(s, sx + sw + 0.02, y + 0.72, 0.22, 0.24, color=acc)
    ry = y + 2.08
    box(s, M, ry, CW, 0.62,
        [P("A fill is not the end of the story: the exit deadline is a hard field with no default, so an "
           "open trade always has a time it must be re-examined at - and the same record feeds both the "
           "safety story and the performance story.", size=9.9, color=INK, line=1.08)],
        fill=T_BLUE, line=BLUE, tag="s24 strip", pad=0.11)
    cy = ry + 0.80
    cw2 = (CW - 0.20) / 2
    rules = [
        ("Reason is human, math is machine", BRICK, T_BRICK,
         "The agent may reject a trade and recompute risk, but it may not author a reason it did not "
         "observe. That is why a refusal is logged with the same care as a fill."),
        ("No silent state change", GREEN, T_GREEN,
         "A status transition is an event with a payload, not a field someone edited. Two agents cannot "
         "overwrite each other's meaning, and the chain makes the sequence checkable."),
        ("One writer, one clock", BLUE, T_BLUE,
         "The laptop owns every write; cloud cards only read and report. Times are UTC to the second in the "
         "data and ET in the prose, because the gap between the zones is exactly one trading day (L-036)."),
        ("A claim needs a file", AMBER, T_AMBER,
         "Any change to a strategy or risk file must name the tests and the record that cover it, and "
         "anything unverifiable is labelled 'planned' or 'not recorded' rather than asserted."),
    ]
    for i, (head, acc, tint, body) in enumerate(rules):
        rx = M + (i % 2) * (cw2 + 0.20)
        ryy = cy + (i // 2) * 1.30
        box(s, rx, ryy, cw2, 1.16,
            [P(head, size=11.0, color=acc, bold=True, font=HEAD, line=1.02, after=4),
             P(body, size=9.6, color=INK, line=1.09)], fill=tint, line=acc, tag=f"s24 rule {i}", pad=0.11)
    notes(s, "This is the whole life of a trade on one line, left to right, and the interesting part is what "
             "the machine cannot do. Stage one is written by a person: the repository rule is that the agent "
             "may not author the entry reason, because a reason generated after seeing the numbers is not "
             "evidence. Stages two and three are pure code - the agent quotes, sizes and explains, then "
             "arithmetic and a human decide. Stage six is where the design has grown most: a pre-armed "
             "exit, filed at entry time and bounded by that plan, can act before a person replies. The four "
             "cards are the rules that keep the story honest: reasons are human, state changes are events, "
             "one machine writes, and any claim points at a file. If a judge asks how an agent did not run "
             "away with the account, these four lines are the short answer.")


def s25_divider_return(prs):
    divider(prs, "SECTION 3 OF 4", "Risk-adjusted return",
            "25% of the score: risk-adjusted return, and the discipline to report it honestly",
            "What this section claims",
            ["Four trading days, three daily marks, one closed batch of three trades. The account is down "
             "1.25%; SPY fell 5.82% over the same days. Both numbers are printed, and the first one is the "
             "one that matters.",
             "The comparison is against the baseline the handbook names, from one generated file, with the "
             "report's own blanks left blank.",
             "Every decision the desk refused is on the slide next to it, because a log of trades that did "
             "not happen is the cheapest evidence of discipline there is."],
            "Slides 26-28. Evidence: docs/performance/2026-11-23-metrics.md, "
            "desk-site/web/data/state.json, journal rows.",
            "This is the section I am least comfortable presenting, and that is the point. Twenty-five "
             "percent of the score is risk-adjusted return, and I have four days of data on a paper "
             "account that is down one and a quarter percent. What I can offer instead of a good number is "
             "a defensible one: a baseline computed the way the handbook describes, one generated file as "
             "the single source for every figure, no cherry-picked window, and the refusals logged beside "
             "the fills. If a judge wants to check a number, the next three slides point at the file it "
             "came from.")


def s26_baseline(prs):
    s = add_slide(prs)
    y = title(s, "The baseline, computed one way",
              "Every figure on this slide is a cell from docs/performance/2026-11-23-metrics.md, the file "
              "`tyche performance report` generates. Nothing is re-typed by hand and no SPY number is "
              "computed here.")
    rows = [
        ["2026-11-17", "100,000.00", "start", "-", "+0.00%", "+0.00%", "732.44", "+0.00%", "+0.00%"],
        ["2026-11-18", "99,931.44", "feed", "-0.07%", "-0.07%", "-0.07%", "730.20", "-0.31%", "+0.24%"],
        ["2026-11-19", "99,927.13", "plan", "-0.00%", "-0.07%", "-0.07%", "715.87", "-2.26%", "+2.19%"],
        ["2026-11-20", "98,754.20", "feed", "-1.17%", "-1.25%", "-1.25%", "689.81", "-5.82%", "+4.57%"],
    ]

    def col(r, c, val):
        if c == 8 and isinstance(val, str) and val.startswith("+"):
            return GREEN
        if c in (3, 4, 5, 7) and isinstance(val, str) and val.startswith("-"):
            return BRICK
        return INK

    th_ = table(s, M, y, CW, ["Date", "Account value", "Mark", "Day", "Since start", "Drawdown",
                              "SPY close", "SPY since base", "Desk minus SPY"],
                rows, [1.32, 1.62, 0.82, 0.92, 1.30, 1.20, 1.20, 1.85, 2.08], font=9.8, head_font=9.6,
                tag="s26 table", bold_col0=True, max_h=1.90, cell_colors=col,
                aligns=[PP_ALIGN.LEFT, PP_ALIGN.RIGHT, PP_ALIGN.LEFT, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT,
                        PP_ALIGN.RIGHT, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT])
    ny = y + th_ + 0.06
    txt(s, M, ny, CW, 0.60,
        [P("Mark basis, from the same file: close is the broker's total asset at the end-of-day reconcile, "
           "plan is a pre-trade NAV, feed is the last published desk mark for that date and can be an "
           "intraday capture. SPY is always the close, so a feed row compares an intraday mark with a "
           "closing price - the report calls its last column approximate until that day reconciles.",
           size=9.3, color=MUT, line=1.08)], tag="s26 basis")
    cy = ny + 0.74
    ch_h = 6.88 - cy
    cd = CategoryChartData()
    cd.categories = ["17 Nov", "18 Nov", "19 Nov", "20 Nov"]
    cd.add_series("Desk account, % since start", (0.00, -0.07, -0.07, -1.25))
    cd.add_series("SPY baseline, % since base", (0.00, -0.31, -2.26, -5.82))
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(M), Inches(cy), Inches(6.55),
                           Inches(ch_h), cd)
    ch = gf.chart
    chart_base(ch, font=9.5, legend=True)
    plot = ch.plots[0]
    cols = [GREEN, RGBColor(0x8B, 0x9A, 0x92)]
    for i, ser in enumerate(plot.series):
        ser.format.line.color.rgb = cols[i]
        ser.format.line.width = Pt(2.4)
        ser.smooth = False
        line_marker(ser, cols[i], 6)
    axis_style(ch, val_fmt='0.0"%"', vmin=-7, vmax=1, cat_size=9.5, cat_low=True)
    box(s, M + 6.80, cy, CW - 6.80, ch_h,
        [P("Read this honestly", size=13.6, color=AMBER, bold=True, font=HEAD, line=1.02, after=7),
         P("The outperformance is +4.57% while losing money. The account is down 1.25%; SPY fell 5.82% in "
           "the same three sessions. Falling less fast is not the same as being right.", size=10.0,
           color=INK, line=1.10, after=6),
         P("Where the cushion came from: 46.3% of the book was cash on 20 Nov, and the only closed trades "
           "were three small scalps. The desk did not dodge the drop by reading it; it was early enough in "
           "the build that most of the money had not been deployed.", size=10.0, color=INK, line=1.10,
           after=6),
         P("The bar flatters SPY: the same starting cash into SPY at the 17 Nov close with no fees, per the "
           "report's own wording. It is the bar, not a strategy.", size=10.0, color=INK, line=1.10,
           after=6),
         P("Three daily marks. Volatility +10.44% annualized and Sharpe -10.03 come from n=3, and the "
           "report labels them provisional. I am not claiming a Sharpe.", size=10.0, color=BRICK,
           line=1.10)],
        fill=T_AMBER, line=AMBER, tag="s26 honest", pad=0.13)
    notes(s, "One file produced every number on this slide: the generated performance pack, which reads the "
             "journal, the published desk feed and the price CSVs, and marks a missing value as missing "
             "instead of filling it in. The table is the pack's daily-marks table, unchanged, including the "
             "dash in the first row where the record has no day change. The baseline is the same starting "
             "cash bought at the 17 November close of SPY with no fees, so it is slightly unfair to us and "
             "the report says so. Here is the honest reading: over four days the account is down 1.25 "
             "percent while SPY is down 5.82 percent, so the desk beat the bar by 4.57 percentage points "
             "while losing money. Most of that came from being half in cash early in the build, not from a "
             "correct call, and I would rather say that than dress it up. The volatility and Sharpe "
             "figures in the pack come from three marks, so they are reported as provisional and I have "
             "not turned them into a headline.")


def s27_results(prs):
    s = add_slide(prs)
    y = title(s, "Results so far, on the challenge account",
              "The published feed's daily marks for the competition account, from "
              "desk-site/web/data/state.json, tabulated by the same performance pack. Four trading days, "
              "start to now.")
    r1 = 1.95
    cd = CategoryChartData()
    cd.categories = ["17 Nov start", "18 Nov", "19 Nov", "20 Nov"]
    cd.add_series("Account value (USD)", (100000.00, 99931.44, 99927.13, 98754.20))
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(M), Inches(y), Inches(6.10), Inches(r1), cd)
    ch = gf.chart
    chart_base(ch, font=9.5, legend=False)
    plot = ch.plots[0]
    ser = plot.series[0]
    ser.format.line.color.rgb = GREEN
    ser.format.line.width = Pt(2.6)
    ser.smooth = False
    line_marker(ser, GREEN, 7)
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = '#,##0'
    dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.ABOVE
    dl.font.size = Pt(8.8)
    dl.font.color.rgb = MUT
    axis_style(ch, val_fmt='#,##0', vmin=98000, vmax=100500, cat_size=9.2)
    tx = M + 6.30
    tw = (CW - 6.30 - 0.14) / 2
    tiles = [
        ("-1.25%", "since the 100,000.00 start on 17 Nov", BRICK),
        ("+4.57%", "against the SPY baseline over the same three sessions", GREEN),
        ("46.3%", "of the account in cash, so 53.7% gross against a 95% ceiling", BLUE),
        ("3 of 3", "closed trades won: +66.39 net of 5.95 in modelled fees", AMBER),
    ]
    for i, (big, small, acc) in enumerate(tiles):
        box(s, tx + (i % 2) * (tw + 0.14), y + (i // 2) * 1.07, tw, 0.96,
            [P(big, size=19.5, color=acc, bold=True, font=HEAD, line=1.0, after=2),
             P(small, size=9.4, color=INK, line=1.07)], fill=T_GRAY, line=acc, tag=f"s27 tile {i}",
            pad=0.10)
    rows = [
        ["US.SPY", "PB-001 rotation", "28", "731.54", "712.80", "19,958.40", "20.2%", "-524.72"],
        ["US.MSFT", "PB-002 tactical", "39", "503.33", "492.70", "19,215.30", "19.5%", "-414.57"],
        ["US.EFA", "PB-001 rotation", "142", "100.50", "97.89", "13,900.38", "14.1%", "-369.91"],
        ["Cash", "unused buying power", "-", "-", "-", "45,680.12", "46.3%", "-"],
    ]

    def col(r, c, val):
        return BRICK if c == 7 and str(val).startswith("-") else INK

    tb_h = table(s, M, y + r1 + 0.12, CW, ["Position", "Lane", "Qty", "Avg cost", "Last", "Market value",
                                    "Weight", "Unrealized"],
          rows, [1.90, 1.15, 0.95, 1.50, 1.50, 1.90, 1.40, 2.03], font=9.5, head_font=9.4, tag="s27 book",
          max_h=2.00, bold_col0=True, cell_colors=col,
          aligns=[PP_ALIGN.LEFT, PP_ALIGN.LEFT] + [PP_ALIGN.RIGHT] * 6)
    cy = y + r1 + 0.16 + tb_h
    cw4 = (CW - 3 * 0.16) / 4
    cards = [
        ("Nothing here is a sample", BRICK, T_BRICK,
         "Three daily marks, three closed trades, 10 orders across two sessions against a 200-a-day "
         "ceiling. The feed holds five marks, three of them intraday captures from 18 Nov. A desk on day "
         "four, not a track record."),
        ("Expectancy is not recorded", AMBER, T_AMBER,
         "Win rate 100%, average win 2.54R - and no losing trade yet, so the pack leaves expected R and "
         "expected return blank. A formula with no losses is not an edge."),
        ("Unrealized outweighs realized", BLUE, T_BLUE,
         "Realized +66.39 against -1,309.20 open across the three positions. The account is down because of "
         "what it still holds, not what it closed."),
        ("One open lot has no stop", BRICK, T_BRICK,
         "The feed's MSFT lot carries a null stop and no initial risk. Every closed scalp had one, so the "
         "gap is in how that lot was recorded, not in the rule."),
    ]
    for i, (head, acc, tint, body) in enumerate(cards):
        box(s, M + i * (cw4 + 0.16), cy, cw4, 6.90 - cy,
            [P(head, size=10.9, color=acc, bold=True, font=HEAD, line=1.02, after=4),
             P(body, size=9.5, color=INK, line=1.08)], fill=tint, line=acc, tag=f"s27 card {i}", pad=0.11)
    notes(s, "This is the competition account as the desk publishes it. It started with 100,000 on 17 "
             "November and reads 98,754 on 20 November, so it is down 1.25 percent, and the line bends "
             "because the market fell while most of the book was invested. Three scalps closed on 19 "
             "November for 66.39 net of fees, and the three positions still open carry a little over 1,300 "
             "in unrealized loss, which is why realized profit and a falling account can both be true at "
             "once. The four cards are the limits I want a judge to apply: this is four days, not a track "
             "record; expectancy is blank because there is no losing trade to compute it from; the loss "
             "sits in what we still hold; and one open lot was recorded without a stop, a data gap we found "
             "in our own feed. Cash is 46 percent because the build is early and the kernel holds a floor, "
             "not because of a market call.")


def s28_log(prs):
    s = add_slide(prs)
    y = title(s, "The decision log, both directions",
              "What the desk did, and the 18 times it decided not to. A trading deck that shows only fills "
              "is showing half the evidence.")
    rows = [
        ["19 Nov", "US.NVDA", "PB-004 buy 33 at 149.053", "17:26:02Z", "17:31:46Z", "5m 44s",
         "+34.95", "1.99", "+32.96", "+2.70"],
        ["19 Nov", "US.AMD", "PB-004 buy 10 at 485.431", "17:26:06Z", "17:49:48Z", "23m 42s",
         "+21.84", "1.98", "+19.86", "+1.63"],
        ["19 Nov", "US.MU", "PB-004 buy 7 at 700.518", "17:26:11Z", "17:49:53Z", "23m 42s",
         "+15.55", "1.98", "+13.57", "+3.30"],
    ]

    def col(r, c, val):
        return GREEN if c in (6, 8, 9) else INK

    th_ = table(s, M, y, CW, ["Day", "Symbol", "What went out", "Entry", "Exit", "Held", "Gross", "Fees",
                              "Net", "Realized R"],
                rows, [0.95, 1.05, 2.80, 1.20, 1.20, 0.98, 1.02, 0.90, 1.08, 1.10], font=9.5,
                head_font=9.4, tag="s28 trades", max_h=1.60, cell_colors=col,
                aligns=[PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.LEFT] + [PP_ALIGN.RIGHT] * 7)
    ny = y + th_ + 0.08
    txt(s, M, ny, CW, 0.56,
        [P("Exit reason for all three: not recorded. The pack carries timestamps, prices, fees and realized "
           "R, and no exit-reason field, so I cannot say which of the lane's four exits fired. Two holds "
           "ran past the 20-minute deadline: PB-004 exits are limit sells with a 900-second submit window, "
           "so a fill can land after the clock - the playbook states that design.",
           size=9.4, color=BRICK, line=1.09)], tag="s28 trade note")
    ry = ny + 0.70
    lw = 7.20
    box(s, M, ry, lw, 1.92,
        [P("The 18 refusals, grouped by rule", size=12.4, color=DARK, bold=True, font=HEAD, line=1.02,
           after=6)] +
        [P("%d   %s" % (n, rule), size=10.4, color=(GREEN if n >= 3 else AMBER), bold=True, line=1.05,
           after=3)
         for n, rule in [(6, "gate.wait - submit window closed, or a client-policy block stopped it"),
                         (4, "account.paper_only - an id outside the allowlist, blocked in code"),
                         (3, "turnover.daily - 33k-35k traded against that day's 25%-of-NAV cap"),
                         (3, "halt.skip - the 18 Nov kill-switch drill: buys skipped on purpose"),
                         (1, "portfolio.gross - post-trade gross 98.6% against a 95% ceiling"),
                         (1, "portfolio.min_cash - post-trade cash 1.4% against a 5% floor")]],
        fill=T_GRAY, line=LINE, tag="s28 refusals", pad=0.13)
    rx = M + lw + 0.24
    rw2 = CW - lw - 0.24
    card(s, rx, ry, rw2, 0.92, "What the log proves worked",
         [P("Six distinct rules fired on real orders and the halt rows sit inside the drill's timestamps. "
            "The caps are not decoration.", size=9.7, color=INK, line=1.09)],
         accent=GREEN, fill=T_GREEN, head_size=11.2, tag="s28 worked")
    card(s, rx, ry + 1.00, rw2, 0.98, "What it shows failing",
         [P("All six gate.wait rows are AMD and MU on 19 Nov: a client-policy block, then an expired window. "
            "The exit was never armed, so the desk carried risk it wanted to shed.", size=9.7, color=INK,
            line=1.09)],
         accent=BRICK, fill=T_BRICK, head_size=11.2, tag="s28 failed")
    bky = ry + 2.10
    box(s, M, bky, CW, 6.90 - bky,
        [P("How a judge can check any of this", size=11.4, color=DARK, bold=True, font=HEAD, line=1.02,
           after=4),
         P("docs/performance/2026-11-23-metrics.md holds every table on these three slides, generated by "
           "tyche performance report; desk-site/web/data/state.json holds the marks, the open book, the 13 "
           "rejection rows and the chain length; journal/events.jsonl is the source, hash-chained and "
           "verified by tyche journal-verify.", size=9.7, color=INK, line=1.09)],
        fill=T_BLUE, line=BLUE, tag="s28 verify", pad=0.12)
    notes(s, "The fills are three scalps on 19 November, all small, all won, and I have deliberately "
             "included the two that ran past the lane's 20-minute deadline - the playbook explains why a "
             "limit exit can fill late, but the pack records no exit reason, so that cell says not recorded "
             "rather than my guess. The refusal list is the half most entries hide: six waits, four "
             "allowlist blocks, three turnover blocks, three halt skips from the drill, one gross breach "
             "and one cash-floor breach, each with a symbol, a quantity and a rule id. Two of those groups "
             "are uncomfortable. The six waits are AMD and MU exits that never got armed, so the desk held "
             "risk it wanted to shed, and the turnover rows ran against a 25 percent cap that has since "
             "been raised in config. The bottom strip is the verification route: three files in the "
             "repository and a command that re-checks the chain, so none of these numbers have to be taken "
             "on trust.")


def s29_divider_reuse(prs):
    divider(prs, "SECTION 4 OF 4", "Reusability and documentation",
            "15% of the score: can somebody else run this, read it, and trust what they read",
            "What this section claims",
            ["The repository runs without a Moomoo account: create a virtual environment, install with the "
             "dev extra, generate demo data, and the same doctor, plan and journal-verify commands the live "
             "desk uses.",
             "Eleven skills, eighteen ADRs, fifty-seven lesson rows and one open-defect list that is longer "
             "than most roadmaps - because every claim in this deck has a file behind it.",
             "The lessons and the defects are written down at the time they happen, including the ones that "
             "make the build look rough."],
            "Slides 30-33. Evidence: README.md, docs/adr/, docs/lessons/LESSONS.md, "
            "documentation/PRD.md §7, skills/.",
            "The last section is the one a judge can check without watching me click anything. I will show "
             "the tree, the four commands that get it running, and then the parts of the record that most "
             "submissions leave out: what failed, in the reviewers' own words, and what is still open. I "
             "have kept the ugly rows in deliberately. A build with no recorded failures is either very "
             "young or badly documented, and this one is neither. If you want to reuse any piece of it, "
             "the skills and the risk card are the two places worth starting.")


def s30_package(prs):
    s = add_slide(prs)
    y = title(s, "Somebody else can run this",
              "No Moomoo account is needed to see the kernel work: demo prices, the same CLI, the same "
              "journal. The tree below is the repository as submitted.")
    tree = [
        ("documentation/", "PRD with per-capability status, architecture, changelog"),
        ("config/", "universe, risk policy, one frozen yaml per playbook id"),
        ("playbook/", "one thesis file per setup + INDEX.yaml roster, agent-loadable"),
        ("src/tyche/", "config, models, strategies, risk.py, journal.py, broker/, cli.py"),
        ("dashboard/  desk-site/", "local desk (authored) and hosted site (exported + feed)"),
        ("scripts/  tests/", "cloud deploys, fetches, exports; 616 unit and end-to-end tests"),
        ("docs/", "18 ADRs, 57 lesson rows, runbooks, validation, performance, competition"),
        ("journal/  plans/  runs/", "runtime evidence, gitignored by design (L-025, L-056)"),
    ]
    box(s, M, y, 6.95, 2.88,
        [P("tyche/", size=10.6, color=DARK, bold=True, font="Consolas", line=1.06, after=3)] +
        [P("  " + d + "  " + t, size=9.5, color=INK, font="Consolas", line=1.06, after=3)
         for d, t in tree],
        fill=T_GRAY, line=LINE, tag="s30 tree", pad=0.13)
    qs = [
        "python -m venv .venv",
        "source .venv/Scripts/activate     # Windows Git Bash",
        'pip install -e ".[dev]" -c constraints.txt',
        "",
        "python scripts/make_demo_data.py",
        "tyche doctor                      # config, CLI, skills, journal",
        "tyche plan --prices data/demo_prices.csv --as-of 2026-11-16 \\",
        "  --account data/demo_account.json",
        "tyche journal-verify              # the hash chain",
    ]
    box(s, M + 7.19, y, CW - 7.19, 2.88,
        [P("README quick start, verbatim", size=10.6, color=GREEN, bold=True, font=HEAD, line=1.02,
           after=6)] +
        [P(line, size=9.4, color=INK, font="Consolas", line=1.06, after=3) for line in qs],
        fill=T_GREEN, line=GREEN, tag="s30 quickstart", pad=0.13)
    ty = y + 3.04
    tiles = [
        ("616", "tests pass with `pytest -q` on the README headline; the PRD's CI row says 607 and the "
         "22 Nov entry 651", GREEN),
        ("18", "architecture decision records, 0001 to 0018, each with status and consequences", BLUE),
        ("57", "rows in docs/lessons/LESSONS.md: assumption, what broke, what changed", AMBER),
        ("11", "skills across five roles: auditor, coordinator, executor, researcher, shared", BRICK),
        ("3", "role skills the prompts point at instead of repeating, so one fix reaches every card",
         DARK),
    ]
    tw = (CW - 4 * 0.16) / 5
    for i, (big, small, acc) in enumerate(tiles):
        box(s, M + i * (tw + 0.16), ty, tw, 1.36,
            [P(big, size=21, color=acc, bold=True, font=HEAD, line=1.0, after=3),
             P(small, size=9.3, color=INK, line=1.07)], fill=T_GRAY, line=acc, tag=f"s30 tile {i}",
            pad=0.11)
    box(s, M, ty + 1.48, CW, 6.90 - (ty + 1.48),
        [P("Reusing it does not require reusing my prompts", size=11.2, color=DARK, bold=True, font=HEAD,
           line=1.02, after=4),
         P("Each skill ships as a directory with a SKILL.md that states its inputs, its outputs and what it "
           "must not do, and the cloud agents are pinned to a published version of it, so another entrant "
           "can attach the same skill and get the same procedure. `tyche doctor` checks config, the Moomoo "
           "CLI, the skills and the journal in one pass, and it is the first thing the quick start runs.",
           size=9.7, color=INK, line=1.10)],
        fill=T_BLUE, line=BLUE, tag="s30 reuse", pad=0.12)
    notes(s, "This is a repository, not a notebook. The tree on the left is what you get, and the box on "
             "the right is copied straight out of the README: four commands, then the doctor, then a plan "
             "against demo prices, and no Moomoo account is required to see the risk kernel refuse an order "
             "and write it to the chain. The tiles are counts you can reproduce with a file listing - 616 "
             "tests, 18 decision records, 57 lesson rows, 11 skills. I gave three different test counts "
             "because the documents disagree and the suite is growing daily; I would rather show the "
             "disagreement than pick a number. The bottom point is the reusable part: the skills are "
             "published and version-pinned, so someone else can attach the same auditor skill and get the "
             "same procedure, and the doctor command tells them whether their config, CLI, skills and "
             "journal are sound before they trade anything.")


def s31_lessons(prs):
    s = add_slide(prs)
    y = title(s, "What failed, and why",
              "Eight rows from docs/lessons/LESSONS.md, quoted in their own shape: the assumption, what it "
              "cost, what changed. None of these were found by a judge.")
    cards = [
        ("L-010  The guard that blocked the right account", BRICK,
         "Assumed an id starting with SIM identifies a paper account.",
         "The regex rejected the real competition account (numeric id, type 2); the type-only replacement "
         "then blocked the personal drill account.",
         "Now a conjunction: env is paper, id allowlisted from vault, type in {1,2}, market 100."),
        ("L-012  Retrying a submit that timed out", AMBER,
         "Assumed a timed-out submit is safe to resend.",
         "MCP submission is not idempotent, so a retry can double-submit an order.",
         "On an unknown outcome, query today's orders before any further write. Never retry blindly."),
        ("L-025  Believing the sandbox remembers", BRICK,
         "Assumed the cloud workspace survives a run.",
         "The sandbox is ephemeral and journal, plans and reports are gitignored - 60% of the score would "
         "vanish with it.",
         "Every run persists: raw data to Drive, sanitized summaries to git, one command owns the split."),
        ("L-033  A cap quoted in two places", AMBER,
         "Assumed restating the limits inside a prompt made them safer.",
         "The auditor prompt said 40 orders and 150% turnover while config enforced 120 and 300%. Two "
         "authorities, and the stale one read as permission.",
         "Prompts now name the YAML and quote no number; a script fails the write if a recited cap survives."),
        ("L-036  A freeze that guarded one lane", BRICK,
         "Assumed that because every lane stamps a PB id, every lane was frozen.",
         "Only pb-001.yaml existed, so hashing raised FileNotFoundError and the approval path degraded to a "
         "blanket block and a traceback.",
         "A lane table maps each id to the file that freezes it; an id that resolves to no file is a build "
         "failure."),
        ("L-040  Green tests, dead dashboard", AMBER,
         "Assumed the Python suite covered the desk's JavaScript.",
         "One raw newline inside a string broke app.js at parse time: every control on the page was dead "
         "while ruff and 470 Python tests stayed green.",
         "A test runs node --check over the script and its hosted copy, and skips loudly rather than "
         "passing silently."),
        ("L-043  Timing a breach off the write stamp", BLUE,
         "Assumed the journal's timestamp is when the market printed the level.",
         "A 135-second breach reported as 4.5 days naked, plus two phantom coverage gaps. 22 monitor tests "
         "passed over it.",
         "Read market time from the payload and fall back to the stamp only for older rows."),
        ("L-056  Two journals, zero shared events", BRICK,
         "Assumed the nearest journal file was the ledger.",
         "Four freeze rows landed in the laptop's 93-event copy while the desk reads a 41-event Drive "
         "ledger. On the ledger, nothing had ever been frozen.",
         "The recorder refuses a repo path without --drill and stamps each row ledger or drill."),
    ]
    cw = (CW - 3 * 0.17) / 4
    chh = 2.62
    for i, (head, acc, a1, a2, a3) in enumerate(cards):
        cx = M + (i % 4) * (cw + 0.17)
        cyy = y + (i // 4) * (chh + 0.17)
        tint = T_BRICK if acc is BRICK else (T_AMBER if acc is AMBER else T_BLUE)
        box(s, cx, cyy, cw, chh,
            [P(head, size=10.4, color=acc, bold=True, font=HEAD, line=1.03, after=5),
             P(a1, size=9.3, color=DARK, bold=True, line=1.07, after=4),
             P(a2, size=9.3, color=INK, line=1.07, after=4),
             P(a3, size=9.3, color=GREEN, line=1.07)],
            fill=tint, line=acc, tag=f"s31 card {i}", pad=0.11)
    notes(s, "These are not decorations; each one is a bug that would still be live if I had not written it "
             "down. Three of them are about authority: a prompt restating a cap that config had already "
             "raised, two journals that shared no events, a timestamp that was not the market's. Two are "
             "about the blind spot between languages - Python tests that could not see a broken JavaScript "
             "file, and a sandbox that forgot everything between runs. One is a guard that blocked the "
             "wrong accounts in both directions. The format is the same in every row because it is the "
             "format that makes a lesson reusable: name the assumption, name the cost, name the change. "
             "Fifty-seven rows exist; these eight are the ones that changed the architecture.")


def s32_open(prs):
    s = add_slide(prs)
    y = title(s, "What is still open",
              "Eight live rows from documentation/PRD.md §7, with the tag the PRD gives each one. Two of "
              "them are the reason two earlier slides say not recorded.")
    cards = [
        ("Prompt drift has no scheduled check", "SAFETY", BRICK,
         "Nothing re-reads the live agents between re-pins, so a hand-edit in the hosted console can make a "
         "prompt stale again. Fix is to fold the live-agent read into a scheduled check (PRD §7 item 1)."),
        ("Strategy id is a default, not an argument", "SAFETY", BRICK,
         "OrderIntent.strategy_id defaults to PB-001 while strategy-score defaults to PB-004, so a lane that "
         "forgets to set it books trades under the wrong strategy - and the ledger filters on that field "
         "(item 3)."),
        ("Ballast lots cannot be pre-armed", "SAFETY", BRICK,
         "PB-001 computes a stop it never journals, so the exit-envelope path finds nothing to protect and "
         "SPY and EFA were refused drafting today. Matches ADR 0013's rebalance stance, but it was "
         "undocumented until rung 1.5 (item 11)."),
        ("A skipped calendar check leaves no trace", "PROVENANCE", AMBER,
         "The drift clause is in the live card brief and the first unattended run was 23 Nov 13:05Z, but a "
         "prompt is not a kernel: a fire that skips it shows only as a missing event (item 7)."),
        ("PB-003 has an id and no page", "PROVENANCE", AMBER,
         "The options lane is registered and hashed through the tactical file but has no thesis document, so "
         "it stays off behind options_enabled: false. PB-002's page landed on 23 Nov; PB-003's has not "
         "(item 2 residue)."),
        ("Provenance rows sit on the drill chain", "PROVENANCE", AMBER,
         "The 21 Nov freeze rows were written to the laptop's 93-event copy; the Drive ledger the desk reads "
         "was re-frozen on 23 Nov with 41 events. The performance pack is generated from the drill copy and "
         "says so (L-056)."),
        ("dashboard/ is outside the lint set", "HYGIENE", BLUE,
         "CI lints src, scripts and tests; ruff reports 18 findings in the operator-facing server and its UI, "
         "the same class of blind spot that let one JS parse error blank the desk (item 9)."),
        ("The hosted console is unverified", "HYGIENE", BLUE,
         "The site is private and answers 401 to unauthenticated requests, so the operator-configured read "
         "must be done from a signed-in session. Pages also move only on an IDE republish (item 12)."),
    ]
    cw = (CW - 3 * 0.17) / 4
    chh = 2.42
    for i, (head, tag, acc, body) in enumerate(cards):
        cx = M + (i % 4) * (cw + 0.17)
        cyy = y + (i // 4) * (chh + 0.17)
        tint = T_BRICK if acc is BRICK else (T_AMBER if acc is AMBER else T_BLUE)
        box(s, cx, cyy, cw, chh,
            [P(tag, size=8.8, color=acc, bold=True, line=1.0, after=3),
             P(head, size=10.6, color=DARK, bold=True, font=HEAD, line=1.03, after=5),
             P(body, size=9.3, color=INK, line=1.07)],
            fill=tint, line=acc, tag=f"s32 card {i}", pad=0.11)
    ny = y + 2 * (chh + 0.17) + 0.02
    txt(s, M, ny, CW, 6.92 - ny,
        [P("Also owed, from the competition notes: a fixed evaluation-prompt suite so a prompt change can be "
           "claimed as an improvement (tip H6), the same drill re-run on the challenge account, and the "
           "PB-002 cap cut from 45% to 25%. None of it is claimed as done on any slide in this deck.",
           size=9.7, color=BRICK, line=1.09)], tag="s32 owed")
    notes(s, "The PRD keeps a list of what is wrong, ordered by what it can cost rather than by effort, and "
             "this is a copy of eight rows from it. The red ones can lose money: a stale prompt can read as "
             "permission, a default strategy id can mis-attribute a trade, and ballast positions cannot be "
             "pre-armed because the stop is computed and never journaled. The amber ones can lose trust: a "
             "skipped calendar check is invisible, one lane has an id without a document, and the freeze "
             "rows sat on the wrong chain for two days. The blue ones are hygiene that has bitten before. "
             "Two of these rows are why earlier slides say not recorded rather than guessing - I would "
             "rather carry the blank than invent the number. The footer lists the three things I still owe, "
             "so nobody has to discover them.")


def s33_plan(prs):
    s = add_slide(prs)
    y = title(s, "The demo, and what goes in",
              "Deadline 30 Nov 2026, 23:59 SGT. The trading window closes 28 Nov, Thanksgiving shuts the "
              "market on 26 Nov and 27 Nov is a half day, so the useful days are these.")
    steps = [
        ("Mon 23", "Re-pin check: confirm the calendar clause ran unattended at 13:05Z and that the feed "
         "published itself from the desk card", GREEN),
        ("Tue 24", "Re-run the performance pack from the Drive ledger, not the drill copy, and update slides "
         "26-28 in place", GREEN),
        ("Wed 25", "Cut PB-002 from 45% to 25% through the cap route: pull request, both hash lines, a "
         "re-freeze from a console session", BLUE),
        ("26-27", "Market closed, then a half day: no new lanes. Flatten anything that would carry into the "
         "28 Nov close", AMBER),
        ("Fri 28", "Last trading day: normal three-fire day, flat or hedged before the regular close",
         AMBER),
        ("Sat 29", "Freeze the deck against the published feed, record the demo video, and check every "
         "number against its file", BRICK),
        ("Sun 30", "Submit before 23:59 SGT: repository, deck, decision log, results, and a demo of what "
         "worked and what did not", BRICK),
    ]
    sw = (CW - 6 * 0.24) / 7
    for i, (day, body, acc) in enumerate(steps):
        sx = M + i * (sw + 0.24)
        box(s, sx, y, sw, 2.32,
            [P(day, size=12.4, color=acc, bold=True, font=HEAD, line=1.0, after=5),
             P(body, size=9.4, color=INK, line=1.08)], fill=T_GRAY, line=acc, tag=f"s33 step {i}",
            pad=0.11)
        if i < 6:
            arrow_r(s, sx + sw + 0.01, y + 1.02, 0.22, 0.24, color=acc)
    cy = y + 2.50
    cw2 = (CW - 0.22) / 2
    box(s, M, cy, cw2, 6.90 - cy,
        [P("The live demo, in the order I would run it", size=11.6, color=DARK, bold=True, font=HEAD,
           line=1.02, after=6),
         P("1. Open the desk and show the halt banner is clear, then press the kill switch and watch the "
           "buy controls go grey while the sell controls stay live - the 18 Nov drill, in eleven minutes.",
           size=9.6, color=INK, line=1.09, after=4),
         P("2. Show a real proposal from the morning fire, approve it in Telegram, and watch the order land "
           "in the journal with a risk verdict and a hash.", size=9.6, color=INK, line=1.09, after=4),
         P("3. Run tyche rules-freeze and tyche journal-verify on stage, and point at the refusal rows the "
           "chain already carries.", size=9.6, color=INK, line=1.09, after=4),
         P("4. Open the hosted desk from a phone and show the same numbers, published by the run rather "
           "than typed by me.", size=9.6, color=INK, line=1.09)],
        fill=T_GREEN, line=GREEN, tag="s33 demo", pad=0.13)
    box(s, M + cw2 + 0.22, cy, cw2, 6.90 - cy,
        [P("Submission checklist", size=11.6, color=DARK, bold=True, font=HEAD, line=1.02, after=6),
         P("Repository at github.com/aloisohzh/tyche, paper-only, no reset or revival of any kind.",
           size=9.7, color=INK, line=1.08, after=3),
         P("Strategy explanation: playbook/INDEX.yaml plus one thesis file per lane, each with a frozen "
           "rules hash.", size=9.7, color=INK, line=1.08, after=3),
         P("Risk limits: docs/risk-card.md and config/risk.yaml, with the drill records beside them.",
           size=9.7, color=INK, line=1.08, after=3),
         P("Decision log: journal/events.jsonl, verified; the same rows feed the desk and this deck.",
           size=9.7, color=INK, line=1.08, after=3),
         P("Fills and results: docs/performance/2026-11-23-metrics.md, regenerated from the ledger before "
           "submission.", size=9.7, color=INK, line=1.08, after=3),
         P("Demo of what worked, what failed and why: this deck, plus slides 31 and 32 on purpose.",
           size=9.7, color=INK, line=1.08)],
        fill=T_BLUE, line=BLUE, tag="s33 check", pad=0.13)
    notes(s, "Five trading days are left, and the calendar narrows them: Thanksgiving closes the market on "
             "the 26th and the 27th is a half day, so the 28th is the last real session and everything "
             "either ships by then or ships as documentation. The first two cards are verification, not "
             "new work - confirm the calendar clause fired unattended, and regenerate the performance pack "
             "from the ledger the desk actually reads so the numbers on slides 26 to 28 are the live ones. "
             "Then the cap cut on PB-002, which is the planned change I mentioned earlier, done through the "
             "freeze route so the chain records it. The two boxes at the bottom are the demo I would give "
             "and the checklist the handbook asks for, and I would rather show the kill switch and the "
             "refusals than a curve that is four days long.")


def s34_close(prs):
    s = add_slide(prs, dark=True)
    kicker(s, "TYCHE  ·  MOOMOO X QODER AI AGENT PAPER TRADING CHALLENGE")
    txt(s, M + 0.35, 1.30, CW - 0.7, 1.5,
        [P("A desk that keeps its own receipts", size=34, color=WHITE, bold=True, font=HEAD, line=1.02,
           after=8),
         P("github.com/aloisohzh/tyche", size=15, color=AMBER, line=1.05)], tag="s34 head")
    cards = [
        ("The idea", "A person owns the reasons, the code owns the numbers, and every claim is a file. "
         "Three fires a day, four agents, eleven skills, one operator who has to say yes."),
        ("What is proven", "616 tests, two safety drills, a hash-chained journal that carries the refusals, "
         "five lanes with frozen rules hashes, and a hosted desk the run itself publishes to."),
        ("What is not", "Four trading days of marks, an account down 1.25%, no evaluation-prompt suite, and "
         "a breach that has never been handled unattended. The deck says so on the slide, not in the notes."),
        ("Where to start", "README quick start, then docs/risk-card.md, playbook/INDEX.yaml, and "
         "docs/performance/2026-11-23-metrics.md. This deck is generated by "
         "docs/competition/deck/build_deck.py."),
    ]
    cw = (CW - 0.7 - 3 * 0.20) / 4
    for i, (head, body) in enumerate(cards):
        box(s, M + 0.35 + i * (cw + 0.20), 3.24, cw, 2.72,
            [P(head, size=12.6, color=AMBER, bold=True, font=HEAD, line=1.02, after=6),
             P(body, size=10.2, color=WHITE, line=1.11)], fill=DARK_PANEL, line=DARK_EDGE,
            tag=f"s34 card {i}", pad=0.14)
    txt(s, M + 0.35, 6.16, CW - 0.7, 0.9,
        [P("Thank you - questions welcome, including the hard ones.", size=13.5, color=WHITE, bold=True,
           font=HEAD, line=1.05, after=4),
         P("Slides, diagrams and charts in this deck were generated by Qoder from the repository's own "
           "records.", size=10.5, color=OFFWHITE, line=1.08)], tag="s34 thanks")
    notes(s, "To close: tyche is a paper-trading desk where the human writes the reasons and the code owns "
             "the numbers, and everything in between is on a hash-chained journal that records the trades "
             "that never happened as carefully as the ones that did. What I can prove today is the "
             "machinery - tests, two drills, five frozen strategy lanes, a desk that publishes itself. What "
             "I cannot prove yet is the edge: the account is down 1.25 percent over four days and beat SPY "
             "only because half the book was cash. I would rather stand in front of a judge with that "
             "sentence on the slide than with a lucky week. Everything here is in the repository, and the "
             "deck itself is generated by a script that reads the same records, so the numbers cannot drift "
             "from the files. Thank you, and I am happy to take the hard questions.")

BUILDERS = [
    s01_title, s02_one_minute, s03_mapping, s04_one_rule, s05_divider, s06_architecture,
    s07_one_day, s08_team, s09_planes, s10_skills, s11_telegram, s12_modes,
    s13_rungs, s14_dashboard, s15_hosted_feed, s16_evidence, s17_checks,
    s18_divider_strategy, s19_book, s20_allocation, s21_invalidation,
    s22_gates, s23_drills, s24_lifecycle,
    s25_divider_return, s26_baseline, s27_results, s28_log,
    s29_divider_reuse, s30_package, s31_lessons, s32_open, s33_plan, s34_close,
]


def main() -> int:
    prs = Presentation()
    prs.slide_width = Emu(int(SW * 914400))
    prs.slide_height = Emu(int(SH * 914400))
    for builder in BUILDERS:
        builder(prs)
    tightened = tighten(prs)
    # page numbers on every slide but the title
    dark_pages = {1, 5, 18, 25, 29, 34}
    for n, sl in enumerate(prs.slides, start=1):
        if n > 1:
            page_no(sl, n, dark=n in dark_pages)
    # notes audit: every slide speaks, in 4-8 sentences
    thin = []
    for n, sl in enumerate(prs.slides, start=1):
        txt_ = sl.notes_slide.notes_text_frame.text if sl.has_notes_slide else ""
        n_sent = sum(txt_.count(sep) for sep in (". ", ".  ")) + 1 if txt_.strip() else 0
        if not txt_.strip():
            thin.append(f"slide {n}: NO SPEAKER NOTES")
        elif n_sent < 4 or n_sent > 8:
            thin.append(f"slide {n}: {n_sent} sentences ({len(txt_)} chars)")
    if thin:
        print("\nNOTES AUDIT:")
        for t_ in thin:
            print("  " + t_)
    else:
        print("notes audit: every slide has 4-8 sentences")
    prs.save(str(OUT))
    print(f"tighten pass: {tightened} shapes resized to fit their text")
    print(f"wrote {OUT} ({len(prs.slides._sldIdLst)} slides)")
    if FIT:
        print(f"\nFIT WARNINGS ({len(FIT)}):")
        for f in FIT:
            print("  " + f)
    else:
        print("fit audit: no overflow detected")
    # geometry audit: nothing may sit past the printable area, and nothing may overlap
    bad = []
    for n, sl in enumerate(prs.slides, start=1):
        boxes = []
        for sp in sl.shapes:
            if sp.left is None or sp.top is None or sp.width is None or sp.height is None:
                continue
            x0, y0 = sp.left / 914400, sp.top / 914400
            x1, y1 = x0 + sp.width / 914400, y0 + sp.height / 914400
            label = (sp.text_frame.text[:34].replace("\n", " ") if sp.has_text_frame else sp.shape_type)
            if isinstance(label, str) and label.strip().isdigit() and (y1 - y0) < 0.4:
                continue  # the page number lives in the bottom margin on purpose
            if y1 > 7.16 or x1 > 12.90 or x0 < 0.30 or y0 < 0.05:
                bad.append(f"slide {n:<3} out of area  y1={y1:5.2f} x1={x1:5.2f}  {label}")
            if sp.shape_type != MSO_SHAPE_TYPE.TEXT_BOX and (x1 - x0) > 0.6 and (y1 - y0) > 0.6:
                boxes.append((x0, y0, x1, y1, label))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                inside = (a[0] <= b[0] + .01 and a[1] <= b[1] + .01 and a[2] >= b[2] - .01
                          and a[3] >= b[3] - .01)
                inside = inside or (b[0] <= a[0] + .01 and b[1] <= a[1] + .01 and b[2] >= a[2] - .01
                                    and b[3] >= a[3] - .01)
                if inside:
                    continue  # a container panel with shapes laid inside it is intentional
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if ox > 0.06 and oy > 0.06:
                    bad.append(f"slide {n:<3} overlap {ox:4.2f}x{oy:4.2f}in  [{a[4]}] / [{b[4]}]")
    if bad:
        print(f"\nGEOMETRY ({len(bad)}):")
        for b in bad:
            print("  " + b)
    else:
        print("geometry audit: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
