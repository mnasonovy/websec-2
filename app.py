from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.ssau_parser import (
    get_current_week,
    get_groups,
    get_schedule_by_group,
    get_schedule_by_teacher,
    get_teachers,
)

app = Flask(__name__)
app.json.ensure_ascii = False


def register_pdf_fonts() -> None:
    font_candidates = [
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        ),
    ]

    for regular_path, bold_path in font_candidates:
        if regular_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont("AppFont", str(regular_path)))
            pdfmetrics.registerFont(TTFont("AppFont-Bold", str(bold_path)))
            return

    raise FileNotFoundError("Не удалось найти подходящие шрифты для генерации PDF.")


def build_schedule_pdf(
    schedule_data: dict,
    mode: str,
    entity_name: str,
    week: int,
) -> BytesIO:
    register_pdf_fonts()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontName="AppFont-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1a3fa6"),
        spaceAfter=10,
    )

    meta_style = ParagraphStyle(
        "MetaStyle",
        parent=styles["Normal"],
        fontName="AppFont",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2d3b5f"),
        spaceAfter=4,
    )

    day_style = ParagraphStyle(
        "DayStyle",
        parent=styles["Heading2"],
        fontName="AppFont-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#233b88"),
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontName="AppFont",
        fontSize=9,
        leading=12,
        textColor=colors.black,
    )

    center_note_style = ParagraphStyle(
        "CenterNote",
        parent=styles["Normal"],
        fontName="AppFont",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4b5c84"),
        spaceBefore=10,
    )

    story = [
        Paragraph("Расписание Самарского университета", title_style),
        Paragraph(
            f"{'Группа' if mode == 'group' else 'Преподаватель'}: <b>{entity_name}</b>",
            meta_style,
        ),
        Paragraph(f"Учебная неделя: <b>{week}</b>", meta_style),
        Spacer(1, 6),
    ]

    days = schedule_data.get("days", [])

    if not days:
        message = schedule_data.get("message", "На выбранную неделю занятий нет.")
        story.append(Paragraph(message, center_note_style))
    else:
        for day in days:
            day_name = day.get("day_name", "")
            day_date = day.get("date", "")
            story.append(Paragraph(f"{day_name} - {day_date}", day_style))

            table_data = [["Время", "Тип", "Предмет", "Преподаватель", "Аудитория"]]

            for lesson in day.get("lessons", []):
                table_data.append(
                    [
                        lesson.get("time", ""),
                        lesson.get("type", ""),
                        Paragraph(lesson.get("title", ""), body_style),
                        Paragraph(lesson.get("teacher", ""), body_style),
                        lesson.get("room", ""),
                    ]
                )

            table = Table(
                table_data,
                colWidths=[26 * mm, 24 * mm, 70 * mm, 42 * mm, 20 * mm],
                repeatRows=1,
            )

            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a56c6")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "AppFont-Bold"),
                        ("FONTNAME", (0, 1), (-1, -1), "AppFont"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                        ("LEADING", (0, 0), (-1, -1), 10),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9fb4e8")),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7f9ff")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            story.extend([table, Spacer(1, 10)])

    document.build(story)
    buffer.seek(0)
    return buffer


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/groups")
def api_groups():
    return jsonify(get_groups())


@app.route("/api/teachers")
def api_teachers():
    return jsonify(get_teachers())


@app.route("/api/current-week")
def api_current_week():
    return jsonify({"week": get_current_week()})


@app.route("/api/schedule/group/<group_id>")
def api_schedule_group(group_id: str):
    week = request.args.get("week", type=int)
    return jsonify(get_schedule_by_group(group_id, week))


@app.route("/api/schedule/teacher")
def api_schedule_teacher():
    teacher = request.args.get("name", "")
    week = request.args.get("week", type=int)
    return jsonify(get_schedule_by_teacher(teacher, week))


@app.route("/download/pdf")
def download_pdf():
    mode = request.args.get("mode", "group")
    week = request.args.get("week", type=int) or get_current_week()

    if mode == "teacher":
        teacher_name = request.args.get("name", "").strip()
        schedule_data = get_schedule_by_teacher(teacher_name, week)
        entity_name = teacher_name or "teacher"
        filename = f"schedule_teacher_week_{week}.pdf"
    else:
        group_id = request.args.get("group_id", "").strip()
        schedule_data = get_schedule_by_group(group_id, week)
        entity_name = next(
            (group["name"] for group in get_groups() if group["id"] == group_id),
            group_id,
        )
        filename = f"schedule_{entity_name}_week_{week}.pdf"

    pdf_buffer = build_schedule_pdf(schedule_data, mode, entity_name, week)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    app.run(debug=True)