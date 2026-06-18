import json

from pydantic import ValidationError

from app.config import settings
from app.models import ChatResponse


#openai sometimes wraps json answers in ```json fences even when not asked to, strip those off
def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # remove the opening ``` or ```json line
        if lines[0].startswith("```"):
            lines = lines[1:]
        # remove the closing ``` line if its there
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


#parses the llm's raw text as our chat response schema, and if it doesnt parse or doesnt
#match the schema, sends it back to the llm with the error so it can try fixing its own output
def validate_with_retry(raw_str: str, llm_fn, max_retries: int | None = None) -> ChatResponse:
    if max_retries is None:
        max_retries = settings.max_validation_retries

    current = raw_str
    last_error = ""

    for attempt in range(max_retries + 1):
        cleaned = _strip_markdown_fences(current)
        try:
            data = json.loads(cleaned)
            return ChatResponse(**data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            if attempt < max_retries:
                prompt = (
                    f"The previous response failed validation with error:\n{last_error}\n\n"
                    f"Original response:\n{cleaned}\n\n"
                    "Please return a corrected JSON response matching the schema: "
                    '{"answer": str, "sources": list[str], "confidence": float (0..1)}'
                )
                current = llm_fn(prompt, last_error)
            else:
                raise exc

    # Should never reach here
    raise RuntimeError(f"Output validation failed unexpectedly: {last_error}")
