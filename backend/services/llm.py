import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_NVIDIA_API_KEY = os.environ.get("API_KEY", "")
_BASE_URL = "https://integrate.api.nvidia.com/v1"
_MODEL = "z-ai/glm-5.2"

_SYSTEM_PROMPT = """You are an educational assignment designer.

Given content from three course documents (curriculum, lesson plan, and lecture notes),
produce a structured assignment in **strict JSON** — no prose outside the JSON block.

Output exactly one JSON code block with this shape:
```json
{
  "key_ideas": ["<name 1>", "<name 2>", "<name 3>"],
  "questions": ["<question 1>", "..."]
}
```

Rules:
- `key_ideas`: exactly 3 entries — short concept names only, NO descriptions. If more than 3, keep the first 3 entries.
- `questions`: minimum 8 open-ended questions (why/how/explain/discuss/analyse).
  No multiple-choice, no fill-in-the-blank, no yes/no questions.
- Do not include any text outside the JSON code block."""


def generate_assignment(
    curriculum: str,
    lesson_plan: str,
    lecture_notes: str,
    user_prompt: str | None,
) -> dict:
    """Call the NVIDIA GLM endpoint and return a dict with key_ideas and questions."""
    client = OpenAI(api_key=_NVIDIA_API_KEY, base_url=_BASE_URL)

    user_message = (
        f"## Curriculum\n{curriculum}\n\n"
        f"## Lesson Plan\n{lesson_plan}\n\n"
        f"## Lecture Notes\n{lecture_notes}"
    )
    if user_prompt:
        user_message += f"\n\n## Additional instructions from user:\n{user_prompt}"

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

    return _parse_response(raw)


def _parse_response(raw: str) -> dict:
    """Extract and validate the JSON block from the model's raw response."""
    # Try to find a ```json ... ``` block first, then fall back to bare JSON
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # Fallback: find the first { ... } span
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON object found in model response:\n{raw}")
        json_str = raw[start:end]

    data = json.loads(json_str)

    if "key_ideas" not in data or "questions" not in data:
        raise ValueError(f"Missing required keys in model response: {data}")
    if len(data["key_ideas"]) != 3:
        raise ValueError(
            f"Expected exactly 3 key_ideas, got {len(data['key_ideas'])}"
        )
    if len(data["questions"]) < 8:
        raise ValueError(
            f"Expected at least 8 questions, got {len(data['questions'])}"
        )

    return data
