import time
import io
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional

from app.ai_engine import AIEngine
from app.config_manager import load_settings, load_specialties
from app.file_storage import log_request, check_rate_limit

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class StudentInput(BaseModel):
    specialty: str
    interests: str
    resources: str = ""
    deadline: str = "4-6 месяцев"
    work_type: str = "Смешанный"
    level: str = "бакалавр"
    use_ai: bool = False
    regenerate: bool = False


@router.get("/")
async def student_home(request: Request):
    specialties = load_specialties()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "specialties": specialties,
    })


@router.post("/api/generate")
async def generate_topics(data: StudentInput, request: Request):
    settings = load_settings()
    client_ip = request.client.host if request.client else "unknown"

    limit = settings.get("rate_limit_per_ip_per_hour", 10)
    if not check_rate_limit(client_ip, limit):
        raise HTTPException(
            status_code=429,
            detail=f"Превышен лимит запросов: {limit} в час с одного IP. Попробуйте позже."
        )

    engine = AIEngine()
    start = time.time()
    try:
        topics = await engine.generate_topics(data.dict(), regenerate=data.regenerate)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    duration = time.time() - start
    model_used = settings.get("default_model", "unknown")

    if settings.get("save_all_requests", True):
        log_request(
            ip=client_ip,
            specialty=data.specialty,
            interests=data.interests,
            topics_count=len(topics),
            duration_sec=duration,
            model_used=model_used,
        )

    return {"topics": topics, "model_used": model_used, "duration_sec": round(duration, 2)}


@router.get("/api/download_pdf")
async def download_pdf(request: Request):
    settings = load_settings()
    if not settings.get("enable_pdf_export", True):
        raise HTTPException(status_code=403, detail="Экспорт в PDF отключён администратором")

    import json as json_lib
    topics_raw = request.query_params.get("topics", "[]")
    specialty = request.query_params.get("specialty", "")
    try:
        topics = json_lib.loads(topics_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Неверный формат данных")

    pdf_bytes = _generate_pdf(topics, specialty)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=diploma_ideas.pdf"}
    )


def _generate_pdf(topics: List[dict], specialty: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import io as _io

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"], fontSize=18, spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "Heading", parent=styles["Heading2"], fontSize=13, spaceAfter=6,
        textColor=colors.HexColor("#1e3a5f"),
    )
    normal_style = ParagraphStyle(
        "Normal", parent=styles["Normal"], fontSize=10, spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "Label", parent=styles["Normal"], fontSize=10, spaceAfter=2,
        textColor=colors.HexColor("#6b7280"), fontName="Helvetica-Bold",
    )

    story = [
        Paragraph("DiplomaSpark — Идеи для дипломных работ", title_style),
    ]
    if specialty:
        story.append(Paragraph(f"Специальность: {specialty}", label_style))
    story.append(Spacer(1, 0.4*cm))

    difficulty_map = {"easy": "Лёгкая", "medium": "Средняя", "hard": "Сложная"}

    for i, topic in enumerate(topics, 1):
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(f"Тема {i}: {topic.get('title', '')}", heading_style))

        fields = [
            ("Актуальность", topic.get("relevance", "")),
            ("Научная новизна", topic.get("novelty", "")),
            ("Методы", topic.get("methods", "")),
            ("Ожидаемый результат", topic.get("expected_result", "")),
            ("Необходимые ресурсы", topic.get("required_resources", "")),
            ("Сложность", difficulty_map.get(topic.get("difficulty", ""), topic.get("difficulty", ""))),
            ("Примерный объём", f"{topic.get('pages_approx', '—')} страниц"),
        ]
        for label, value in fields:
            story.append(Paragraph(f"<b>{label}:</b> {value}", normal_style))

        structure = topic.get("structure", [])
        if structure:
            story.append(Paragraph("<b>Структура:</b>", label_style))
            for ch in structure:
                story.append(Paragraph(f"• {ch}", normal_style))

        story.append(Spacer(1, 0.4*cm))

    doc.build(story)
    return buf.getvalue()
