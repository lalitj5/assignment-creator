# Features Plan — Answer Key, Auto-Grader, Grading UI, Assignment History

## Overview

Four new features are added on top of the existing assignment-creator app, ordered from
easiest to hardest:

1. **Database setup** — SQLite (stdlib `sqlite3`) with two tables to persist assignments and grading records.
2. **Answer key maker** — parallel LLM call during `/generate`; one model answer per question; stored in DB.
3. **Auto-grader** — student submits a PDF; one fast GLM call per question returns a short comment; teacher reviews and assigns final grade; saved to DB.
4. **Frontend additions** — assignment history panel + teacher grading section in the existing `index.html`.

**Key decisions locked in:**
- Same GLM model (`z-ai/glm-5.2`) for the answer key, called in parallel with assignment generation via `asyncio.gather`.
- Student submits a PDF; grading uses `pdf_parser.extract_text` (already exists) then one LLM call per question in `asyncio.gather`.
- DB: SQLite via `sqlite3` stdlib — no new dependency.
- `/generate` keeps returning only the PDF. A **separate `POST /save`** endpoint persists the assignment JSON + answer key and returns an `assignment_id`. The frontend calls `/save` immediately after a successful `/generate`.
- Final grade + LLM comments are saved to DB via `POST /grade/save`.
- All new UI lives in the existing `index.html` (new collapsible/hidden sections).

**Stack additions:** none (all new deps already available or avoided by design).

---

## Data Flow (new paths only)

```
POST /generate  →  PDF blob  (unchanged)
POST /save      →  { assignment_id }   saves assignment_json + answer_key_json to DB

POST /grade     →  { comments: [{question, answer_key_answer, comment}, ...] }
POST /grade/save →  { ok: true }       saves grading record to DB

GET /assignments →  [{ id, title, created_at }, ...]
GET /assignments/{id}/answer-key → { assignment_json, answer_key_json }
```

---

## Sub-Tasks

---

### Sub-Task 1 — Database Setup

**Intent**
Create the SQLite database layer that all other sub-tasks depend on. Keep it in a single
`backend/db.py` module so it is easy to import from any route.

**Expected Outcomes**
- `backend/db.py` with:
  - `init_db()` — creates the DB file and both tables if they don't exist; called once at app startup.
  - `save_assignment(title, assignment_json, answer_key_json) -> int` — inserts a row and returns the new `id`.
  - `list_assignments() -> list[dict]` — returns `[{id, title, created_at}]` newest-first.
  - `get_assignment(id) -> dict | None` — returns full row including JSON fields.
  - `save_grading_record(assignment_id, student_name, comments_json, final_grade) -> int`
- Two tables:
  - `assignments(id INTEGER PK, title TEXT, created_at TEXT, assignment_json TEXT, answer_key_json TEXT)`
  - `grading_records(id INTEGER PK, assignment_id INTEGER FK, student_name TEXT, created_at TEXT, comments_json TEXT, final_grade TEXT)`
- `backend/main.py` calls `init_db()` at startup via FastAPI's `lifespan` event.
- `sqlite3` only — no new dependency; DB file path defaults to `./assignments.db` (configurable via env `DB_PATH`).

**Todo List**
1. Create `backend/db.py` with the schema DDL and all five helper functions.
2. Use `json.dumps` / `json.loads` to serialise the JSON fields.
3. Import and call `init_db()` in `backend/main.py` using a `lifespan` context manager.
4. Add `DB_PATH=./assignments.db` to `.env.example`.

**Relevant Context**
- `backend/main.py` — add lifespan; existing CORS/health routes stay untouched.
- `.env.example` currently contains only `API_KEY=`.
- No other file needs to change in this sub-task.

**Status:** `[x] done`

---

### Sub-Task 2 — Answer Key Service + `/save` Endpoint

**Intent**
Generate a model answer for every assignment question in a parallel LLM call, then expose
a `/save` endpoint the frontend calls to persist the assignment and its answer key.

**Expected Outcomes**
- `backend/services/answer_key.py` with `generate_answer_key(questions, curriculum, lesson_plan, lecture_notes) -> dict`
  - Returns `{ "answers": ["<model answer 1>", ...] }` — one entry per question, same order.
  - Uses same GLM model and `openai` client pattern as `llm.py`.
  - System prompt instructs: concise model answers only (2–4 sentences each), plain JSON output.
- `POST /generate` in `backend/main.py` is updated to call `generate_assignment` AND `generate_answer_key` via `asyncio.gather` so they run in parallel. The endpoint still returns only the PDF blob; the raw assignment + answer key dicts are stored in a module-level in-memory staging dict keyed by a short UUID, returned as header `X-Staging-Key`.
- New `POST /save` endpoint accepts JSON body `{ staging_key, title }`, looks up the staging dict, calls `db.save_assignment(...)`, removes the staging entry, returns `{ assignment_id }`.

**Todo List**
1. Create `backend/services/answer_key.py` with `generate_answer_key`.
2. In `backend/main.py`:
   a. Make the `generate` handler `async` (it already is) and run both LLM calls with `asyncio.gather`.
   b. After gathering, store `(assignment_data, answer_key_data)` in a module-level `_staging: dict[str, tuple]` with a UUID key.
   c. Add the staging key as response header `X-Staging-Key` on the `StreamingResponse`.
3. Add `POST /save` route: reads `staging_key` + `title` from JSON body, calls `db.save_assignment`, clears the staging entry, returns `{ "assignment_id": id }`.
4. Staging entries older than the request lifetime are harmless (small dict); no TTL needed.

**Relevant Context**
- `backend/services/llm.py` — `generate_assignment` is the pattern to follow for the answer key call; reuse `_NVIDIA_API_KEY`, `_BASE_URL`, `_MODEL`.
- `backend/main.py` — `POST /generate` handler; `StreamingResponse` is returned from `io.BytesIO(pdf_bytes)`.
- `backend/db.py` — `save_assignment` from Sub-Task 1.

**Status:** `[x] done`

---

### Sub-Task 3 — Auto-Grader Service + `/grade` and `/grade/save` Endpoints

**Intent**
Accept a student's PDF submission and an `assignment_id`, extract the student's answers,
and produce a short LLM comment per question. The teacher then reviews and submits a final
grade which is persisted.

**Expected Outcomes**
- `backend/services/grader.py` with `grade_submission(questions, answer_key_answers, student_text) -> list[dict]`
  - Splits student text into per-question answers by looking for numbered headings (best-effort; falls back to sending the full text for each question).
  - Fires one GLM call per question via `asyncio.gather` (using `asyncio.to_thread` since the `openai` client is sync).
  - Each call returns a short comment (≤ 3 sentences) comparing the student answer against the model answer.
  - Returns `[{ "question": str, "model_answer": str, "student_answer": str, "comment": str }, ...]`.
- `POST /grade` — accepts `multipart/form-data`: `submission` (PDF file) + `assignment_id` (int form field).
  - Loads the assignment from DB, extracts student text, calls `grade_submission`, returns the list as JSON.
- `POST /grade/save` — accepts JSON body `{ assignment_id, student_name, comments, final_grade }`.
  - Calls `db.save_grading_record(...)`, returns `{ "ok": true }`.

**Todo List**
1. Create `backend/services/grader.py` with `grade_submission`.
2. For the per-question LLM call: system prompt = "You are a grading assistant. Given a question, a model answer, and a student's answer, write a short comment (max 3 sentences) on what the student did well and what is missing. Be concise."
3. Add `POST /grade` route to `backend/main.py`.
4. Add `POST /grade/save` route to `backend/main.py`.
5. Import `db.get_assignment` and `db.save_grading_record` in `main.py`.

**Relevant Context**
- `backend/services/pdf_parser.py` — `extract_text(file_bytes)` reused for the student PDF.
- `backend/services/llm.py` — same client/model pattern; the grader just uses a different system prompt.
- `backend/db.py` — `get_assignment` and `save_grading_record` from Sub-Task 1.
- `asyncio.to_thread` wraps the blocking `openai` streaming call so multiple questions run concurrently.

**Status:** `[x] done`

---

### Sub-Task 4 — Assignment History API Endpoints

**Intent**
Expose two read endpoints so the frontend can list past assignments and fetch an answer key
for grading.

**Expected Outcomes**
- `GET /assignments` returns `[{ id, title, created_at }]` (newest first).
- `GET /assignments/{id}/answer-key` returns the full `{ assignment_json, answer_key_json }` for the given record, or `404` if not found.

**Todo List**
1. Add `GET /assignments` route to `backend/main.py` — calls `db.list_assignments()`, returns list directly.
2. Add `GET /assignments/{id}/answer-key` route — calls `db.get_assignment(id)`, parses JSON fields, returns them, raises `HTTPException(404)` if `None`.

**Relevant Context**
- `backend/db.py` — `list_assignments` and `get_assignment` from Sub-Task 1.
- These are pure read routes; no new service files needed.

**Status:** `[x] done`

---

### Sub-Task 5 — Frontend: Assignment History + Save Flow

**Intent**
After a successful `/generate`, prompt the teacher to name and save the assignment. Show a
collapsible history panel that lists past assignments.

**Expected Outcomes**
- After the PDF preview appears, a small "Save assignment" form (title input + Save button) is shown.
- On save: `POST /save` is called with `{ staging_key, title }`; on success, the `assignment_id` is stored in a JS variable and the save form is replaced with a success message.
- A "Past Assignments" collapsible section at the bottom of the page fetches `GET /assignments` on page load and renders a table: ID, title, date, and a "Grade" button.
- Clicking "Grade" for a past assignment populates the grading section (Sub-Task 6) with that assignment's data (fetched from `/assignments/{id}/answer-key`).
- CSS for the new elements follows the existing minimal style in `frontend/style.css`.

**Todo List**
1. Add "Save assignment" form markup to `frontend/index.html` inside `#result`, initially hidden.
2. Add "Past Assignments" section markup to `frontend/index.html`.
3. In `frontend/app.js`:
   a. After a successful `/generate` response, read the `X-Staging-Key` response header, reveal the save form.
   b. Save form submit → `POST /save` → store `assignment_id`, show confirmation, hide save form.
   c. On page load, `fetch GET /assignments` and render the history table.
   d. "Grade" button click: fetch `/assignments/{id}/answer-key`, store data, scroll to/reveal grading section.
4. Add styles for the history table and save form to `frontend/style.css`.

**Relevant Context**
- `frontend/app.js` — existing `fetch` pattern, `FormData`, blob handling.
- `frontend/index.html` — existing `#result` section; new markup appended after it.
- `frontend/style.css` — existing `.hidden`, `.field`, button styles to reuse/extend.

**Status:** `[x] done`

---

### Sub-Task 6 — Frontend: Teacher Grading UI

**Intent**
Give the teacher a section to upload a student PDF, trigger auto-grading, review per-question
LLM comments, enter a final grade, and save everything.

**Expected Outcomes**
- A "Grade a Submission" section in `index.html` (hidden until an assignment is selected from history or directly activated).
- Inputs: student PDF upload, student name text field, "Auto-Grade" button.
- After auto-grading: a table/list showing each question, the model answer, the student's extracted answer, and the LLM comment — all read-only.
- A "Final Grade" text input and a "Save Grade" button below the table.
- On "Save Grade": `POST /grade/save` is called; on success a confirmation message is shown.
- Loading and error states follow the same pattern as the existing generate flow.

**Todo List**
1. Add "Grade a Submission" section markup to `frontend/index.html`.
2. In `frontend/app.js`:
   a. "Auto-Grade" button click: build `FormData` with `submission` PDF + `assignment_id`, call `POST /grade`, render returned comments list.
   b. "Save Grade" button click: call `POST /grade/save` with `{ assignment_id, student_name, comments, final_grade }`.
   c. Show/hide loading state and inline errors for both actions.
3. Add styles for the grading table to `frontend/style.css`.

**Relevant Context**
- `frontend/app.js` — existing loading/error state pattern (spinner, error-msg, disabled button) to replicate.
- `POST /grade` and `POST /grade/save` from Sub-Task 3.
- The grading section is pre-populated with `assignment_id` from the history "Grade" button click (Sub-Task 5, step d).

**Status:** `[x] done`

---

## Non-Goals (out of scope for this plan)

- Multiple student submissions per assignment tracked separately in history UI.
- PDF export of the grading report.
- Authentication or multi-teacher support.
- Changing the PDF generation or assignment question format.
