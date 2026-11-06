"""Build a printable PDF from the report's text and referenced original PNGs."""

from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "hw3-writeup.pdf"


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.current = None
        self.parts = []
        self.figure = None
        self.table = None
        self.row = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"h1", "h2", "h3", "p", "figcaption", "th", "td"}:
            self.current = tag
            self.parts = []
        elif tag == "table":
            self.table = []
        elif tag == "tr":
            self.row = []
        elif tag == "figure":
            self.figure = {"src": None, "caption": "", "wide": "wide" in attrs.get("class", "").split()}
        elif tag == "img" and self.figure is not None:
            self.figure["src"] = attrs.get("src")

    def handle_data(self, data):
        if self.current is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.current:
            value = " ".join("".join(self.parts).split())
            if tag == "figcaption" and self.figure is not None:
                self.figure["caption"] = unescape(value)
            elif tag in {"th", "td"} and self.row is not None:
                self.row.append(unescape(value))
            elif value:
                self.blocks.append((tag, unescape(value)))
            self.current = None
            self.parts = []
        if tag == "figure" and self.figure is not None:
            self.blocks.append(("figure", self.figure))
            self.figure = None
        elif tag == "tr" and self.table is not None and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.blocks.append(("table", self.table))
            self.table = None


pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("ArialBold", r"C:\Windows\Fonts\arialbd.ttf"))
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="ReportTitle", fontName="ArialBold", fontSize=20, leading=24, spaceAfter=10))
styles.add(ParagraphStyle(name="Section", fontName="ArialBold", fontSize=13, leading=17, textColor=colors.HexColor("#17496a"), spaceBefore=19, spaceAfter=8, keepWithNext=True))
styles.add(ParagraphStyle(name="Subsection", fontName="ArialBold", fontSize=10.5, leading=14, spaceBefore=12, spaceAfter=6, keepWithNext=True))
styles.add(ParagraphStyle(name="BodyText2", fontName="Arial", fontSize=9.3, leading=13.5, spaceAfter=8))
styles.add(ParagraphStyle(name="Caption2", fontName="Arial", fontSize=7.8, leading=10, textColor=colors.HexColor("#455762"), alignment=TA_CENTER))


def figure_flowable(item, width):
    source = ROOT / item["src"]
    if not source.is_file():
        raise FileNotFoundError(source)
    with PILImage.open(source) as png:
        w, h = png.size
    factor = min(width / w, 160 * mm / h)
    image = Image(str(source), width=w * factor, height=h * factor)
    image.hAlign = "CENTER"
    return [image, Spacer(1, 2 * mm), Paragraph(escape(item["caption"]), styles["Caption2"])]


parser = ReportParser()
parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
story = []
pending = []
content_width = A4[0] - 30 * mm
cell_width = (content_width - 6 * mm) / 2


def flush_figures():
    while pending:
        if pending[0]["wide"]:
            item = pending.pop(0)
            story.append(KeepTogether(figure_flowable(item, content_width * 0.83)))
            story.append(Spacer(1, 5 * mm))
            continue
        left = pending.pop(0)
        right = pending.pop(0) if pending and not pending[0]["wide"] else None
        cells = [figure_flowable(left, cell_width)]
        cells.append(figure_flowable(right, cell_width) if right else [])
        table = Table([cells], colWidths=[cell_width, cell_width], hAlign="CENTER")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
        ]))
        story.append(table)


for kind, value in parser.blocks:
    if kind == "figure":
        pending.append(value)
        continue
    flush_figures()
    if kind == "table":
        rows = [[Paragraph(escape(cell), styles["BodyText2"]) for cell in row] for row in value]
        table = Table(rows, colWidths=[content_width / len(rows[0])] * len(rows[0]), repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f1f5")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7e0e5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        story.append(Spacer(1, 4 * mm))
        continue
    style = {"h1": "ReportTitle", "h2": "Section", "h3": "Subsection", "p": "BodyText2"}.get(kind)
    if style:
        story.append(Paragraph(escape(value), styles[style]))
flush_figures()


def decorate(canvas, document):
    canvas.saveState()
    canvas.setFont("Arial", 8)
    canvas.setFillColor(colors.HexColor("#687780"))
    canvas.drawString(15 * mm, 10 * mm, "CS184 Homework 3 · Arthur Yu and Wenxuan Yuan")
    canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, str(document.page))
    canvas.restoreState()


document = BaseDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                           topMargin=16 * mm, bottomMargin=17 * mm)
frame = Frame(document.leftMargin, document.bottomMargin, document.width, document.height,
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
document.addPageTemplates(PageTemplate(id="report", frames=[frame], onPage=decorate))
document.build(story)
print(f"Created {OUTPUT} with {sum(kind == 'figure' for kind, _ in parser.blocks)} images")
