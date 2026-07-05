const API = "http://localhost:8000";

// ── Helpers ──────────────────────────────────────────────────────────────────

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

function setError(el, msg) {
  el.textContent = msg;
  show(el);
}

function clearStatus(...els) {
  els.forEach(el => { el.textContent = ""; hide(el); });
}

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `Server error ${res.status}`;
    try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ── State ─────────────────────────────────────────────────────────────────────

let _stagingKey = null;       // from X-Staging-Key after /generate
let _gradeAssignmentId = null; // currently selected assignment for grading
let _lastComments = [];        // grading results from /grade

// ── Section 1: Generate ───────────────────────────────────────────────────────

const assignmentForm  = document.getElementById("assignment-form");
const submitBtn       = document.getElementById("submit-btn");
const genSpinner      = document.getElementById("generate-spinner");
const genError        = document.getElementById("generate-error");
const resultSection   = document.getElementById("result");
const pdfPreview      = document.getElementById("pdf-preview");
const downloadLink    = document.getElementById("download-link");
const answerKeyPanel  = document.getElementById("answer-key-panel");
const answerKeyList   = document.getElementById("answer-key-list");

assignmentForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearStatus(genError);
  hide(resultSection);
  show(genSpinner);
  submitBtn.disabled = true;

  try {
    const res = await fetch(`${API}/generate`, {
      method: "POST",
      body: new FormData(assignmentForm),
    });

    if (!res.ok) {
      let detail = `Server error ${res.status}`;
      try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (_) {}
      throw new Error(detail);
    }

    _stagingKey = res.headers.get("X-Staging-Key");

    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    pdfPreview.src = objectUrl;
    downloadLink.href = objectUrl;

    // Fetch and render the answer key from staging
    hide(answerKeyPanel);
    answerKeyList.innerHTML = "";
    if (_stagingKey) {
      try {
        const ak = await fetchJSON(`${API}/staging/${_stagingKey}/answer-key`);
        ak.questions.forEach((q, i) => {
          const li = document.createElement("li");
          li.innerHTML = `<p class="ak-question">${escapeHtml(q)}</p><p class="ak-answer">${escapeHtml(ak.answers[i])}</p>`;
          answerKeyList.appendChild(li);
        });
        show(answerKeyPanel);
      } catch (_) {
        // Non-fatal — answer key display failure shouldn't block the PDF preview
      }
    }

    // Reset save form state
    clearStatus(
      document.getElementById("save-error"),
      document.getElementById("save-success"),
    );
    document.getElementById("assignment-title").value = "";
    show(document.getElementById("save-form-wrap"));
    document.getElementById("save-btn").disabled = false;

    show(resultSection);
  } catch (err) {
    setError(genError, err.message || "An unexpected error occurred.");
  } finally {
    hide(genSpinner);
    submitBtn.disabled = false;
  }
});

// ── Section 1b: Save ──────────────────────────────────────────────────────────

const saveForm    = document.getElementById("save-form");
const saveBtn     = document.getElementById("save-btn");
const saveSpinner = document.getElementById("save-spinner");
const saveError   = document.getElementById("save-error");
const saveSuccess = document.getElementById("save-success");

saveForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = document.getElementById("assignment-title").value.trim();
  if (!title) return;
  if (!_stagingKey) { setError(saveError, "No assignment to save yet."); return; }

  clearStatus(saveError, saveSuccess);
  show(saveSpinner);
  saveBtn.disabled = true;

  try {
    const data = await fetchJSON(`${API}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ staging_key: _stagingKey, title }),
    });

    _stagingKey = null;
    saveSuccess.textContent = `Saved! Assignment ID: ${data.assignment_id}`;
    show(saveSuccess);
    hide(document.getElementById("save-form-wrap"));

    loadHistory(); // refresh list
  } catch (err) {
    setError(saveError, err.message || "Save failed.");
    saveBtn.disabled = false;
  } finally {
    hide(saveSpinner);
  }
});

// ── Section 2: History ────────────────────────────────────────────────────────

const historySpinner = document.getElementById("history-spinner");
const historyError   = document.getElementById("history-error");
const historyEmpty   = document.getElementById("history-empty");
const historyTable   = document.getElementById("history-table");
const historyBody    = document.getElementById("history-body");

async function loadHistory() {
  clearStatus(historyError);
  show(historySpinner);
  hide(historyTable);
  hide(historyEmpty);

  try {
    const rows = await fetchJSON(`${API}/assignments`);

    historyBody.innerHTML = "";

    if (rows.length === 0) {
      show(historyEmpty);
    } else {
      rows.forEach(row => {
        const tr = document.createElement("tr");
        const date = row.created_at ? row.created_at.slice(0, 16).replace("T", " ") : "—";
        tr.innerHTML = `
          <td>${row.id}</td>
          <td>${escapeHtml(row.title)}</td>
          <td>${escapeHtml(date)}</td>
          <td><button class="grade-pick-btn outline" data-id="${row.id}" data-title="${escapeAttr(row.title)}">Grade</button></td>
        `;
        historyBody.appendChild(tr);
      });
      show(historyTable);
    }
  } catch (err) {
    setError(historyError, err.message || "Could not load history.");
  } finally {
    hide(historySpinner);
  }
}

// Delegate Grade button clicks in the table
historyBody.addEventListener("click", (e) => {
  const btn = e.target.closest(".grade-pick-btn");
  if (!btn) return;
  const id    = parseInt(btn.dataset.id, 10);
  const title = btn.dataset.title;
  openGradeSection(id, title);
});

// ── Section 3: Grade ──────────────────────────────────────────────────────────

const gradeSection       = document.getElementById("grade-section");
const gradeLabel         = document.getElementById("grade-assignment-label");
const gradeForm          = document.getElementById("grade-form");
const gradeBtn           = document.getElementById("grade-btn");
const gradeSpinner       = document.getElementById("grade-spinner");
const gradeError         = document.getElementById("grade-error");
const gradeResults       = document.getElementById("grade-results");
const gradeResultsBody   = document.getElementById("grade-results-body");
const saveGradeBtn       = document.getElementById("save-grade-btn");
const saveGradeSpinner   = document.getElementById("save-grade-spinner");
const saveGradeError     = document.getElementById("save-grade-error");
const saveGradeSuccess   = document.getElementById("save-grade-success");

function openGradeSection(assignmentId, title) {
  _gradeAssignmentId = assignmentId;
  gradeLabel.textContent = `Assignment: ${title} (ID ${assignmentId})`;

  // Reset state
  clearStatus(gradeError, saveGradeError, saveGradeSuccess);
  hide(gradeResults);
  document.getElementById("student-name").value = "";
  document.getElementById("submission-file").value = "";
  document.getElementById("final-grade").value = "";
  gradeResultsBody.innerHTML = "";

  show(gradeSection);
  gradeSection.scrollIntoView({ behavior: "smooth" });
}

gradeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!_gradeAssignmentId) return;

  clearStatus(gradeError);
  hide(gradeResults);
  show(gradeSpinner);
  gradeBtn.disabled = true;

  try {
    const fd = new FormData();
    fd.append("assignment_id", _gradeAssignmentId);
    fd.append("submission", document.getElementById("submission-file").files[0]);

    const comments = await fetchJSON(`${API}/grade`, { method: "POST", body: fd });
    _lastComments = comments;

    gradeResultsBody.innerHTML = "";
    comments.forEach((row, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${i + 1}</td>
        <td>${escapeHtml(row.question)}</td>
        <td>${escapeHtml(row.model_answer)}</td>
        <td>${escapeHtml(row.student_answer)}</td>
        <td>${escapeHtml(row.comment)}</td>
      `;
      gradeResultsBody.appendChild(tr);
    });

    clearStatus(saveGradeError, saveGradeSuccess);
    saveGradeBtn.disabled = false;
    show(gradeResults);
  } catch (err) {
    setError(gradeError, err.message || "Grading failed.");
  } finally {
    hide(gradeSpinner);
    gradeBtn.disabled = false;
  }
});

saveGradeBtn.addEventListener("click", async () => {
  const studentName = document.getElementById("student-name").value.trim();
  const finalGrade  = document.getElementById("final-grade").value.trim();

  if (!studentName) { setError(saveGradeError, "Please enter the student name."); return; }
  if (!finalGrade)  { setError(saveGradeError, "Please enter the final grade."); return; }

  clearStatus(saveGradeError, saveGradeSuccess);
  show(saveGradeSpinner);
  saveGradeBtn.disabled = true;

  try {
    await fetchJSON(`${API}/grade/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assignment_id: _gradeAssignmentId,
        student_name: studentName,
        comments: _lastComments,
        final_grade: finalGrade,
      }),
    });

    saveGradeSuccess.textContent = `Grade saved for ${studentName}.`;
    show(saveGradeSuccess);
  } catch (err) {
    setError(saveGradeError, err.message || "Save failed.");
    saveGradeBtn.disabled = false;
  } finally {
    hide(saveGradeSpinner);
  }
});

// ── Utilities ─────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return String(str ?? "").replace(/"/g, "&quot;");
}

// ── Boot ──────────────────────────────────────────────────────────────────────

loadHistory();
