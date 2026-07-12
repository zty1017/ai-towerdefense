"""Guarded optional world evolution after deterministic battle settlement.

The deterministic campaign delta is always computed by the caller first. This
service may then append a small, validated live delta to that resulting state.
Normal runtime can discover the shared worktree ``.env`` just like the other
live compiler services, but prompts, provider bodies, and credentials are never
returned or persisted.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
_LLM_DIR = _REPO_ROOT / "tools" / "llm"
_WORLD_STATE_DIR = _REPO_ROOT / "tools" / "world_state"
_REVIEW_PACK = (
    _REPO_ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
)
_PROFILE_NAME = "ark_deepseek_v4_flash"
_ALLOWED_OPS = frozenset(
    {
        "append_event",
        "adjust_resource",
        "update_npc_relationship",
        "introduce_npc",
        "upsert_task",
        "schedule_random_event",
    }
)
_MAX_OPERATIONS = 8
_MAX_RESOURCE_CHANGE = 2
_MAX_TOTAL_RESOURCE_CHANGE = 3
_MAX_RELATIONSHIP_CHANGE = 0.1
# At most one bounded repair attempt after the first candidate fails a gate.
_MAX_REPAIR_ATTEMPTS = 1
_DEFAULT_TIMEOUT_SECONDS = 45
# The browser allows 100 seconds for settlement. Two bounded provider attempts
# must therefore remain below that deadline, including validation overhead.
_MAX_TIMEOUT_SECONDS = 45
# Stage labels and their compact, non-sensitive diagnostic codes. The codes are
# deliberately free of raw validator text so the diagnostic never leaks content.
_STAGE_ERROR_CODE = {
    "structure": "structure_invalid",
    "semantic": "semantic_invalid",
    "policy": "policy_violation",
    "apply": "apply_failed",
    "output_state": "output_state_invalid",
    "parse": "parse_failed",
    "provider": "provider_error",
}
_ERROR_FEEDBACK_LIMIT = 8
_ERROR_MESSAGE_LIMIT = 240
_LIVE_APPEND_SYSTEM_POLICY = """

本次调用只为确定性战役结算追加少量战后演化。必须服从用户消息中的
post_battle_live_policy：不得输出 set_progress_phase、set_map_node_state、
set_flag、unlock_fact、研究/蓝图/样品操作，不得创建 main 任务，也不得复用
已有事件、任务、随机事件或 NPC 标识。确定性主线已经提交，不得改写或回滚。

所有非 nullable 的可选字段若无有效值必须整条省略，不得用 null、空串或占位值
填充：尤其 schedule_random_event 的 random_event.related_task_id，在没有可关联
任务时必须省略该字段，绝不要写 null、"" 或 "none"；append_event/upsert_task 等
其它可选字段同理。若某字段在本轮确实没有内容，直接不输出该键。
"""


def _modules():
    for path in (_LLM_DIR, _WORLD_STATE_DIR):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    import adapter  # type: ignore
    import apply_world_delta  # type: ignore
    import validate_run_world_state  # type: ignore
    import validate_world_delta  # type: ignore
    import validate_world_delta_semantics  # type: ignore
    import world_delta_prompt  # type: ignore

    return (
        adapter,
        apply_world_delta,
        validate_run_world_state,
        validate_world_delta,
        validate_world_delta_semantics,
        world_delta_prompt,
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _dotenv_path() -> Path:
    configured = os.environ.get("AI_TD_ENV_FILE")
    if configured:
        return Path(configured).expanduser()
    local = _REPO_ROOT / ".env"
    if local.is_file():
        return local
    git_pointer = _REPO_ROOT / ".git"
    if git_pointer.is_file():
        try:
            marker = git_pointer.read_text(encoding="utf-8").strip()
            if marker.startswith("gitdir:"):
                git_dir = Path(marker.partition(":")[2].strip()).resolve()
                for parent in git_dir.parents:
                    candidate = parent / ".env"
                    if (parent / ".git").exists() and candidate.is_file():
                        return candidate
        except OSError:
            pass
    return local


def _enabled() -> bool:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    mode = os.environ.get("AI_TD_LIVE_WORLD_EVOLUTION", "auto").strip().lower()
    return mode not in {"0", "false", "off", "disabled"}


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _request_provider_response(
    messages: list[dict[str, str]], *, timeout: int, max_tokens: int
) -> dict[str, Any]:
    """Call the fixed provider profile; kept narrow so tests can mock the wire."""
    adapter, *_ = _modules()
    profile = adapter.PROFILES[_PROFILE_NAME]
    return adapter.chat_completion(
        profile,
        messages,
        timeout=timeout,
        max_tokens=max_tokens,
        response_format={"type": "json_object"} if profile.supports_json_object else None,
    )


def _dedupe(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))


def _ids(items: Any, key: str) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {
        str(item[key])
        for item in items
        if isinstance(item, dict) and isinstance(item.get(key), str) and item[key]
    }


def _visible_texts(delta: dict[str, Any]) -> list[str]:
    texts = [delta.get("summary")]
    for operation in delta.get("operations", []):
        if not isinstance(operation, dict):
            continue
        for container_key, text_keys in (
            ("event", ("summary",)),
            ("task", ("title", "summary")),
            ("random_event", ("summary",)),
        ):
            container = operation.get(container_key)
            if isinstance(container, dict):
                texts.extend(container.get(key) for key in text_keys)
    return [text for text in texts if isinstance(text, str)]


def _controlled_policy_errors(
    delta: dict[str, Any], state: dict[str, Any], *, require_next_turn: bool = True
) -> list[str]:
    """Reject updates that could overwrite deterministic campaign authority."""
    errors: list[str] = []
    operations = delta.get("operations")
    if not isinstance(operations, list):
        return ["operations must be an array"]
    if len(operations) > _MAX_OPERATIONS:
        errors.append(f"operations exceeds live limit {_MAX_OPERATIONS}")

    current_turn = (state.get("progress") or {}).get("turn", 1)
    if not isinstance(current_turn, int):
        current_turn = 1
    if require_next_turn and delta.get("created_turn") != current_turn + 1:
        errors.append("created_turn must be the next run turn")

    existing_events = _ids(state.get("event_log"), "event_id")
    existing_tasks = _ids(state.get("tasks"), "task_id")
    existing_random_events = _ids(state.get("random_events"), "random_event_id")
    existing_npcs = _ids(state.get("npcs"), "npc_id")
    existing_resources = _ids(state.get("resources"), "resource_id")
    introduced_events: set[str] = set()
    introduced_tasks: set[str] = set()
    introduced_random_events: set[str] = set()
    introduced_npcs: set[str] = set()
    total_resource_change = 0.0

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            continue
        op = operation.get("op")
        path = f"operations[{index}]"
        if op not in _ALLOWED_OPS:
            errors.append(f"{path}.op is outside the post-battle append policy")
            continue
        if op == "append_event":
            event = operation.get("event") or {}
            event_id = event.get("event_id") if isinstance(event, dict) else None
            if event_id in existing_events or event_id in introduced_events:
                errors.append(f"{path} must append a new event_id")
            if isinstance(event_id, str):
                introduced_events.add(event_id)
            if isinstance(event, dict) and event.get("turn") != delta.get("created_turn"):
                errors.append(f"{path}.event.turn must match created_turn")
        elif op == "upsert_task":
            task = operation.get("task") or {}
            task_id = task.get("task_id") if isinstance(task, dict) else None
            if task_id in existing_tasks or task_id in introduced_tasks:
                errors.append(f"{path} must append a new task_id")
            if isinstance(task_id, str):
                introduced_tasks.add(task_id)
            if isinstance(task, dict) and task.get("kind") == "main":
                errors.append(f"{path} cannot create or replace a core main task")
            if isinstance(task, dict) and task.get("status") not in {"available", "active"}:
                errors.append(f"{path} must create a playable pending task")
        elif op == "schedule_random_event":
            event = operation.get("random_event") or {}
            event_id = event.get("random_event_id") if isinstance(event, dict) else None
            if event_id in existing_random_events or event_id in introduced_random_events:
                errors.append(f"{path} must append a new random_event_id")
            if isinstance(event_id, str):
                introduced_random_events.add(event_id)
            if isinstance(event, dict) and event.get("status") not in {"pending", "available"}:
                errors.append(f"{path} must schedule a pending event")
        elif op == "introduce_npc":
            npc = operation.get("npc") or {}
            npc_id = npc.get("npc_id") if isinstance(npc, dict) else None
            if npc_id in existing_npcs or npc_id in introduced_npcs:
                errors.append(f"{path} must append a new npc_id")
            if isinstance(npc_id, str):
                introduced_npcs.add(npc_id)
            roles = npc.get("gameplay_roles") if isinstance(npc, dict) else None
            if not isinstance(roles, list) or not roles:
                errors.append(f"{path} requires at least one functional gameplay role")
        elif op == "update_npc_relationship":
            npc_id = operation.get("npc_id")
            if npc_id not in existing_npcs | introduced_npcs:
                errors.append(f"{path} can only change a present or newly introduced NPC")
            relationship = operation.get("relationship_delta") or {}
            trust = relationship.get("trust") if isinstance(relationship, dict) else None
            if not isinstance(trust, (int, float)) or isinstance(trust, bool):
                errors.append(f"{path} requires a numeric trust change")
            elif abs(float(trust)) > _MAX_RELATIONSHIP_CHANGE:
                errors.append(f"{path} relationship change is too large")
        elif op == "adjust_resource":
            resource_id = operation.get("resource_id")
            amount = operation.get("amount_delta")
            if resource_id not in existing_resources:
                errors.append(f"{path} can only adjust an existing run resource")
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                errors.append(f"{path} requires a numeric amount_delta")
            else:
                total_resource_change += abs(float(amount))
                if abs(float(amount)) > _MAX_RESOURCE_CHANGE:
                    errors.append(f"{path} resource change is too large")

    if total_resource_change > _MAX_TOTAL_RESOURCE_CHANGE:
        errors.append("total resource change is too large")
    for text in _visible_texts(delta):
        unsafe_control = any(
            ord(character) < 32 and character not in "\n\t" for character in text
        )
        if len(text) > 600 or "<" in text or ">" in text or unsafe_control:
            errors.append("player-visible delta text is not runtime-safe")
            break
    return _dedupe(errors)


def _projection_fields(delta: dict[str, Any]) -> dict[str, Any]:
    next_task: dict[str, str] | None = None
    npc_feedback: str | None = None
    for operation in delta.get("operations", []):
        if not isinstance(operation, dict):
            continue
        if next_task is None and operation.get("op") == "upsert_task":
            task = operation.get("task")
            if isinstance(task, dict):
                next_task = {
                    "task_id": str(task.get("task_id") or "")[:128],
                    "title": str(task.get("title") or "")[:120],
                    "summary": str(task.get("summary") or "")[:600],
                }
        if npc_feedback is None and operation.get("op") == "append_event":
            event = operation.get("event")
            if isinstance(event, dict) and event.get("kind") == "npc":
                npc_feedback = str(event.get("summary") or "")[:600]
    projected: dict[str, Any] = {"interlude_summary": str(delta.get("summary") or "")[:600]}
    if next_task and next_task["task_id"] and next_task["title"]:
        projected["next_task"] = next_task
    if npc_feedback:
        projected["npc_feedback"] = npc_feedback
    return projected


def replay_committed_deltas(
    deterministic_state: dict[str, Any], deltas: list[dict[str, Any]]
) -> dict[str, Any]:
    """Replay previously gated append deltas over a later campaign baseline.

    A cumulative deterministic fixture remains authoritative. Historical
    deltas that no longer pass current gates are skipped individually, so one
    stale append cannot erase other previously committed live content.
    """
    if not deltas:
        return deterministic_state
    (
        _,
        applier,
        state_validator,
        delta_validator,
        semantic_validator,
        _,
    ) = _modules()
    state = deterministic_state
    try:
        for delta in deltas:
            if not isinstance(delta, dict):
                continue
            if _dedupe(
                [
                    *delta_validator.validate_with_jsonschema(delta),
                    *delta_validator.validate_world_delta(delta),
                ]
            ):
                continue
            registry = semantic_validator.build_reference_registry(state, _REVIEW_PACK)
            if semantic_validator.validate_world_delta_semantics(delta, state, registry):
                continue
            if _controlled_policy_errors(delta, state, require_next_turn=False):
                continue
            previous_state = state
            state, apply_errors = applier.apply_delta(state, delta)
            if apply_errors:
                state = previous_state
                continue
        if _dedupe(
            [
                *state_validator.validate_with_jsonschema(state),
                *state_validator.validate_run_world_state(state),
            ]
        ):
            return deterministic_state
    except Exception:
        return deterministic_state
    return state


def _diagnostic(attempt_count: int, fallback_stage, error_codes) -> dict[str, Any]:
    return {
        "attempt_count": attempt_count,
        "fallback_stage": fallback_stage,
        "error_codes": sorted(set(error_codes)),
    }


def _truncate_validation_error(text: str) -> str:
    """Bound a validator message before feeding it back to the provider.

    Validator strings are deterministic and contain no secrets, but we strip
    control characters and cap their length so the repair prompt stays small
    and cannot accidentally surface unrelated content.
    """
    cleaned = " ".join(str(text).split())
    if len(cleaned) > _ERROR_MESSAGE_LIMIT:
        cleaned = cleaned[:_ERROR_MESSAGE_LIMIT].rstrip() + "..."
    return cleaned


def _build_repair_user_prompt(candidate: dict[str, Any], errors: list[str]) -> str:
    sanitized = [_truncate_validation_error(error) for error in errors[:_ERROR_FEEDBACK_LIMIT]]
    parts = [
        "你上一轮返回的 WorldStateDelta 未能通过校验，已被整体回退。",
        "请仅修复下面的校验错误，并返回**完整**的合法 WorldStateDelta v0.1 JSON 对象。",
        "要求：不得输出 Markdown、解释文字或代码块；不得附加 raw_prompt/response/key 等字段；"
        "所有非 nullable 可选字段若无值必须省略（尤其是 random_event.related_task_id 不得写 null 或空串）。",
        "候选 JSON：",
        json.dumps(candidate, ensure_ascii=False),
        "校验错误（已截断）：",
    ]
    parts.extend(sanitized)
    return "\n".join(parts)


def _evaluate_delta(
    delta: dict[str, Any],
    deterministic_state: dict[str, Any],
    registry: Any,
    applier: Any,
    delta_validator: Any,
    semantic_validator: Any,
    state_validator: Any,
) -> tuple[bool, str | None, list[str], Any, list[str]]:
    """Run the full gate pipeline in order.

    Returns ``(ok, failed_stage, error_codes, next_state, error_messages)``.
    ``error_codes`` / ``error_messages`` describe only the first failing gate,
    so they are safe to surface back to the provider as repair hints without
    leaking the original prompt or response.
    """
    structure_errors = _dedupe(
        [
            *delta_validator.validate_with_jsonschema(delta),
            *delta_validator.validate_world_delta(delta),
        ]
    )
    if structure_errors:
        return (
            False,
            "structure",
            [_STAGE_ERROR_CODE["structure"]],
            None,
            structure_errors,
        )
    semantic_errors = semantic_validator.validate_world_delta_semantics(
        delta, deterministic_state, registry
    )
    if semantic_errors:
        return (
            False,
            "semantic",
            [_STAGE_ERROR_CODE["semantic"]],
            None,
            semantic_errors,
        )
    policy_errors = _controlled_policy_errors(delta, deterministic_state)
    if policy_errors:
        return (
            False,
            "policy",
            [_STAGE_ERROR_CODE["policy"]],
            None,
            policy_errors,
        )
    next_state, apply_errors = applier.apply_delta(deterministic_state, delta)
    if apply_errors:
        return (
            False,
            "apply",
            [_STAGE_ERROR_CODE["apply"]],
            None,
            apply_errors,
        )
    next_state_errors = _dedupe(
        [
            *state_validator.validate_with_jsonschema(next_state),
            *state_validator.validate_run_world_state(next_state),
        ]
    )
    if next_state_errors:
        return (
            False,
            "output_state",
            [_STAGE_ERROR_CODE["output_state"]],
            None,
            next_state_errors,
        )
    return (True, None, [], next_state, [])


def evolve_world(
    *,
    deterministic_state: dict[str, Any],
    battle_result: dict[str, Any],
    deployed_objects: list[dict[str, Any]],
    session_context: dict[str, Any],
) -> dict[str, Any]:
    """Return an applied live evolution or a silent deterministic fallback.

    The result always carries an internal-only ``diagnostic`` (never player
    facing): ``attempt_count``, ``fallback_stage`` and ``error_codes``. On a
    first-attempt gate failure the candidate JSON plus truncated/sanitized
    validation errors are fed back to the *same* fixed provider for at most
    one bounded repair; the repaired candidate is then re-validated through the
    full gate pipeline. No raw prompt, response, or credential is persisted and
    the schema is never relaxed; a provider timeout or exception degrades
    deterministically to the original state.
    """
    diagnostic_disabled = _diagnostic(0, None, [])
    fallback = {
        "applied": False,
        "state": deterministic_state,
        "diagnostic": diagnostic_disabled,
    }
    if not _enabled():
        return fallback

    (
        adapter,
        applier,
        state_validator,
        delta_validator,
        semantic_validator,
        prompt_helper,
    ) = _modules()
    adapter.load_dotenv(_dotenv_path())
    profile = adapter.PROFILES[_PROFILE_NAME]
    if not os.environ.get(profile.env_key):
        return fallback
    if _dedupe(
        [
            *state_validator.validate_with_jsonschema(deterministic_state),
            *state_validator.validate_run_world_state(deterministic_state),
        ]
    ):
        return fallback

    review_pack = _load_json(_REVIEW_PACK)
    prompt_battle_result = dict(battle_result)
    prompt_battle_result["deployed_objects"] = deployed_objects
    prompt_session_context = dict(session_context)
    prompt_session_context["world_evolution_policy"] = {
        "allowed_operations": sorted(_ALLOWED_OPS),
        "append_only_ids": ["event_id", "task_id", "random_event_id", "npc_id"],
        "forbid_main_task": True,
        "max_operations": _MAX_OPERATIONS,
        "max_resource_change": _MAX_RESOURCE_CHANGE,
        "deterministic_campaign_progress_is_immutable": True,
        "omit_empty_optional_fields": True,
    }
    messages = [
        {
            "role": "system",
            "content": prompt_helper.SYSTEM_PROMPT + _LIVE_APPEND_SYSTEM_POLICY,
        },
        {
            "role": "user",
            "content": prompt_helper.build_user_prompt(
                deterministic_state,
                prompt_battle_result,
                prompt_session_context,
                review_pack,
            ),
        },
    ]
    timeout = _bounded_env_int(
        "AI_TD_WORLD_EVOLUTION_TIMEOUT", _DEFAULT_TIMEOUT_SECONDS, 1, _MAX_TIMEOUT_SECONDS
    )
    max_tokens = _bounded_env_int(
        "AI_TD_WORLD_EVOLUTION_MAX_TOKENS", 4096, 512, 8192
    )
    registry = semantic_validator.build_reference_registry(
        deterministic_state, _REVIEW_PACK
    )
    attempt_count = 0
    try:
        response = _request_provider_response(
            messages, timeout=timeout, max_tokens=max_tokens
        )
        attempt_count = 1
        candidate = adapter.extract_json(
            adapter.extract_content_from_response(response)
        )
        if not isinstance(candidate, dict):
            return {
                "applied": False,
                "state": deterministic_state,
                "diagnostic": _diagnostic(1, "parse", [_STAGE_ERROR_CODE["parse"]]),
            }
        ok, stage, codes, next_state, error_messages = _evaluate_delta(
            candidate,
            deterministic_state,
            registry,
            applier,
            delta_validator,
            semantic_validator,
            state_validator,
        )
        if ok:
            return {
                "applied": True,
                "state": next_state,
                "delta": candidate,
                "projection": _projection_fields(candidate),
                "diagnostic": _diagnostic(1, None, []),
            }

        # First candidate failed a gate -> bounded repair (at most one retry).
        repair_messages = [
            *messages,
            {
                "role": "assistant",
                "content": json.dumps(candidate, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": _build_repair_user_prompt(candidate, error_messages),
            },
        ]
        response = _request_provider_response(
            repair_messages, timeout=timeout, max_tokens=max_tokens
        )
        attempt_count = 1 + _MAX_REPAIR_ATTEMPTS
        candidate = adapter.extract_json(
            adapter.extract_content_from_response(response)
        )
        if not isinstance(candidate, dict):
            return {
                "applied": False,
                "state": deterministic_state,
                "diagnostic": _diagnostic(
                    attempt_count, "parse", codes + [_STAGE_ERROR_CODE["parse"]]
                ),
            }
        ok, stage, codes2, next_state, _ = _evaluate_delta(
            candidate,
            deterministic_state,
            registry,
            applier,
            delta_validator,
            semantic_validator,
            state_validator,
        )
        if ok:
            return {
                "applied": True,
                "state": next_state,
                "delta": candidate,
                "projection": _projection_fields(candidate),
                "diagnostic": _diagnostic(attempt_count, None, []),
            }
        return {
            "applied": False,
            "state": deterministic_state,
            "diagnostic": _diagnostic(attempt_count, stage, codes + codes2),
        }
    except Exception:
        return {
            "applied": False,
            "state": deterministic_state,
            "diagnostic": _diagnostic(
                attempt_count or 1, "provider", [_STAGE_ERROR_CODE["provider"]]
            ),
        }
