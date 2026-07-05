# Assignment Creator — Plan

## Overview

A web app that takes three PDF inputs (curriculum, lesson plan, lecture notes/whiteboard) plus an
optional free-text user prompt, calls an LLM (via the NVIDIA/GLM endpoint), and produces a
plain/clean one-page PDF assignment. The assignment lists the three key idea names at the top
(no descriptions) followed by a minimum of 8 open-ended questions. A browser preview is shown
before the user downloads.

**Stack**
- Frontend: vanilla JS + HTML/CSS (single-page, no framework)
- Backend: Python / FastAPI
- PDF parsing: `pdfplumber` (text extraction from uploaded PDFs)
- PDF generation: `reportlab` (produce the final one-page assignment PDF)
- LLM: NVIDIA `z-ai/glm-5.2` via OpenAI-compatible streaming endpoint

---

## Sub-Tasks

---

### Sub-Task 1 — Project Scaffold

**Intent**  
Establish the directory layout, dependency files, and entry points so every subsequent sub-task has
a clear home.

**Expected Outcomes**
- `backend/` directory with `main.py`, `requirements.txt`, and a `services/` package stub
- `frontend/` directory with `index.html`, `style.css`, `app.js`
- `.env.example` listing the one required secret (`NVIDIA_API_KEY`)
- The FastAPI app boots with `uvicorn backend.main:app` and returns `200` on `GET /health`

**Todo List**
1. Create `backend/main.py` with a FastAPI app and `/health` route
2. Create `backend/services/__init__.py` (empty stub)
3. Create `backend/requirements.txt` with: `fastapi`, `uvicorn`, `pdfplumber`, `reportlab`,
   `openai`, `python-multipart`, `python-dotenv`
4. Create `frontend/index.html` with a placeholder `<h1>`
5. Create `frontend/style.css` and `frontend/app.js` as empty stubs
6. Create `.env.example` with `NVIDIA_API_KEY=`

**Relevant Context**
- No existing files — greenfield project
- API key from documentation: used as `OPENAI_API_KEY`-equivalent, loaded from `.env`

**Status:** `[ ] pending`

---

### Sub-Task 2 — PDF Parsing Service

**Intent**  
Extract readable text from each of the three uploaded PDF files so the LLM pipeline has clean
string inputs to work with.

**Expected Outcomes**
- `backend/services/pdf_parser.py` with a single function `extract_text(file_bytes: bytes) -> str`
- Text is stripped of excessive whitespace; empty pages are skipped
- Unit-testable in isolation (no FastAPI dependency)

**Todo List**
1. Create `backend/services/pdf_parser.py`
2. Implement `extract_text` using `pdfplumber` — open from `io.BytesIO`, concatenate page text
3. Strip/normalize whitespace and truncate to a safe token ceiling (≈ 6 000 chars per document)
   so the combined prompt stays within the model's context window

**Relevant Context**
- `pdfplumber` works on file-like objects, so `io.BytesIO(file_bytes)` is the right entry point
- Truncation ceiling is a simple safeguard; exact value can be tuned later

**Status:** `[ ] pending`

---

### Sub-Task 3 — LLM Orchestration Service

**Intent**  
Take the three extracted texts plus the user's custom prompt and call the NVIDIA GLM endpoint in a
single structured request that returns three key ideas and a set of open-ended questions.

**Expected Outcomes**
- `backend/services/llm.py` with a function
  `generate_assignment(curriculum: str, lesson_plan: str, lecture_notes: str, user_prompt: str | None) -> dict`
- The returned dict has shape `{ "key_ideas": [str, str, str], "questions": [str, ...] }`
- The function uses the streaming API and assembles the full response before returning
- The system prompt enforces: exactly 3 key ideas (names only, no descriptions), open-ended
  questions only, minimum 8 questions, no multiple-choice or fill-in-the-blank
- `user_prompt` is optional — when present it is appended as additional freeform instruction to
  the LLM (e.g. "focus on critical thinking", "make questions harder"); when absent the LLM uses
  only the three documents

**Todo List**
1. Create `backend/services/llm.py`
2. Build the system prompt that instructs the model on output format (JSON block with `key_ideas`
   and `questions` arrays), enforcing: 3 short key idea names, minimum 8 open-ended questions
3. Build the user message by composing the three extracted texts; if `user_prompt` is non-empty,
   append it under a clearly labelled section ("Additional instructions from user:")
4. Call the NVIDIA endpoint using the `openai` client (streaming), collect chunks, parse final JSON
5. Validate the parsed dict has the required keys and that `questions` has at least 8 items;
   raise a clear error if malformed
6. Load `NVIDIA_API_KEY` from environment via `python-dotenv`

**Relevant Context**
- Endpoint: `https://integrate.api.nvidia.com/v1`, model: `z-ai/glm-5.2`
- Client pattern is from the provided documentation — stream chunks, concatenate `delta.content`
- Ask the model to respond with a JSON code block so it is easy to extract with a regex/split

**Status:** `[ ] pending`

---

### Sub-Task 4 — PDF Generation Service

**Intent**  
Take the structured LLM output and render a clean, one-page PDF assignment: three key ideas at the
top, followed by numbered open-ended questions.

**Expected Outcomes**
- `backend/services/pdf_generator.py` with `build_assignment_pdf(data: dict) -> bytes`
- PDF contains only: a "Key Ideas" label + three idea names (no descriptions), then numbered
  open-ended questions — no title block, no course name, no other decoration
- Plain/clean styling: standard serif or sans-serif font, no borders, no colour accents
- Output is always constrained to one page; content auto-shrinks via `KeepInFrame` to fit
- The returned bytes can be sent directly as a FastAPI `StreamingResponse`

**Todo List**
1. Create `backend/services/pdf_generator.py`
2. Use `reportlab` `SimpleDocTemplate` with letter-size page and standard margins
3. Render a "Key Ideas:" label followed by the three idea names as a simple bulleted or
   dash-prefixed list
4. Add a small spacer, then render numbered open-ended questions (1. … 2. … etc.)
5. Use `reportlab`'s `KeepInFrame` to guarantee single-page output regardless of content length

**Relevant Context**
- `reportlab.platypus.SimpleDocTemplate` + `Paragraph` + `Spacer` is the standard pattern
- `KeepInFrame` from `reportlab.platypus.flowables` can shrink content to fit one page

**Status:** `[ ] pending`

---

### Sub-Task 5 — FastAPI `/generate` Endpoint

**Intent**  
Wire the three services (PDF parsing → LLM → PDF generation) behind a single `POST /generate`
endpoint that accepts the three PDF uploads, the user prompt text, and an optional course name.

**Expected Outcomes**
- `POST /generate` accepts `multipart/form-data` with fields:
  `curriculum` (file), `lesson_plan` (file), `lecture_notes` (file),
  `user_prompt` (str, optional — empty string is treated as absent)
- Returns the generated PDF as `application/pdf` with
  `Content-Disposition: attachment; filename="assignment.pdf"`
- Returns a structured JSON error (`422` or `500`) if any stage fails

**Todo List**
1. Add the `/generate` route to `backend/main.py`
2. Read uploaded file bytes with `await file.read()`
3. Call `extract_text` on each file
4. Call `generate_assignment` with the three texts + user prompt (pass `None` if blank)
5. Call `build_assignment_pdf` with the LLM result (no course name argument)
6. Return a `StreamingResponse` of the PDF bytes with correct headers
7. Add CORS middleware so the frontend (served separately on a different port) can call the API

**Relevant Context**
- `python-multipart` must be installed for FastAPI file uploads (already in `requirements.txt`)
- `fastapi.middleware.cors.CORSMiddleware` with `allow_origins=["*"]` is sufficient for local dev

**Status:** `[ ] pending`

---

### Sub-Task 6 — Frontend UI

**Intent**  
Build a clean single-page UI where the user uploads the three PDFs, types a custom prompt, submits
the form, sees a PDF preview, and downloads the result.

**Expected Outcomes**
- `frontend/index.html` has: three labelled file inputs (curriculum, lesson plan, lecture notes),
  an optional textarea for the custom prompt (placeholder: "Optional: any extra instructions…"),
  and a "Generate" button — no course-name field
- On submit, `app.js` calls `POST /generate` via `fetch` with a `FormData` body
- While waiting, a loading spinner/indicator is shown and the button is disabled
- On success, the PDF blob is rendered in an `<iframe>` preview and a download link appears
- On error, a visible inline error message is shown

**Todo List**
1. Build the full `frontend/index.html` layout with semantic HTML
2. Style with `frontend/style.css` — clean, minimal, readable; no external CSS frameworks
3. In `frontend/app.js`:
   a. Intercept form submit, build `FormData`
   b. `fetch('http://localhost:8000/generate', { method: 'POST', body: formData })`
   c. Convert response to `Blob`, create an object URL
   d. Set the `<iframe>` `src` to the object URL
   e. Set the download `<a>` `href` to the same object URL
4. Handle loading state and errors

**Relevant Context**
- No framework — plain `fetch`, `FormData`, `URL.createObjectURL`
- The `<iframe>` preview works natively in Chrome/Firefox for PDF blobs

**Status:** `[ ] pending`

---

## Data Flow Summary

```
User Browser
  │
  │  POST /generate  (multipart: 3 PDFs + optional prompt)
  ▼
FastAPI /generate
  ├── pdf_parser.extract_text(curriculum_bytes)    → curriculum_text
  ├── pdf_parser.extract_text(lesson_plan_bytes)   → lesson_plan_text
  ├── pdf_parser.extract_text(lecture_notes_bytes) → lecture_notes_text
  │
  ├── llm.generate_assignment(...)
  │     └── NVIDIA GLM endpoint  →  { key_ideas: [...], questions: [...] }
  │
  └── pdf_generator.build_assignment_pdf(data)  →  PDF bytes
  │
  │  Response: application/pdf
  ▼
Browser — <iframe> preview + download link
```

---

## Non-Goals (out of scope for this plan)

- User authentication or session management
- Storing assignments or uploaded files server-side
- Multiple-page assignments
- Question types other than open-ended
- Deployment / containerisation
