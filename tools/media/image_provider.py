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
import urllib.parse
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
    fallback_env_keys: tuple[str, ...] = ()

    @property
    def env_keys(self) -> tuple[str, ...]:
        return (self.env_key, *self.fallback_env_keys)


TRANSIENT_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})


class TransientProviderError(RuntimeError):
    """Base class for retryable transport-layer provider errors.

    Carries no provider response body. The string form is a compact
    ``stage:kind`` token so it can be recorded without retaining secrets or
    upstream error payloads.
    """


class TransientHttpError(TransientProviderError):
    """A retryable provider HTTP error (429/500/502/503/504).

    Only the status code is retained; the response body is intentionally
    discarded so retry reports and evidence never store upstream payloads.
    """

    def __init__(self, status_code: int, *, stage: str = "image_generation"):
        self.status_code = int(status_code)
        self.stage = stage
        super().__init__(f"{stage}:transient_http_{self.status_code}")


class TransientTransportError(TransientProviderError):
    """A retryable transport-layer error (connection, DNS, timeout).

    Wraps low-level ``URLError``/``TimeoutError`` causes without retaining
    upstream response bodies.
    """

    def __init__(self, *, stage: str = "image_generation", cause_type: str = "transport"):
        self.stage = stage
        self.cause_type = cause_type or "transport"
        super().__init__(f"{stage}:transient_transport:{self.cause_type}")


class HttpError(RuntimeError):
    """A non-transient provider HTTP error; carries the status code only."""

    def __init__(self, status_code: int, *, stage: str = "image_generation"):
        self.status_code = int(status_code)
        self.stage = stage
        super().__init__(f"{stage}:http_{self.status_code}")


def is_transient_error(exc: BaseException) -> bool:
    """Return True if ``exc`` is a retryable transport-layer provider error."""
    return isinstance(exc, TransientProviderError)


PROFILES: dict[str, ImageProfile] = {
    "agnes_image_flash": ImageProfile(
        name="agnes_image_flash",
        env_key="AGNES_API_KEY",
        fallback_env_keys=("AGNES_API_KEY_2", "AGNES_API_KEY_3"),
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


def get_api_key(profile: ImageProfile, credential_index: int = 0) -> str:
    keys = [
        key.strip()
        for env_key in profile.env_keys
        if (key := os.environ.get(env_key)) and key.strip()
    ]
    if keys:
        return keys[max(0, credential_index) % len(keys)]
    env_names = " or ".join(profile.env_keys)
    raise RuntimeError(
        f"Missing environment variable: {env_names} "
        f"(required for profile {profile.name!r})"
    )


def parse_size(size: str) -> tuple[int, int]:
    """Parse an image size string like 1024x1024."""
    parts = size.lower().split("x", 1)
    if len(parts) != 2:
        raise ValueError(f"invalid image size {size!r}; expected WIDTHxHEIGHT")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"invalid image size {size!r}; dimensions must be integers") from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid image size {size!r}; dimensions must be positive")
    if width > 4096 or height > 4096:
        raise ValueError(f"invalid image size {size!r}; maximum supported dimension is 4096")
    return width, height


def validate_size(size: str) -> str:
    """Validate either an exact size or an Agnes resolution tier."""
    normalized = size.strip()
    if normalized.upper() in {"1K", "2K", "3K", "4K"}:
        return normalized.upper()
    parse_size(normalized)
    return normalized


def validate_ratio(ratio: str) -> str:
    normalized = ratio.strip()
    supported = {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"}
    if normalized not in supported:
        raise ValueError(f"unsupported image ratio {ratio!r}")
    return normalized


def image_data_uri(path: Path, max_bytes: int = 20 * 1024 * 1024) -> str:
    """Encode a local PNG/JPEG/WebP reference without publishing it."""
    size = path.stat().st_size
    if size > max_bytes:
        raise RuntimeError(f"input image exceeds maximum allowed size: {path}")
    mime_by_suffix = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime = mime_by_suffix.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported input image type: {path.suffix}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_generation_payload(
    profile: ImageProfile,
    prompt: str,
    *,
    size: str | None = None,
    ratio: str | None = None,
    input_images: list[str] | None = None,
    response_format: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": profile.model,
        "prompt": prompt,
        "size": validate_size(size or profile.default_size),
    }
    payload.update(profile.extra_payload)
    if ratio is not None:
        payload["ratio"] = validate_ratio(ratio)
    if input_images or response_format:
        extra_body = dict(payload.get("extra_body") or {})
        if input_images:
            extra_body["image"] = list(input_images)
        if response_format:
            if response_format not in {"url", "b64_json"}:
                raise ValueError(f"unsupported image response format {response_format!r}")
            extra_body["response_format"] = response_format
        payload["extra_body"] = extra_body
    return payload


def generate_image(
    profile: ImageProfile,
    prompt: str,
    size: str | None = None,
    timeout: int = 120,
    *,
    ratio: str | None = None,
    input_images: list[str] | None = None,
    response_format: str | None = None,
    credential_index: int = 0,
) -> dict[str, Any]:
    """Call an OpenAI-compatible image generation endpoint.

    Returns the full API response dict.
    """
    api_key = get_api_key(profile, credential_index)
    url = profile.base_url.rstrip("/") + profile.path

    payload = build_generation_payload(
        profile,
        prompt,
        size=size,
        ratio=ratio,
        input_images=input_images,
        response_format=response_format,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            if not body:
                raise RuntimeError("empty response from image provider")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        # Read and discard the body: it must never be retained in errors or
        # reports. Only the identifiable status code survives.
        exc.read()
        if exc.code in TRANSIENT_HTTP_STATUS:
            raise TransientHttpError(exc.code, stage="image_generation") from exc
        raise HttpError(exc.code, stage="image_generation") from exc
    except urllib.error.URLError as exc:
        cause_type = type(exc.reason).__name__ if exc.reason is not None else "URLError"
        raise TransientTransportError(
            stage="image_generation", cause_type=cause_type or "URLError"
        ) from exc
    except TimeoutError as exc:
        raise TransientTransportError(
            stage="image_generation", cause_type="TimeoutError"
        ) from exc


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
    max_bytes: int = 20 * 1024 * 1024,
) -> Path:
    """Download an image from a URL to a local file.

    Supports both http/https URLs and data: URIs (base64).
    Returns the output path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "data":
        _, b64_data = url.split(",", 1)
        image_bytes = base64.b64decode(b64_data)
        if len(image_bytes) > max_bytes:
            raise RuntimeError("decoded image exceeds maximum allowed size")
        output_path.write_bytes(image_bytes)
        return output_path

    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"unsupported image URL scheme: {parsed.scheme!r}")

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError("downloaded image exceeds maximum allowed size")
                chunks.append(chunk)
            image_bytes = b"".join(chunks)
    except urllib.error.HTTPError as exc:
        exc.read()
        if exc.code in TRANSIENT_HTTP_STATUS:
            raise TransientHttpError(exc.code, stage="image_download") from exc
        raise HttpError(exc.code, stage="image_download") from exc
    except urllib.error.URLError as exc:
        cause_type = type(exc.reason).__name__ if exc.reason is not None else "URLError"
        raise TransientTransportError(
            stage="image_download", cause_type=cause_type or "URLError"
        ) from exc
    except TimeoutError as exc:
        raise TransientTransportError(
            stage="image_download", cause_type="TimeoutError"
        ) from exc

    output_path.write_bytes(image_bytes)
    return output_path
