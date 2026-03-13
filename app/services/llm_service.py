from __future__ import annotations

import os
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
    LLM call via Google Gemini with optional Langfuse tracing.

    Configuration:
      - GEMINI_API_KEY: Your Gemini API key
      - GEMINI_MODEL: Model name (default: gemini-2.0-flash)

    Returns: (response_text, total_tokens) or None on failure.
    """
    from app.core import config

    api_key = config.GEMINI_API_KEY
    model_name = config.GEMINI_MODEL

    if not api_key:
        logger.error("[LLM] GEMINI_API_KEY not set in environment")
        return None

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
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
            ),
        )

        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        text = response.text.strip() if response.text else ""
        input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

        return text, input_tokens, output_tokens, latency_ms

    langfuse = get_langfuse_client()

    # -------- traced path --------
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
                }
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
                logger.error(f"[LLM] Gemini error: {e}", exc_info=True)
                generation.end(output=f"Error: {str(e)}", metadata={"error": True})
                trace.update(tags=["error", "gemini"], metadata={"error": str(e)})
                return None

        except Exception as e:
            logger.warning(f"[Langfuse] Tracing error: {e}", exc_info=True)
            # fall through to non-traced path

    # -------- non-traced path --------
    try:
        logger.info(f"[LLM] Calling Gemini (no tracing)...")

        text, in_tok, out_tok, latency_ms = _call_gemini_api()

        logger.info(f"[LLM] Gemini response received ({latency_ms:.0f}ms)")

        return text, in_tok + out_tok

    except Exception as e:
        logger.error(f"[LLM] Gemini error: {e}", exc_info=True)
        return None