import json
import os
import re

from openai import OpenAI

_NVIDIA_API_KEY = os.environ.get("API_KEY", "")
_BASE_URL = "https://integrate.api.nvidia.com/v1"
_MODEL = "z-ai/glm-5.2"

_SYSTEM_PROMPT = """You are an educational answer key writer.

Given a list of open-ended questions and supporting course material, produce a model answer
for every question. Respond in **strict JSON** — no prose outside the JSON block.

Output exactly one JSON code block with this shape:
```json
{
  "answers": ["<model answer 1>", "<model answer 2>", "..."]
}
```

Rules:
- One entry per question, in the same order as the questions.
- Each answer must be 2–4 concise sentences.
- Do not include any text outside the JSON code block."""


def generate_answer_key(
    questions: list[str],
    curriculum: str,
    lesson_plan: str,
    lecture_notes: str,
) -> dict:
    """Return { "answers": [...] } — one model answer per question."""
    client = OpenAI(api_key=_NVIDIA_API_KEY, base_url=_BASE_URL)

    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    user_message = (
        f"## Questions\n{numbered}\n\n"
        f"## Curriculum\n{curriculum}\n\n"
        f"## Lesson Plan\n{lesson_plan}\n\n"
        f"## Lecture Notes\n{lecture_notes}"
    )

    stream = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        stream=True,
    )

    raw = ""
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            raw += delta.content

    return _parse_response(raw, expected_count=len(questions))


def _parse_response(raw: str, expected_count: int) -> dict:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON object found in answer key response:\n{raw}")
        json_str = raw[start:end]

    data = json.loads(json_str)

    if "answers" not in data:
        raise ValueError(f"Missing 'answers' key in answer key response: {data}")
    if len(data["answers"]) != expected_count:
        raise ValueError(
            f"Expected {expected_count} answers, got {len(data['answers'])}"
        )

    return data
