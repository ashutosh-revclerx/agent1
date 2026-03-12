from __future__ import annotations

import os
import requests
from typing import Optional, Tuple
from datetime import datetime
import google.generativeai as genai

from app.services.langfuse_service import (
    get_langfuse_client,
    is_langfuse_enabled,
)
from app.core.logging import logger

TIMEOUT_S = 120


def ask_llm(
    prompt: str,
    trace_name: str = "LLM Call",
    metadata: dict | None = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Tuple[str, int]]:
    """
    LLM call with optional Langfuse tracing.
    Primary: Google Gemini (configured model)
    Fallback: Gemma3 (via Ollama/LM Studio)
    Returns: (response_text, total_tokens)
    """

    try:
        return _call_gemini(prompt, trace_name, metadata, session_id, user_id)
    except Exception as e:
        logger.warning(f"[LLM] Gemini failed: {e}. Falling back to Gemma3...")
        try:
            return _call_gemma3(prompt, trace_name, metadata, session_id, user_id)
        except Exception as fallback_error:
            logger.error(f"[LLM] Gemma3 fallback also failed: {fallback_error}")
            return None


def _call_gemini(
    prompt: str,
    trace_name: str = "LLM Call",
    metadata: dict | None = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Tuple[str, int]]:
    """Call Google Gemini API (Primary LLM)"""
    from app.core import config

    api_key = config.GEMINI_API_KEY
    model_name = config.GEMINI_MODEL

    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")

    logger.info(
        f"[LLM] Gemini model={model_name} | timeout={TIMEOUT_S}s | "
        f"prompt_chars={len(prompt or '')} words={len((prompt or '').split())}"
    )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    def _call_gemini_api() -> tuple[str, int, int, float]:
        start_time = datetime.utcnow()

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.2),
        )

        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        text = response.text.strip() if response.text else ""

        input_tokens = (
            response.usage_metadata.prompt_token_count
            if response.usage_metadata
            else 0
        )
        output_tokens = (
            response.usage_metadata.candidates_token_count
            if response.usage_metadata
            else 0
        )

        return text, input_tokens, output_tokens, latency_ms

    langfuse = get_langfuse_client()

    if langfuse and is_langfuse_enabled():
        try:
            trace = langfuse.trace(
                name=trace_name,
                session_id=session_id,
                user_id=user_id,
                metadata={
                    **(metadata or {}),
                    "model": model_name,
                    "provider": "google",
                    "timeout_s": TIMEOUT_S,
                },
            )

            generation = trace.generation(
                name="llm-generation",
                model=model_name,
                input=prompt,
            )

            try:
                logger.info(
                    f"[LLM] Calling Gemini..."
                    + (f" (session: {session_id})" if session_id else "")
                )

                text, in_tok, out_tok, latency_ms = _call_gemini_api()
                logger.info(f"[LLM] Gemini response received ({latency_ms:.0f}ms)")

                total_tokens = in_tok + out_tok

                generation.end(
                    output=text,
                    usage={
                        "input": in_tok,
                        "output": out_tok,
                        "total": total_tokens,
                    },
                    metadata={"latency_ms": latency_ms, "error": False},
                )

                trace.update(tags=["gemini"], metadata={"tokens": total_tokens})
                return text, total_tokens

            except Exception as e:
                logger.error(f"[LLM] Gemini Error: {e}", exc_info=True)
                generation.end(output=f"Error: {str(e)}", metadata={"error": True})
                trace.update(tags=["error", "gemini"], metadata={"error": str(e)})
                raise

        except Exception as e:
            logger.warning(f"[Langfuse] Error in tracing: {e}", exc_info=True)

    try:
        logger.info("[LLM] Calling Gemini (no tracing)...")

        text, in_tok, out_tok, latency_ms = _call_gemini_api()
        logger.info(f"[LLM] Gemini response received ({latency_ms:.0f}ms)")

        total_tokens = in_tok + out_tok
        return text, total_tokens

    except Exception as e:
        logger.error(f"[LLM] Gemini Error: {e}", exc_info=True)
        raise


def _call_gemma3(
    prompt: str,
    trace_name: str = "LLM Call",
    metadata: dict | None = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Tuple[str, int]]:
    """Call Gemma3 via Ollama/LM Studio (Fallback LLM)"""
    from app.core import config

    llm_url = config.LLM_URL
    model = config.LLM_MODEL

    if not llm_url:
        raise ValueError("LLM_URL not set in environment")

    logger.info(
        f"[LLM] Gemma3 (FALLBACK) model={model} | url={llm_url} | timeout={TIMEOUT_S}s | "
        f"prompt_chars={len(prompt or '')} words={len((prompt or '').split())}"
    )

    def _call_gemma3_api() -> tuple[str, int, int, float]:
        start_time = datetime.utcnow()

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }

        response = requests.post(
            f"{llm_url}/api/generate",
            json=payload,
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()

        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        result = response.json()
        text = (result.get("response", "") or "").strip()

        input_tokens = int(result.get("prompt_eval_count", 0) or 0)
        output_tokens = int(result.get("eval_count", 0) or 0)

        return text, input_tokens, output_tokens, latency_ms

    langfuse = get_langfuse_client()

    if langfuse and is_langfuse_enabled():
        try:
            trace = langfuse.trace(
                name=trace_name,
                session_id=session_id,
                user_id=user_id,
                metadata={
                    **(metadata or {}),
                    "model": model,
                    "provider": "gemma3_fallback",
                    "timeout_s": TIMEOUT_S,
                },
            )

            generation = trace.generation(
                name="llm-generation",
                model=model,
                input=prompt,
            )

            try:
                logger.info(
                    f"[LLM] Calling Gemma3 (FALLBACK)..."
                    + (f" (session: {session_id})" if session_id else "")
                )

                text, in_tok, out_tok, latency_ms = _call_gemma3_api()
                logger.info(f"[LLM] Gemma3 response received ({latency_ms:.0f}ms)")

                total_tokens = (
                    (in_tok + out_tok)
                    if (in_tok or out_tok)
                    else _estimate_tokens(prompt, text)
                )

                generation.end(
                    output=text,
                    usage={
                        "input": in_tok,
                        "output": out_tok,
                        "total": total_tokens,
                    },
                    metadata={"latency_ms": latency_ms, "error": False},
                )

                trace.update(tags=["gemma3"], metadata={"tokens": total_tokens})
                return text, total_tokens

            except Exception as e:
                logger.error(f"[LLM] Gemma3 Error: {e}", exc_info=True)
                generation.end(output=f"Error: {str(e)}", metadata={"error": True})
                trace.update(tags=["error", "gemma3"], metadata={"error": str(e)})
                raise

        except Exception as e:
            logger.warning(f"[Langfuse] Error in tracing: {e}", exc_info=True)

    try:
        logger.info("[LLM] Calling Gemma3 (FALLBACK, no tracing)...")

        text, in_tok, out_tok, latency_ms = _call_gemma3_api()
        logger.info(f"[LLM] Gemma3 response received ({latency_ms:.0f}ms)")

        total_tokens = (
            (in_tok + out_tok)
            if (in_tok or out_tok)
            else _estimate_tokens(prompt, text)
        )

        return text, total_tokens

    except Exception as e:
        logger.error(f"[LLM] Gemma3 Error: {e}", exc_info=True)
        raise


def _estimate_tokens(prompt: str, response_text: str) -> int:
    return int(len((prompt + "\n" + (response_text or "")).split()) * 1.3)