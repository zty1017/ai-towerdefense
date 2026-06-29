"""LLM adapter: OpenAI-compatible chat completions with provider profiles.

Supports multiple provider profiles. Default mode is dry-run; live mode
requires an explicit flag. Never prints API keys — only env var names.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    env_key: str
    base_url: str
    model: str
    supports_json_object: bool = True


PROFILES: dict[str, ProviderProfile] = {
    "ark_deepseek_v4_flash": ProviderProfile(
        name="ark_deepseek_v4_flash",
        env_key="ARK_API_KEY",
        base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
        model="deepseek-v4-flash",
        supports_json_object=False,
    ),
    "ark_deepseek_v4_pro": ProviderProfile(
        name="ark_deepseek_v4_pro",
        env_key="ARK_API_KEY",
        base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
        model="deepseek-v4-pro",
        supports_json_object=False,
    ),
    "ark_glm_5_2": ProviderProfile(
        name="ark_glm_5_2",
        env_key="ARK_API_KEY",
        base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
        model="glm-5.2",
    ),
    "deepseek_v4_flash": ProviderProfile(
        name="deepseek_v4_flash",
        env_key="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    ),
    "deepseek_v4_pro": ProviderProfile(
        name="deepseek_v4_pro",
        env_key="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
    ),
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key(profile: ProviderProfile) -> str:
    key = os.environ.get(profile.env_key)
    if not key:
        raise RuntimeError(
            f"Missing environment variable: {profile.env_key} "
            f"(required for profile {profile.name!r})"
        )
    return key


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from text.

    Handles:
    - Direct JSON (starts with {)
    - Markdown fenced JSON (```json ... ```)
    - Text with leading/trailing noise
    """
    # Try markdown fenced first
    m = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try direct JSON
    text_stripped = text.strip()
    if text_stripped.startswith("{"):
        try:
            return json.loads(text_stripped)
        except json.JSONDecodeError:
            pass

    # Try JSON objects embedded in explanatory text. raw_decode handles braces
    # inside quoted strings correctly, unlike a naive brace counter.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def chat_completion(
    profile: ProviderProfile,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    timeout: int = 90,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call an OpenAI-compatible chat completion endpoint.

    Returns the full API response dict.
    """
    api_key = get_api_key(profile)
    url = profile.base_url.rstrip("/") + "/chat/completions"

    payload: dict[str, Any] = {
        "model": profile.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        if not body:
            raise RuntimeError("empty response from provider")
        return json.loads(body)


def extract_content_from_response(response: dict[str, Any]) -> str:
    """Extract the text content from a chat completion response."""
    choices = response.get("choices", [])
    if not choices:
        raise RuntimeError("no choices in provider response")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str):
        raise RuntimeError(f"unexpected content type: {type(content).__name__}")
    return content
