"""Structured-JSON LLM calls: JSON mode -> Pydantic validation -> retry with error -> fallback model."""
import asyncio
import json
import logging
from typing import Callable, Sequence, TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

log = logging.getLogger("triage.llm")
T = TypeVar("T", bound=BaseModel)


class LLMFailure(Exception):
    """All models/attempts failed; caller must escalate instead of guessing."""


def extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model output")
    return text[start : end + 1]


async def call_json(
    models: Sequence,
    system: str,
    user: str,
    schema: type[T],
    timeout_s: float,
    extra_check: Callable[[T], None] | None = None,
    attempts_per_model: int = 2,
) -> T:
    if not models:
        raise LLMFailure("no LLM configured (missing GROQ_API_KEY?)")
    sys_prompt = (
        f"{system}\n\nRespond with ONLY a JSON object matching this JSON schema, no prose:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
    errors: list[str] = []
    for m_idx, model in enumerate(models):
        msgs = [SystemMessage(sys_prompt), HumanMessage(user)]
        for attempt in range(attempts_per_model):
            try:
                resp = await asyncio.wait_for(model.ainvoke(msgs), timeout=timeout_s)
            except asyncio.TimeoutError:
                errors.append(f"model{m_idx}: timeout after {timeout_s}s")
                break  # don't retry a slow model; go to fallback
            except Exception as e:  # network / rate limit / auth
                errors.append(f"model{m_idx}: {type(e).__name__}: {e}"[:300])
                break
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            try:
                obj = schema.model_validate_json(extract_json(text))
                if extra_check:
                    extra_check(obj)
                return obj
            except (ValidationError, ValueError) as e:
                err = str(e)[:500]
                errors.append(f"model{m_idx} attempt{attempt}: invalid output: {err[:150]}")
                log.warning("invalid LLM output, retrying: %s", err[:200])
                msgs = msgs + [
                    AIMessage(text),
                    HumanMessage(f"That output was invalid: {err}\nReturn ONLY the corrected JSON object."),
                ]
    raise LLMFailure("; ".join(errors))


def make_groq_models(api_key: str, primary: str, fallback: str, timeout_s: float) -> list:
    if not api_key:
        return []
    from langchain_groq import ChatGroq

    out = []
    for name in dict.fromkeys([primary, fallback]):  # dedupe, keep order
        llm = ChatGroq(model=name, api_key=api_key, temperature=0, max_retries=0, timeout=timeout_s)
        out.append(llm.bind(response_format={"type": "json_object"}))
    return out
