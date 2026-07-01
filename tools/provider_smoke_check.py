#!/usr/bin/env python3
"""Small provider smoke checker.

Default mode is dry-run and does not contact any remote service.
Live modes require --live so API keys and quotas are not used by accident.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Provider:
    name: str
    env_key: str
    base_url: str
    chat_path: str
    default_model: str
    models_path: str | None = None
    image_path: str | None = None
    image_model: str | None = None
    image_size: str = "1024x1024"
    video_path: str | None = None
    video_model: str | None = None
    video_status_path: str | None = None
    extra_payload: dict[str, Any] = field(default_factory=dict)
    supports_json_object: bool = True
    fallback_env_keys: tuple[str, ...] = ()

    @property
    def env_keys(self) -> tuple[str, ...]:
        return (self.env_key, *self.fallback_env_keys)


PROVIDERS: dict[str, Provider] = {
    "agnes": Provider(
        name="agnes",
        env_key="AGNES_API_KEY",
        base_url="https://apihub.agnes-ai.com/v1",
        chat_path="/chat/completions",
        default_model="agnes-2.0-flash",
        # Not officially documented. Keep disabled unless explicitly added later.
        models_path=None,
        image_path="/images/generations",
        image_model="agnes-image-2.1-flash",
        image_size="1024x1024",
        video_path="/videos",
        video_model="agnes-video-v2.0",
        video_status_path=None,
        fallback_env_keys=("AGNES_API_KEY_2", "AGNES_API_KEY_3"),
    ),
    "ark": Provider(
        name="ark",
        env_key="ARK_API_KEY",
        base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
        chat_path="/chat/completions",
        default_model="doubao-seed-2.0-code",
        models_path=None,
        supports_json_object=False,
    ),
    "deepseek": Provider(
        name="deepseek",
        env_key="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        chat_path="/chat/completions",
        default_model="deepseek-v4-flash",
        models_path="/models",
        extra_payload={"thinking": {"type": "disabled"}},
    ),
    "glm": Provider(
        name="glm",
        env_key="GLM_API_KEY",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        chat_path="/chat/completions",
        default_model="glm-5.2",
        models_path=None,
        image_path="/images/generations",
        image_model="glm-image",
        image_size="1280x1280",
        video_path="/videos/generations",
        video_model="cogvideox-3",
        video_status_path="/async-result/{id}",
        extra_payload={"thinking": {"type": "disabled"}},
    ),
    "glmfree": Provider(
        name="glmfree",
        env_key="GLM_API_KEY_FREE",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        chat_path="/chat/completions",
        default_model="glm-4.7-flash",
        models_path=None,
        image_path="/images/generations",
        image_model="cogview-3-flash",
        image_size="1024x1024",
        video_path="/videos/generations",
        video_model="cogvideox-flash",
        video_status_path="/async-result/{id}",
        extra_payload={"thinking": {"type": "disabled"}},
    ),
    "longcat": Provider(
        name="longcat",
        env_key="LONGCAT_API_KEY",
        base_url="https://api.longcat.chat/openai/v1",
        chat_path="/chat/completions",
        default_model="LongCat-2.0",
        models_path="/models",
        extra_payload={"thinking": {"type": "disabled"}},
        supports_json_object=False,
    ),
}

TOKEN_BUDGETS: dict[str, int] = {
    "smoke": 4096,
    "intent": 4096,
    "asset": 8192,
    "review": 16384,
    "world": 32768,
    "large": 65536,
    "huge": 131072,
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


def provider_names(selection: str) -> list[str]:
    if selection == "all":
        return list(PROVIDERS)
    return [selection]


def endpoint(provider: Provider, path: str) -> str:
    return provider.base_url.rstrip("/") + path


def env_presence_summary(provider: Provider) -> tuple[str, str]:
    parts: list[str] = []
    any_present = False
    for env_key in provider.env_keys:
        present = bool(os.environ.get(env_key))
        any_present = any_present or present
        parts.append(f"{env_key}:{'yes' if present else 'no'}")
    return "|".join(parts), "yes" if any_present else "no"


def print_dry_run(names: list[str]) -> int:
    for name in names:
        provider = PROVIDERS[name]
        env_summary, key_present = env_presence_summary(provider)
        print(f"[{name}] env={env_summary} present={key_present}")
        print(f"[{name}] chat={endpoint(provider, provider.chat_path)}")
        print(f"[{name}] model={provider.default_model}")
        if provider.models_path:
            print(f"[{name}] models={endpoint(provider, provider.models_path)}")
        else:
            print(f"[{name}] models=unsupported-or-undocumented")
        if provider.image_path:
            print(f"[{name}] image={endpoint(provider, provider.image_path)} model={provider.image_model}")
        if provider.video_path:
            print(f"[{name}] video={endpoint(provider, provider.video_path)} model={provider.video_model}")
    return 0


def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> Any:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        if not body:
            return None
        return json.loads(body)


def require_key(provider: Provider) -> str:
    for env_key in provider.env_keys:
        key = os.environ.get(env_key)
        if key and key.strip():
            return key
    env_names = " or ".join(provider.env_keys)
    raise RuntimeError(f"Missing environment variable: {env_names}")


def live_models(name: str, timeout: int) -> int:
    provider = PROVIDERS[name]
    if not provider.models_path:
        print(f"[{name}] models endpoint is unsupported or undocumented; skipped")
        return 0
    key = require_key(provider)
    data = request_json("GET", endpoint(provider, provider.models_path), key, timeout=timeout)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def live_chat(name: str, prompt: str, max_tokens: int, model_override: str | None, timeout: int) -> int:
    provider = PROVIDERS[name]
    key = require_key(provider)
    model = model_override or provider.default_model
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,
    }
    payload.update(provider.extra_payload)
    data = request_json("POST", endpoint(provider, provider.chat_path), key, payload, timeout=timeout)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def live_structured(name: str, prompt: str, max_tokens: int, model_override: str | None, timeout: int) -> int:
    provider = PROVIDERS[name]
    key = require_key(provider)
    model = model_override or provider.default_model
    if prompt == "Reply with OK.":
        prompt = (
            "json: 把玩家想法编译成一个塔防资产候选。玩家想法："
            "我想要一座用灯光减速敌人、但会消耗额外电力的防御塔。"
            "只返回 JSON，字段包括 name, role, tags, cost, attack, drawback, balance_note。"
        )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是塔防游戏资产编译器。只输出合法 JSON，不要 Markdown。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }
    if provider.supports_json_object:
        payload["response_format"] = {"type": "json_object"}
    payload.update(provider.extra_payload)
    data = request_json("POST", endpoint(provider, provider.chat_path), key, payload, timeout=timeout)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def live_image(
    name: str,
    prompt: str,
    model_override: str | None,
    size_override: str | None,
    timeout: int,
) -> int:
    provider = PROVIDERS[name]
    if not provider.image_path or not provider.image_model:
        print(f"[{name}] image generation is unsupported; skipped")
        return 0
    key = require_key(provider)
    model = model_override or provider.image_model
    size = size_override or provider.image_size
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
    }
    if name in {"glm", "glmfree"} and model == "glm-image":
        payload["quality"] = "standard"
    data = request_json("POST", endpoint(provider, provider.image_path), key, payload, timeout=timeout)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def live_video(
    name: str,
    prompt: str,
    model_override: str | None,
    size_override: str | None,
    timeout: int,
) -> int:
    provider = PROVIDERS[name]
    if not provider.video_path or not provider.video_model:
        print(f"[{name}] video generation is unsupported; skipped")
        return 0
    key = require_key(provider)
    model = model_override or provider.video_model
    if name == "agnes":
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "height": 768,
            "width": 1152,
            "num_frames": 81,
            "frame_rate": 24,
        }
    else:
        payload = {
            "model": model,
            "prompt": prompt,
            "quality": "speed",
            "with_audio": False,
            "size": size_override or "1280x720",
            "fps": 30,
            "duration": 5,
        }
    data = request_json("POST", endpoint(provider, provider.video_path), key, payload, timeout=timeout)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def live_job_status(name: str, job_id: str, timeout: int) -> int:
    provider = PROVIDERS[name]
    key = require_key(provider)
    if name == "agnes":
        url = f"https://apihub.agnes-ai.com/agnesapi?video_id={job_id}"
    elif provider.video_status_path:
        url = endpoint(provider, provider.video_status_path.format(id=job_id))
    else:
        print(f"[{name}] job status endpoint is unsupported; skipped")
        return 0
    data = request_json("GET", url, key, timeout=timeout)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["all", *PROVIDERS.keys()], default="all")
    parser.add_argument(
        "--mode",
        choices=["dry", "models", "chat", "structured", "image", "video", "job"],
        default="dry",
    )
    parser.add_argument("--live", action="store_true", help="Actually contact remote provider APIs.")
    parser.add_argument("--model", default=None, help="Override default model for chat mode.")
    parser.add_argument("--prompt", default="Reply with OK.", help="Prompt for chat/image/video mode.")
    parser.add_argument("--size", default=None, help="Override image or video size.")
    parser.add_argument("--job-id", default=None, help="Job id for job status mode.")
    parser.add_argument(
        "--budget",
        choices=TOKEN_BUDGETS.keys(),
        default="smoke",
        help="Task-level output token budget preset for chat/structured modes.",
    )
    parser.add_argument("--max-tokens", type=int, default=None, help="Override the selected budget preset.")
    parser.add_argument("--request-timeout", type=int, default=60)
    args = parser.parse_args()

    names = provider_names(args.provider)
    max_tokens = args.max_tokens if args.max_tokens is not None else TOKEN_BUDGETS[args.budget]

    if args.mode == "dry":
        return print_dry_run(names)

    if not args.live:
        print("Refusing to contact remote APIs without --live.", file=sys.stderr)
        return 2
    load_dotenv(ROOT / ".env")

    if args.mode in {"chat", "structured"} and args.provider == "all":
        print(f"Refusing live {args.mode} against all providers. Pick one provider.", file=sys.stderr)
        return 2

    if args.mode in {"image", "video", "job"} and args.provider == "all":
        print(f"Refusing live {args.mode} against all providers. Pick one provider.", file=sys.stderr)
        return 2

    if args.mode == "job" and not args.job_id:
        print("Missing --job-id for job mode.", file=sys.stderr)
        return 2

    try:
        if args.mode == "models":
            for name in names:
                live_models(name, args.request_timeout)
            return 0
        if args.mode == "chat":
            return live_chat(names[0], args.prompt, max_tokens, args.model, args.request_timeout)
        if args.mode == "structured":
            return live_structured(names[0], args.prompt, max_tokens, args.model, args.request_timeout)
        if args.mode == "image":
            return live_image(names[0], args.prompt, args.model, args.size, args.request_timeout)
        if args.mode == "video":
            return live_video(names[0], args.prompt, args.model, args.size, args.request_timeout)
        if args.mode == "job":
            return live_job_status(names[0], args.job_id or "", args.request_timeout)
    except urllib.error.HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        try:
            print(exc.read().decode("utf-8"), file=sys.stderr)
        except Exception:
            pass
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
