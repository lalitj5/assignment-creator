import asyncio
import os
import re

from openai import OpenAI

_NVIDIA_API_KEY = os.environ.get("API_KEY", "")
_BASE_URL = "https://integrate.api.nvidia.com/v1"
_MODEL = "z-ai/glm-5.2"

_SYSTEM_PROMPT = (
    "You are a grading assistant. "
    "Given a question, a model answer, and a student's answer, write a short comment "
    "(max 3 sentences) on what the student did well and what is missing. Be concise."
)


def _grade_one(question: str, model_answer: str, student_answer: str) -> dict:
    """Single blocking GLM call for one question. Wrapped in asyncio.to_thread by caller."""
    client = OpenAI(api_key=_NVIDIA_API_KEY, base_url=_BASE_URL)

    user_message = (
        f"Question: {question}\n\n"
        f"Model Answer: {model_answer}\n\n"
        f"Student Answer: {student_answer}"
    )

    stream = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        stream=True,
    )

    comment = ""
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            comment += delta.content

    return {
        "question": question,
        "model_answer": model_answer,
        "student_answer": student_answer,
        "comment": comment.strip(),
    }


def _split_student_answers(student_text: str, n: int) -> list[str]:
    """Best-effort split of student text into per-question answers.

    Looks for numbered headings like "1.", "1)", "Question 1" etc.
    Falls back to returning the full text for every question if no markers found.
    """
    parts = re.split(r"(?m)^\s*(?:question\s*)?\d+[\.\)]\s*", student_text, flags=re.IGNORECASE)
    # re.split with a leading anchor produces an empty first element
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) >= n:
        return parts[:n]

    # Fallback: same full text for every question
    return [student_text] * n


async def grade_submission(
    questions: list[str],
    answer_key_answers: list[str],
    student_text: str,
) -> list[dict]:
    """Fire one GLM call per question concurrently and return the comment list."""
    student_answers = _split_student_answers(student_text, len(questions))

    tasks = [
        asyncio.to_thread(_grade_one, q, a, s)
        for q, a, s in zip(questions, answer_key_answers, student_answers)
    ]
    return list(await asyncio.gather(*tasks))
