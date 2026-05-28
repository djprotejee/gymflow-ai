from __future__ import annotations

from dataclasses import dataclass
import os

import httpx


@dataclass(frozen=True)
class AIProviderStatus:
    provider: str
    configured: bool
    primary_model: str
    fallback_model: str


class AIProviderError(RuntimeError):
    pass


class GeminiProvider:
    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.primary_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
        self.fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite").strip()
        self.timeout_seconds = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "25"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def status(self) -> AIProviderStatus:
        return AIProviderStatus(
            provider="gemini",
            configured=self.configured,
            primary_model=self.primary_model,
            fallback_model=self.fallback_model,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        if not self.configured:
            raise AIProviderError("GEMINI_API_KEY is not configured.")

        errors: list[str] = []
        for model in [self.primary_model, self.fallback_model]:
            if not model:
                continue
            try:
                return self._generate_with_model(model=model, system_prompt=system_prompt, user_prompt=user_prompt), model
            except (httpx.HTTPError, KeyError, IndexError, TypeError, AIProviderError) as error:
                errors.append(f"{model}: {error}")
                continue
        raise AIProviderError("; ".join(errors) or "Gemini generation failed.")

    def _generate_with_model(self, model: str, system_prompt: str, user_prompt: str) -> str:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.35,
                "topP": 0.9,
                "maxOutputTokens": 900,
            },
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(endpoint, params={"key": self.api_key}, json=payload)
            if response.status_code >= 400:
                raise AIProviderError(f"HTTP {response.status_code}: {response.text[:300]}")
            data = response.json()
        candidate = data["candidates"][0]
        finish_reason = candidate.get("finishReason", "")
        if finish_reason and finish_reason != "STOP":
            raise AIProviderError(f"Gemini stopped with finishReason={finish_reason}.")
        text = candidate["content"]["parts"][0]["text"].strip()
        if not text:
            raise AIProviderError("Gemini returned an empty response.")
        return text


def get_ai_provider_status() -> AIProviderStatus:
    provider = os.getenv("AI_PROVIDER", "deterministic").strip().lower()
    if provider == "gemini":
        return GeminiProvider().status()
    return AIProviderStatus(
        provider=provider or "deterministic",
        configured=True,
        primary_model="deterministic",
        fallback_model="deterministic",
    )


def generate_with_configured_provider(system_prompt: str, user_prompt: str) -> tuple[str, str]:
    provider = os.getenv("AI_PROVIDER", "deterministic").strip().lower()
    if provider != "gemini":
        raise AIProviderError(f"Provider {provider or 'deterministic'} does not use external generation.")
    return GeminiProvider().generate(system_prompt=system_prompt, user_prompt=user_prompt)
