import asyncio
import io
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.db import init_db, save_assignment, list_assignments, get_assignment, save_grading_record
from backend.services.pdf_parser import extract_text
from backend.services.llm import generate_assignment
from backend.services.answer_key import generate_answer_key
from backend.services.pdf_generator import build_assignment_pdf

# In-memory staging: staging_key -> (assignment_data, answer_key_data, curriculum_text, lesson_plan_text, lecture_notes_text)
_staging: dict[str, tuple] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Staging-Key"],
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
        assignment_data = await asyncio.to_thread(
            generate_assignment,
            curriculum=curriculum_text,
            lesson_plan=lesson_plan_text,
            lecture_notes=lecture_notes_text,
            user_prompt=user_prompt if user_prompt.strip() else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {exc}")

    try:
        answer_key_data = await asyncio.to_thread(
            generate_answer_key,
            questions=assignment_data["questions"],
            curriculum=curriculum_text,
            lesson_plan=lesson_plan_text,
            lecture_notes=lecture_notes_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Answer key generation failed: {exc}")

    try:
        pdf_bytes = build_assignment_pdf(assignment_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    staging_key = str(uuid.uuid4())
    _staging[staging_key] = (assignment_data, answer_key_data, curriculum_text, lesson_plan_text, lecture_notes_text)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="assignment.pdf"',
            "X-Staging-Key": staging_key,
        },
    )


@app.get("/staging/{staging_key}/answer-key")
def get_staging_answer_key(staging_key: str):
    if staging_key not in _staging:
        raise HTTPException(status_code=404, detail="staging_key not found or already used")
    assignment_data, answer_key_data, *_ = _staging[staging_key]
    return {
        "questions": assignment_data["questions"],
        "answers": answer_key_data["answers"],
    }


@app.post("/save")
async def save(body: dict):
    staging_key = body.get("staging_key", "")
    title = body.get("title", "").strip()

    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    if staging_key not in _staging:
        raise HTTPException(status_code=404, detail="staging_key not found or already used")

    assignment_data, answer_key_data, *_ = _staging.pop(staging_key)

    try:
        assignment_id = save_assignment(title, assignment_data, answer_key_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database save failed: {exc}")

    return {"assignment_id": assignment_id}


@app.get("/assignments")
def get_assignments():
    return list_assignments()


@app.get("/assignments/{assignment_id}/answer-key")
def get_answer_key(assignment_id: int):
    record = get_assignment(assignment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {
        "assignment_json": record["assignment_json"],
        "answer_key_json": record["answer_key_json"],
    }


@app.post("/grade")
async def grade(
    submission: UploadFile = File(...),
    assignment_id: int = Form(...),
):
    record = get_assignment(assignment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    try:
        submission_bytes = await submission.read()
        student_text = extract_text(submission_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read submission PDF: {exc}")

    from backend.services.grader import grade_submission
    try:
        comments = await grade_submission(
            questions=record["assignment_json"]["questions"],
            answer_key_answers=record["answer_key_json"]["answers"],
            student_text=student_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Grading failed: {exc}")

    return comments


@app.post("/grade/save")
async def save_grade(body: dict):
    assignment_id = body.get("assignment_id")
    student_name = body.get("student_name", "").strip()
    comments = body.get("comments", [])
    final_grade = body.get("final_grade", "").strip()

    if not assignment_id:
        raise HTTPException(status_code=422, detail="assignment_id is required")
    if not student_name:
        raise HTTPException(status_code=422, detail="student_name is required")
    if not final_grade:
        raise HTTPException(status_code=422, detail="final_grade is required")

    try:
        save_grading_record(assignment_id, student_name, comments, final_grade)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database save failed: {exc}")

    return {"ok": True}
