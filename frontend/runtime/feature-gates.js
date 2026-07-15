const ACTIVE_RECEIPT_STATUSES = new Set(["activated", "active", "activated_fixture"]);
const BLOCKED_STATUSES = new Set(["disabled", "blocked", "quarantined", "rolled_back"]);
const FEATURE_SNAPSHOT_SCHEMA_VERSION = "frontend_feature_snapshot.v0.1";
const SURFACE_CONTRIBUTION_SCHEMA_VERSION = "frontend_surface_contribution.v0.1";
const FEATURE_SURFACES = {
  strategic_map: "strategic_map",
  workshop: "prototype_workshop",
  battle: "battle_canvas",
  narrative: "dialogue_modal",
  settlement: "settlement_panel",
};

const SURFACE_KIND_SLOTS = {
  strategic_map: {
    objective_card: new Set(["objective_overlay"]),
    node_participant: new Set(["node_panel"]),
    node_badge: new Set(["node_marker", "node_panel"]),
    map_notice: new Set(["objective_overlay", "node_panel"]),
  },
  prototype_workshop: {
    proposal_hint: new Set(["proposal_panel"]),
    participant_notice: new Set(["participant_panel"]),
    material_notice: new Set(["material_panel"]),
  },
  dialogue_modal: {
    narrative_beat: new Set(["dialogue_queue"]),
  },
  settlement_panel: {
    settlement_note: new Set(["result_summary", "world_delta"]),
  },
};

const PAYLOAD_FIELDS = {
  objective_card: ["title", "summary", "status", "node_id"],
  node_participant: ["npc_id", "display_name", "summary", "node_id", "gameplay_roles"],
  node_badge: ["node_id", "label", "tone"],
  map_notice: ["title", "summary", "severity", "node_id"],
  proposal_hint: ["title", "summary", "node_id"],
  participant_notice: ["npc_id", "display_name", "summary", "node_id"],
  material_notice: ["material_id", "display_name", "summary", "quantity"],
  narrative_beat: [
    "beat_id",
    "speaker_id",
    "speaker_name",
    "portrait_asset_id",
    "text",
    "node_id",
  ],
  settlement_note: ["title", "summary", "node_id"],
};

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function safeId(value, fallback = "") {
  const normalized = String(value || "").replace(/[^A-Za-z0-9_.:-]/g, "_").slice(0, 128);
  return normalized || fallback;
}

function safeText(value, maxLength = 360) {
  return String(value ?? "").replace(/[<>]/g, "").slice(0, maxLength);
}

function normalizePayload(kind, payload) {
  const source = asObject(payload);
  const normalized = {};
  for (const field of PAYLOAD_FIELDS[kind] || []) {
    if (!(field in source)) continue;
    if (field === "gameplay_roles") {
      normalized[field] = asList(source[field]).slice(0, 8).map((item) => safeId(item)).filter(Boolean);
    } else if (field === "quantity") {
      const value = Number(source[field]);
      normalized[field] = Number.isFinite(value) ? Math.max(0, Math.min(999999, value)) : 0;
    } else if (field.endsWith("_id") || field === "status" || field === "tone" || field === "severity") {
      normalized[field] = safeId(source[field]);
    } else {
      normalized[field] = safeText(source[field]);
    }
  }
  return normalized;
}

function normalizeContribution(item, fallbackFeatureId, fallbackSurface, index) {
  const source = asObject(item);
  if (source.schema_version !== SURFACE_CONTRIBUTION_SCHEMA_VERSION) return null;
  if (safeId(source.feature_id) !== safeId(fallbackFeatureId)) return null;
  const surface = safeId(source.surface || fallbackSurface);
  if (surface !== safeId(fallbackSurface)) return null;
  const kind = safeId(source.kind);
  const slot = safeId(source.slot);
  const allowedSlots = (SURFACE_KIND_SLOTS[surface] || {})[kind];
  if (!allowedSlots || !allowedSlots.has(slot)) return null;
  const visibility = safeId(source.visibility || "player_visible");
  if (!new Set(["player_visible", "public", "default"]).has(visibility)) return null;
  return {
    contributionId: safeId(source.contribution_id, `${fallbackFeatureId}_${kind}_${index + 1}`),
    featureId: safeId(source.feature_id || fallbackFeatureId),
    surface,
    kind,
    slot,
    priority: Math.max(-1000, Math.min(1000, Number(source.priority) || 0)),
    targetNodeId: safeId(source.target_node_id || asObject(source.payload).node_id),
    payload: normalizePayload(kind, source.payload),
  };
}

export function createFeatureGateRegistry({ getBundle } = {}) {
  if (typeof getBundle !== "function") {
    throw new TypeError("createFeatureGateRegistry requires getBundle");
  }

  function rawBundle() {
    return asObject(getBundle());
  }

  function evaluateBundle() {
    const bundle = rawBundle();
    const receipt = asObject(bundle.activation_receipt);
    const selection = asObject(bundle.runtime_selection);
    const quarantine = asObject(bundle.quarantine);
    const blockedStatuses = new Set([
      ...BLOCKED_STATUSES,
      ...asList(quarantine.status_values).map((item) => String(item)),
    ]);
    const observedStatuses = [bundle.status, receipt.status, selection.status, quarantine.status]
      .filter(Boolean)
      .map((item) => String(item));
    const reasons = [];
    if (!Object.keys(bundle).length) reasons.push("bundle_missing");
    if (bundle.frontend_role !== "consume_only") reasons.push("frontend_role_invalid");
    if (!ACTIVE_RECEIPT_STATUSES.has(String(receipt.status || ""))) reasons.push("activation_missing");
    if (receipt.runtime_safe_scan !== "passed") reasons.push("runtime_safe_scan_failed");
    if (selection.activation_applied !== true) reasons.push("selection_not_applied");
    if (observedStatuses.some((status) => blockedStatuses.has(status))) reasons.push("bundle_isolated");
    return { active: reasons.length === 0, reasons, bundle };
  }

  function rawFeatureSnapshot(featureId) {
    return asObject(asObject(rawBundle().feature_snapshots)[featureId]);
  }

  function gateEnabled(gateId) {
    const gate = asObject(asObject(rawBundle().feature_gates)[gateId]);
    return gate.enabled === true && !BLOCKED_STATUSES.has(String(gate.status || ""));
  }

  function featureEnabled(featureId) {
    if (!evaluateBundle().active) return false;
    const snapshot = rawFeatureSnapshot(featureId);
    if (!Object.keys(snapshot).length || BLOCKED_STATUSES.has(String(snapshot.status || ""))) return false;
    if (snapshot.schema_version !== FEATURE_SNAPSHOT_SCHEMA_VERSION) return false;
    if (safeId(snapshot.feature_id) !== safeId(featureId)) return false;
    if (snapshot.status !== "active") return false;
    if (safeId(snapshot.surface) !== FEATURE_SURFACES[featureId]) return false;
    const requiredGates = asList(snapshot.required_gates || snapshot.gate_ids);
    return requiredGates.every((gateId) => gateEnabled(gateId));
  }

  function featureSnapshot(featureId) {
    return featureEnabled(featureId) ? rawFeatureSnapshot(featureId) : null;
  }

  function activeBundleFor(featureId) {
    return featureEnabled(featureId) ? rawBundle() : null;
  }

  function capabilityList(key, featureId) {
    const bundle = activeBundleFor(featureId);
    return bundle ? asList(asObject(bundle.capabilities)[key]) : [];
  }

  function surfaceContributions(featureId, { surface = "", nodeId = "" } = {}) {
    const bundle = activeBundleFor(featureId);
    if (!bundle) return [];
    const snapshot = rawFeatureSnapshot(featureId);
    const snapshotSurface = safeId(snapshot.surface || surface);
    const candidates = [
      ...asList(snapshot.contributions),
      ...asList(asObject(bundle.capabilities).surface_contributions).filter(
        (item) => safeId(asObject(item).feature_id) === safeId(featureId),
      ),
    ];
    return candidates
      .map((item, index) => normalizeContribution(item, featureId, snapshotSurface || surface, index))
      .filter(Boolean)
      .filter((item) => !surface || item.surface === surface)
      .filter((item) => !item.targetNodeId || !nodeId || item.targetNodeId === safeId(nodeId))
      .sort((left, right) => right.priority - left.priority || left.contributionId.localeCompare(right.contributionId));
  }

  return {
    activeBundleFor,
    capabilityList,
    evaluateBundle,
    featureEnabled,
    featureSnapshot,
    gateEnabled,
    surfaceContributions,
  };
}
