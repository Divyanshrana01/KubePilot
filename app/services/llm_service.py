from openai import OpenAI

from app.config import settings


#shared openai client used for all llm calls in this file
openai_client = OpenAI(api_key=settings.openai_api_key)


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