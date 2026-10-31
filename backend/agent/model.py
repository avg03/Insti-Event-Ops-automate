"""LLM Client adapter supporting Google Gemini and OpenAI with deterministic fallback.

This module provides structured natural-language capabilities:
- Contextual guest invitation text customized to real Crustdata profiles
- Natural language brief extraction & topic expansion
- Dynamic promotional campaign copy and reel storyboards
- Disruption recovery explanations
"""

from __future__ import annotations

import os
from typing import Any
import httpx
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """Zero-dependency asynchronous LLM adapter using httpx."""

    def __init__(self) -> None:
        self.gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def is_configured(self) -> bool:
        return bool(self.gemini_key or self.openai_key)

    @property
    def active_provider(self) -> str:
        if self.gemini_key:
            return f"Gemini ({self.gemini_model})"
        if self.openai_key:
            return f"OpenAI ({self.openai_model})"
        return "Deterministic Template Engine (Fallback)"

    async def generate_text(self, prompt: str, system_prompt: str | None = None) -> str | None:
        """Query configured LLM provider, returning fallback template if unconfigured or failed."""
        if self.gemini_key:
            return await self._call_gemini(prompt, system_prompt)
        if self.openai_key:
            return await self._call_openai(prompt, system_prompt)
        return None

    async def _call_gemini(self, prompt: str, system_prompt: str | None = None) -> str | None:
        candidate_models = [self.gemini_model, "gemini-flash-lite-latest", "gemini-3.8-flash"]
        # Deduplicate while preserving order
        models_to_try = list(dict.fromkeys(candidate_models))

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System context:\n{system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will act according to this context."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key}"
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, json={"contents": contents})
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
            except Exception:
                continue
        return None

    async def _call_openai(self, prompt: str, system_prompt: str | None = None) -> str | None:
        url = "https://api.openai.com/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.openai_model,
                        "messages": messages,
                        "temperature": 0.7,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0]["message"]["content"].strip()
        except Exception:
            return None
        return None


llm_client = LLMClient()
