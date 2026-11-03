"""OpenAI-compatible Responses API adapter (Meta Model API or OpenRouter)."""
import os
from openai import OpenAI


def configured() -> bool:
    return bool(os.getenv("MODEL_API_KEY") or os.getenv("LLAMA_API_KEY"))


def model_name() -> str:
    default = "meta-llama/llama-4-maverick" if "openrouter.ai" in os.getenv("MODEL_API_BASE", "") else "muse-spark-1.3"
    return os.getenv("MODEL_NAME", default)


def complete(instructions: str, text: str, image_data: str | None = None, web_search: bool = False) -> dict:
    key = os.getenv("MODEL_API_KEY") or os.getenv("LLAMA_API_KEY")
    if not key:
        raise RuntimeError("Set MODEL_API_KEY to enable the configured model provider")
    client = OpenAI(
        base_url=os.getenv("MODEL_API_BASE", "https://api.meta.ai/v1"),
        api_key=key,
        # A UI turn fans out to several specialists. Bound the first network
        # failure so one unavailable provider cannot stall every role in turn.
        timeout=min(float(os.getenv("MODEL_API_TIMEOUT_SECONDS", "20")), 20.0),
        max_retries=0,
    )
    content = [{"type": "input_text", "text": text}]
    if image_data:
        content.append({"type": "input_image", "image_url": image_data})
    request = {
        "model": model_name(),
        "instructions": instructions,
        "input": [{"type": "message", "role": "user", "content": content}],
        "store": False,
        "max_output_tokens": 1200,
    }
    if "openrouter.ai" not in os.getenv("MODEL_API_BASE", ""):
        request["reasoning"] = {"effort": os.getenv("MODEL_REASONING_EFFORT", "medium")}
    if web_search:
        search_tool = "openrouter:web_search" if "openrouter.ai" in os.getenv("MODEL_API_BASE", "") else "web_search"
        request["tools"] = [{"type": search_tool}]
    response = client.responses.create(**request)
    citations = []
    for item in getattr(response, "output", []) or []:
        for block in getattr(item, "content", []) or []:
            for annotation in getattr(block, "annotations", []) or []:
                url = getattr(annotation, "url", None)
                title = getattr(annotation, "title", None)
                if url:
                    citations.append({"title": title or url, "url": url})
    # Preserve citation order while removing duplicate links.
    unique = list({item["url"]: item for item in citations}.values())
    return {"text": response.output_text, "citations": unique, "model": model_name()}
