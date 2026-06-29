"""Image provider adapter: OpenAI-compatible image generation with provider profiles.

Supports multiple image provider profiles. Default mode is dry-run; live mode
requires an explicit flag. Never prints API keys — only env var names.
Uses stdlib urllib only, no extra dependencies.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImageProfile:
    name: str
    env_key: str
    base_url: str
    path: str
    model: str
    default_size: str = "1024x1024"
    extra_payload: dict[str, Any] = field(default_factory=dict)


PROFILES: dict[str, ImageProfile] = {
    "agnes_image_flash": ImageProfile(
        name="agnes_image_flash",
        env_key="AGNES_API_KEY",
        base_url="https://apihub.agnes-ai.com/v1",
        path="/images/generations",
        model="agnes-image-2.1-flash",
        default_size="1024x1024",
    ),
    "glm_image": ImageProfile(
        name="glm_image",
        env_key="GLM_API_KEY",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        path="/images/generations",
        model="glm-image",
        default_size="1280x1280",
        extra_payload={"quality": "standard"},
    ),
    "glmfree_cogview_3_flash": ImageProfile(
        name="glmfree_cogview_3_flash",
        env_key="GLM_API_KEY_FREE",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        path="/images/generations",
        model="cogview-3-flash",
        default_size="1024x1024",
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


def get_api_key(profile: ImageProfile) -> str:
    key = os.environ.get(profile.env_key)
    if not key:
        raise RuntimeError(
            f"Missing environment variable: {profile.env_key} "
            f"(required for profile {profile.name!r})"
        )
    return key


def generate_image(
    profile: ImageProfile,
    prompt: str,
    size: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Call an OpenAI-compatible image generation endpoint.

    Returns the full API response dict.
    """
    api_key = get_api_key(profile)
    url = profile.base_url.rstrip("/") + profile.path

    payload: dict[str, Any] = {
        "model": profile.model,
        "prompt": prompt,
        "size": size or profile.default_size,
    }
    payload.update(profile.extra_payload)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        if not body:
            raise RuntimeError("empty response from image provider")
        return json.loads(body)


def extract_image_url(response: dict[str, Any]) -> str:
    """Extract the first image URL or base64 data from a standard response.

    Supports common {data: [{url: "..."}]} structure.
    Falls back to b64_json if present.
    """
    data_list = response.get("data", [])
    if not isinstance(data_list, list) or not data_list:
        raise RuntimeError("no data array in image provider response")

    first = data_list[0]
    if not isinstance(first, dict):
        raise RuntimeError("image data entry is not an object")

    url = first.get("url")
    if isinstance(url, str) and url:
        return url

    b64 = first.get("b64_json")
    if isinstance(b64, str) and b64:
        return f"data:image/png;base64,{b64}"

    raise RuntimeError("no url or b64_json found in image data entry")


def download_image(
    url: str,
    output_path: Path,
    timeout: int = 120,
) -> Path:
    """Download an image from a URL to a local file.

    Supports both http/https URLs and data: URIs (base64).
    Returns the output path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if url.startswith("data:"):
        _, b64_data = url.split(",", 1)
        image_bytes = base64.b64decode(b64_data)
        output_path.write_bytes(image_bytes)
        return output_path

    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        image_bytes = response.read()

    output_path.write_bytes(image_bytes)
    return output_path
