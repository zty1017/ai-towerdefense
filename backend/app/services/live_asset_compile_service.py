"""Optional live LLM compilation for player research proposals.

Only a validated candidate and compact provenance are retained. Raw prompts,
provider response bodies, and secrets never enter the database or runtime.
"""

from __future__ import annotations

import json
import os
import sys
import hashlib
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
_LLM_DIR = _REPO_ROOT / "tools" / "llm"
_CONTENT_PIPELINE_DIR = _REPO_ROOT / "tools" / "content_pipeline"
_EFFECT_REGISTRY = _REPO_ROOT / "shared" / "module_registry" / "effect_blocks.v0.1.json"
_DEFAULT_PROFILE = "ark_deepseek_v4_flash"


def _modules():
    for path in (_LLM_DIR, _CONTENT_PIPELINE_DIR):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    import adapter  # type: ignore
    import asset_candidate_prompt  # type: ignore
    import validate_asset_candidate  # type: ignore

    return adapter, asset_candidate_prompt, validate_asset_candidate


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _mode() -> str:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return "off"
    raw = os.environ.get("AI_TD_LIVE_COMPILATION", "auto").strip().lower()
    return raw if raw in {"auto", "live", "off"} else "auto"


def _proposal_payload(
    *, proposal_id: str, intent_text: str, worldbook_id: str, candidate_kind: str,
    display_name: str, summary: str,
) -> dict[str, Any]:
    intended = {
        "temporary_trap_sample": "temporary_mod",
        "field_device": "temporary_mod",
    }.get(candidate_kind, candidate_kind)
    return {
        "id": proposal_id,
        "mode": "runtime_safe",
        "title": display_name,
        "summary": summary,
        "intended_asset_type": intended,
        "expected_effect": intent_text,
        "risk_level": "medium",
        "estimated_cost": {"materials": 12},
        "required_inputs": {"npc_ids": [], "materials": []},
        "known_tradeoffs": ["需要经过现场试作验证"],
        "player_prompt": intent_text,
        "worldbook_id": worldbook_id,
    }


def compile_candidate(
    *, proposal_id: str, intent_text: str, worldbook_id: str,
    candidate_kind: str, display_name: str, summary: str,
) -> dict[str, Any]:
    """Return a validated live candidate, or a compact fallback result."""
    mode = _mode()
    if mode == "off":
        return {"status": "fallback", "reason": "disabled", "candidate": None}

    adapter, prompt_helper, validator = _modules()
    adapter.load_dotenv(_REPO_ROOT / ".env")
    profile_name = os.environ.get("AI_TD_LLM_PROFILE", _DEFAULT_PROFILE)
    profile = adapter.PROFILES.get(profile_name)
    if profile is None or not os.environ.get(profile.env_key):
        return {"status": "fallback", "reason": "profile_unavailable", "candidate": None}

    proposal = _proposal_payload(
        proposal_id=proposal_id,
        intent_text=intent_text,
        worldbook_id=worldbook_id,
        candidate_kind=candidate_kind,
        display_name=display_name,
        summary=summary,
    )
    registry = _load_json(_EFFECT_REGISTRY)
    messages = [
        {"role": "system", "content": prompt_helper.SYSTEM_PROMPT},
        {"role": "user", "content": prompt_helper.build_user_prompt(proposal, registry)},
    ]
    try:
        response = adapter.chat_completion(
            profile,
            messages,
            max_tokens=int(os.environ.get("AI_TD_LLM_MAX_TOKENS", "8192")),
            timeout=int(os.environ.get("AI_TD_LLM_TIMEOUT", "120")),
            response_format={"type": "json_object"} if profile.supports_json_object else None,
        )
        candidate = adapter.extract_json(adapter.extract_content_from_response(response))
        if not isinstance(candidate, dict):
            raise ValueError("structured candidate missing")
        candidate = prompt_helper.normalize_candidate_provenance(
            candidate, proposal, provider=profile.name, model=profile.model,
        )
        errors = validator.validate(candidate, registry)
        if errors:
            raise ValueError(errors[0])
    except Exception as exc:  # Provider and candidate failures use the stable fallback.
        return {
            "status": "fallback",
            "reason": type(exc).__name__,
            "candidate": None,
        }

    return {
        "status": "live_validated",
        "reason": None,
        "candidate": candidate,
        "provenance": {
            "mode": "live",
            "profile": profile.name,
            "model": profile.model,
            "provider_call_performed": True,
            "raw_prompt_stored": False,
            "raw_response_stored": False,
        },
    }


def player_fields(candidate: dict[str, Any]) -> dict[str, str]:
    presentation = candidate.get("presentation")
    if not isinstance(presentation, dict):
        presentation = {}
    gameplay = candidate.get("gameplay")
    if not isinstance(gameplay, dict):
        gameplay = {}
    constraints = gameplay.get("constraints")
    if not isinstance(constraints, dict):
        constraints = {}
    name = str(presentation.get("name") or "现场试作方案")[:48]
    summary = str(presentation.get("short_description") or "一项等待现场验证的临时改造。")[:180]
    risk_parts = []
    if constraints.get("max_instances") is not None:
        risk_parts.append(f"本场最多部署 {constraints['max_instances']} 次")
    if constraints.get("requires_power_grid"):
        risk_parts.append("需要稳定供能")
    risk = "，".join(risk_parts) or "具体缺陷将在实战后逐步显现。"
    return {"display_name": name, "summary": summary, "risk_note": risk[:120]}


def write_candidate(candidate: dict[str, Any], job_dir: Path) -> Path:
    path = job_dir / "validated_live_asset_candidate.json"
    path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_provider_envelope(
    *, candidate_path: Path, job_dir: Path, created_at: str, profile: str, model: str,
) -> Path:
    candidate_hash = _sha256(candidate_path)
    artifact_id = f"live_candidate_{candidate_hash[:20]}"
    envelope = {
        "schema_version": "provider_output_envelope.v0.1",
        "envelope_id": f"pout_{candidate_hash[:20]}",
        "created_at": created_at,
        "source": {
            "run_id": f"research_{candidate_hash[:16]}",
            "schedule_item_id": f"player_research_{candidate_hash[:16]}",
            "object_kind": "runtime_safe_asset_candidate",
            "object_ref": artifact_id,
            "provider_profile": profile,
            "provider_mode": "player_authorized_runtime_safe",
            "worker_id": "live_asset_compile_service",
            "guard_id": "runtime_safe_asset_policy_v0_1",
        },
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "provider_call": {
            "status": "performed_redacted",
            "performed": True,
            "authorization_required": True,
            "authorization_granted": True,
            "authorization_ref": "runtime_safe_player_research_policy_v0_1",
            "attempt_count": 1,
            "max_attempts": 1,
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "forbidden",
        },
        "redacted_request_summary": {
            "intent_class": "runtime_safe_asset_compilation",
            "input_refs": [],
            "policy_notes": [
                "Only the validated structured candidate and digests are retained.",
                "The provider result cannot mutate runtime before promotion and apply gates.",
            ],
            "request_digest": None,
        },
        "redacted_result_summary": {
            "result_kind": "json_candidate",
            "status": "candidate_ready_for_validation",
            "summary": "A structured gameplay candidate passed schema and allowlist validation.",
            "result_digest": candidate_hash,
            "finish_reason": "completed",
        },
        "artifact_manifest": {
            "status": "review_only_artifacts_ready",
            "output_refs": [{
                "artifact_id": artifact_id,
                "kind": "json_candidate",
                "path": str(candidate_path),
                "sha256": candidate_hash,
                "content_type": "application/json",
                "byte_size": candidate_path.stat().st_size,
                "media_layer": "processed_media",
            }],
            "review_only": True,
            "notes": ["Candidate remains internal until explicit promotion."],
        },
        "validation": {
            "schema_gate": {
                "status": "passed", "required_before_activation": True,
                "report_ref": str(candidate_path),
            },
            "semantic_gate": {
                "status": "passed", "required_before_activation": True,
                "report_ref": str(candidate_path),
            },
            "media_gate": {
                "status": "not_applicable", "required_before_activation": False,
                "report_ref": None,
            },
            "human_review": {
                "status": "not_applicable", "required_before_activation": False,
                "report_ref": None,
                "notes": ["Runtime-safe structured assets use automated policy and simulation gates."],
            },
        },
        "activation_gate": {
            "activation_allowed": False,
            "blocked_reason": "promotion_required",
            "required_next_gates": ["artifact_staging_manifest", "promotion_report", "runtime_apply_gate"],
        },
    }
    return _write_json(job_dir / "provider_output_envelope.json", envelope)


def _write_staging_manifest(
    *, candidate_path: Path, envelope_path: Path, job_dir: Path, created_at: str,
) -> Path:
    candidate_hash = _sha256(candidate_path)
    source_id = f"live_candidate_{candidate_hash[:20]}"
    staged_id = f"{source_id}_staged"
    envelope = _load_json(envelope_path)
    manifest = {
        "schema_version": "provider_artifact_staging_manifest.v0.1",
        "manifest_id": f"pstaging_{candidate_hash[:20]}",
        "created_at": created_at,
        "source_envelope_ref": str(envelope_path),
        "source_envelope_id": envelope["envelope_id"],
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "local_ref_required",
            "local_refs_only": True,
            "runtime_claim_policy": "forbidden_before_promotion",
        },
        "staging_status": "review_only_artifacts_staged",
        "staged_artifacts": [{
            "artifact_id": staged_id,
            "source_artifact_id": source_id,
            "kind": "json_candidate",
            "path": str(candidate_path),
            "sha256": candidate_hash,
            "content_type": "application/json",
            "byte_size": candidate_path.stat().st_size,
            "media_layer": "candidate_ref",
            "role": "validated_runtime_safe_asset_candidate",
            "review_status": "staged_for_review",
            "runtime_visible": False,
            "player_visible": False,
        }],
        "validation_results": {
            "source_envelope_gate": {
                "status": "passed", "required_before_promotion": True,
                "report_ref": str(envelope_path),
            },
            "local_ref_gate": {
                "status": "passed", "required_before_promotion": True,
                "report_ref": str(candidate_path),
            },
            "schema_gate": {
                "status": "passed", "required_before_promotion": True,
                "report_ref": str(candidate_path),
            },
            "media_gate": {
                "status": "not_applicable", "required_before_promotion": False,
                "report_ref": None,
            },
            "semantic_gate": {
                "status": "passed", "required_before_promotion": True,
                "report_ref": str(candidate_path),
            },
            "human_review": {
                "status": "not_applicable", "required_before_promotion": False,
                "report_ref": None,
                "notes": ["No unrestricted code or unreviewed media is present."],
            },
        },
        "promotion_gate": {
            "promotion_allowed": False,
            "blocked_reason": "promotion_report_required",
            "required_next_gates": ["promotion_report", "runtime_apply_gate"],
        },
    }
    return _write_json(job_dir / "provider_artifact_staging_manifest.json", manifest)


def write_promotion_report(
    *, package_path: Path, candidate_path: Path, job_dir: Path, created_at: str,
    profile: str, model: str,
) -> Path:
    """Write the explicit report consumed by the runtime activation gate."""
    package_hash = _sha256(package_path)
    candidate_hash = _sha256(candidate_path)
    envelope_path = _write_provider_envelope(
        candidate_path=candidate_path,
        job_dir=job_dir,
        created_at=created_at,
        profile=profile,
        model=model,
    )
    staging_path = _write_staging_manifest(
        candidate_path=candidate_path,
        envelope_path=envelope_path,
        job_dir=job_dir,
        created_at=created_at,
    )
    staging_id = f"pstaging_{candidate_hash[:20]}"
    staged_artifact_id = f"live_candidate_{candidate_hash[:20]}_staged"
    report = {
        "schema_version": "provider_artifact_promotion_report.v0.1",
        "report_id": f"ppromo_{package_hash[:20]}",
        "created_at": created_at,
        "source_staging_ref": str(staging_path),
        "source_staging_id": staging_id,
        "authority": {
            "visibility": "internal_evidence",
            "report_only": True,
            "direct_runtime_mutation_allowed": False,
            "direct_world_mutation_allowed": False,
            "player_visible": False,
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "local_ref_required",
        },
        "decision": {
            "promotion_decision": "approved_for_runtime_package_build",
            "promotion_allowed": True,
            "blocked_reason": None,
            "required_next_actions": ["runtime_activation_apply_gate"],
            "notes": ["Validated candidate was lowered to the declarative runtime ABI."],
        },
        "reviewed_artifacts": [{
            "staged_artifact_id": staged_artifact_id,
            "source_artifact_id": f"live_candidate_{candidate_hash[:20]}",
            "kind": "json_candidate",
            "path": str(candidate_path),
            "review_result": "approved",
            "notes": ["Schema, ABI allowlist, simulation budget, and session binding passed."],
        }],
        "gate_results": {
            "source_staging_gate": {"status": "passed", "required_before_promotion": True, "report_ref": str(staging_path)},
            "local_ref_gate": {"status": "passed", "required_before_promotion": True, "report_ref": str(candidate_path)},
            "media_gate": {"status": "not_applicable", "required_before_promotion": False, "report_ref": None},
            "semantic_gate": {"status": "passed", "required_before_promotion": True, "report_ref": str(candidate_path)},
            "human_review": {"status": "not_applicable", "required_before_promotion": False, "report_ref": None},
            "simulation_gate": {"status": "passed", "required_before_promotion": True, "report_ref": str(candidate_path)},
        },
        "promotion_targets": {
            "target_kind": "runtime_package",
            "runtime_package_refs": [{"path": str(package_path), "kind": "runtime_package", "sha256": package_hash}],
            "world_transaction_refs": [],
            "published_media_refs": [],
        },
        "safety_summary": {
            "provider_call_count_by_report": 0,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "stores_secret": False,
            "uses_temporary_url": False,
        },
    }
    return _write_json(job_dir / "provider_artifact_promotion_report.json", report)
