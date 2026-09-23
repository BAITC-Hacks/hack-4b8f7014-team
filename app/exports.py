from hashlib import sha256
from io import BytesIO
from xml.sax.saxutils import escape

from app.adapters import PipelineError


def content_blocks(meeting, minutes):
    yield "title", "Протокол совещания"
    yield "text", f"Запись: {meeting.filename}"
    yield "text", f"Дата совещания: {meeting.options.meeting_date or 'не указана'}"
    yield "text", "Черновик ИИ: проверьте транскрипт, ответственных и сроки перед использованием."
    yield "heading", "Краткое содержание"
    yield "text", minutes.summary
    yield "heading", "Поручения"
    if not minutes.tasks:
        yield "text", "Поручения не найдены."
    for index, task in enumerate(minutes.tasks, 1):
        yield "heading", f"{index}. {task.description}"
        yield "text", f"Ответственный: {task.responsible or 'не указан'}"
        yield "text", f"Срок: {task.deadline or 'не указан'}; исходная формулировка: {task.deadline_text or '—'}"
        yield "text", f"Статус: {task.status.value}; требуется проверка: {'да' if task.needs_review else 'нет'}"
        yield "text", f"Срочность: {task.urgency or '—'}; направление: {task.category or '—'}"
        yield "text", f"Основание: {task.evidence or 'добавлено вручную'}"
    yield "heading", "Транскрипт"
    for segment in minutes.transcript:
        speaker = minutes.speakers.get(segment.speaker_id, segment.speaker_id or "Неизвестный")
        yield "text", f"[{segment.start:.1f}–{segment.end:.1f}] {speaker}: {segment.text}"


def export_docx(meeting, minutes):
    from docx import Document
    from docx.shared import Pt

    document = Document()
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = "Arial", Pt(11)
    for kind, text in content_blocks(meeting, minutes):
        if kind == "title":
            document.add_heading(text, 0)
        elif kind == "heading":
            document.add_heading(text, 1)
        else:
            document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def export_pdf(meeting, minutes, font_path):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    if not font_path.is_file():
        raise PipelineError("Для PDF укажите MINUTES_PDF_FONT: локальный TTF-шрифт с RU/KZ")
    font_name = "Minutes" + sha256(str(font_path.resolve()).encode()).hexdigest()[:12]
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    face = pdfmetrics.getFont(font_name).face
    if any(ord(letter) not in face.charToGlyph for letter in "ӘәҒғҚқҢңӨөҰұҮүҺһІіЯя"):
        raise PipelineError("PDF-шрифт не содержит все необходимые RU/KZ символы")
    styles = {kind: ParagraphStyle(kind, fontName=font_name, fontSize=size,
                                   leading=size * 1.4, spaceAfter=8)
              for kind, size in [("title", 20), ("heading", 13), ("text", 10)]}
    flow = []
    for kind, text in content_blocks(meeting, minutes):
        flow.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[kind]))
        if kind == "title":
            flow.append(Spacer(1, 8))
    buffer = BytesIO()
    SimpleDocTemplate(buffer, rightMargin=42, leftMargin=42,
                      topMargin=42, bottomMargin=42).build(flow)
    return buffer.getvalue()
