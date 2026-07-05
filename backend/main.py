import io
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.services.pdf_parser import extract_text
from backend.services.llm import generate_assignment
from backend.services.pdf_generator import build_assignment_pdf

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate(
    curriculum: UploadFile = File(...),
    lesson_plan: UploadFile = File(...),
    lecture_notes: UploadFile = File(...),
    user_prompt: str = Form(""),
):
    try:
        curriculum_bytes = await curriculum.read()
        lesson_plan_bytes = await lesson_plan.read()
        lecture_notes_bytes = await lecture_notes.read()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read uploaded files: {exc}")

    try:
        curriculum_text = extract_text(curriculum_bytes)
        lesson_plan_text = extract_text(lesson_plan_bytes)
        lecture_notes_text = extract_text(lecture_notes_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"PDF parsing failed: {exc}")

    try:
        assignment_data = generate_assignment(
            curriculum=curriculum_text,
            lesson_plan=lesson_plan_text,
            lecture_notes=lecture_notes_text,
            user_prompt=user_prompt if user_prompt.strip() else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {exc}")

    try:
        pdf_bytes = build_assignment_pdf(assignment_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="assignment.pdf"'},
    )
