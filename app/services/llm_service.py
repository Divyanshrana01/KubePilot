from openai import OpenAI

from app.config import settings


#shared openai client used for all llm calls in this file.
#timeout caps how long a single call may hang (the SDK default is 600s, which turns one
#stalled request into a multi-minute tail); max_retries keeps transient-error backoff bounded.
openai_client = OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=2)


#this fn sends a system prompt + user message to the llm and returns the answer as text.
#temperature is 0 by default so answers are deterministic (no randomness).
#also returns token usage so callers can track costs.
def generate(system_prompt: str, user_message: str, model: str | None = None, temperature: float = 0.0) -> dict:
    if model is None:
        model = settings.llm_model_answer

    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
    )

    text = response.choices[0].message.content or ""

    #pull out token counts from the response, useful for cost tracking
    usage = {
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
        "total_tokens": response.usage.total_tokens if response.usage else 0,
    }

    return {"text": text, "usage": usage}

#streaming variant of generate(): yields the answer text in deltas as the model produces
#them, instead of waiting for the whole completion. used by the SSE /query/stream endpoint
#so the UI can render tokens live. no usage stats here (the streaming API doesn't return
#them mid-stream unless explicitly requested).
def generate_stream(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    temperature: float = 0.0,
):
    if model is None:
        model = settings.llm_model_answer

    stream = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


#same as generate() but forces the model to return a json object.
#used for grading/evaluation tasks where we need structured output we can parse.
def generate_with_json(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    temperature: float = 0.0,
) -> dict:

    #uses the grader model by default (cheaper/faster than the answer model)
    if model is None:
        model = settings.llm_model_grader

    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},  #tells openai to always return valid json
    )
    text = response.choices[0].message.content or ""
    usage = {
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
        "total_tokens": response.usage.total_tokens if response.usage else 0,
    }
    return {"text": text, "usage": usage}