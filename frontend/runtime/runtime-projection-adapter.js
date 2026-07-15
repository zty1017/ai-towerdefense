function asList(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function safeNumber(value, fallback, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return clamp(number, min, max);
}

function battleObjects(bundle) {
  return asList(asObject(asObject(bundle).capabilities).battle_objects);
}

function hotbarObjects(bundle) {
  return battleObjects(bundle).filter((item) =>
    asList(asObject(item && item.behavior_abi).ui_surfaces).includes("battle_hotbar"),
  );
}

function objectAvailableAtNode(object, nodeId) {
  const availableNodeIds = asList(object && object.available_node_ids);
  const sourceNodeId = asString(asObject(object && object.source_runtime_ref).node_id, "");
  if (sourceNodeId && nodeId && sourceNodeId !== nodeId) return false;
  return !availableNodeIds.length || !nodeId || availableNodeIds.includes(nodeId);
}

function activeSessionActivationIds(bundle) {
  return asList(asObject(asObject(bundle).runtime_selection).session_activation_ids)
    .map(String)
    .filter(Boolean);
}

function activationIdForObject(object) {
  return asString(asObject(object && object.source_runtime_ref).activation_id, "");
}

function runtimeHotbarObjects(bundle, battleConfig) {
  const config = asObject(battleConfig);
  const nodeId = asString(config.node_id, "");
  const objects = hotbarObjects(bundle).filter((object) => objectAvailableAtNode(object, nodeId));
  const activationIds = activeSessionActivationIds(bundle);
  const activationPriority = new Map(
    activationIds.map((activationId, index) => [activationId, index]),
  );
  const sessionActivated = objects
    .filter((object) => activationPriority.has(activationIdForObject(object)))
    .sort(
      (left, right) =>
        activationPriority.get(activationIdForObject(right)) -
        activationPriority.get(activationIdForObject(left)),
    );
  const fixtureScope = asObject(asObject(bundle).fixture_scope);
  if (fixtureScope.example_only !== true) {
    const activatedIds = new Set(sessionActivated.map((object) => object.object_id));
    return [
      ...sessionActivated,
      ...objects.filter((object) => !activatedIds.has(object.object_id)),
    ];
  }
  const allowedIds = new Set(asList(config.activated_runtime_object_ids).map(String));
  const activatedObjectIds = new Set(sessionActivated.map((object) => object.object_id));
  return [
    ...sessionActivated,
    ...objects.filter(
      (object) =>
        allowedIds.has(String(object.object_id || "")) &&
        !activatedObjectIds.has(object.object_id),
    ),
  ];
}

function projectionTools(projection) {
  if (Array.isArray(projection)) return projection;
  const data = asObject(projection);
  if (Array.isArray(data.tools)) return data.tools;
  if (Array.isArray(data.toolbar_tools)) return data.toolbar_tools;
  if (Array.isArray(asObject(data.battle).tools)) return data.battle.tools;
  if (Array.isArray(asObject(data.battle).toolbar_tools)) return data.battle.toolbar_tools;
  return [];
}

function hotbarObjectForTool(tool, objects) {
  return (
    objects.find(
      (item) =>
        item &&
        explicitHotbarId(item) === tool.id &&
        (item.asset_kind === tool.assetKind || tool.id === "sample"),
    ) ||
    objects.find(
      (item) =>
        item &&
        item.object_id === tool.objectId &&
        item.asset_kind === tool.assetKind,
    ) ||
    null
  );
}

function explicitHotbarId(object) {
  const ui = asObject(asObject(object && object.behavior_abi).ui);
  return (
    (object && (object.tool_id || object.hotbar_id)) ||
    ui.tool_id ||
    ui.hotbar_id ||
    null
  );
}

function toolDefsFromBattleConfig(battleConfig) {
  const config = asObject(battleConfig);
  const defs = [];

  const basicDefense = asObject(config.basic_defense);
  if (Object.keys(basicDefense).length) {
    defs.push({
      id: "basic",
      assetKind: "tower_blueprint",
      objectId: asString(basicDefense.runtime_object_id || basicDefense.stable_internal_id, ""),
      name: asString(basicDefense.display_name, "基础防御"),
      cooldownMs: 3600,
      mediaKey: "basic",
      meta(battle, behaviorAbi) {
        return [costLabel(behaviorAbi, "材料 20"), `剩余 ${battle.basicUses ?? 0}`];
      },
      locked() {
        return false;
      },
    });
  }

  const sampleAsset = asObject(config.sample_asset);
  if (Object.keys(sampleAsset).length) {
    defs.push({
      id: "sample",
      assetKind: asString(sampleAsset.asset_kind, "temporary_trap_sample"),
      objectId: asString(sampleAsset.runtime_object_id || sampleAsset.stable_internal_id, ""),
      name: asString(sampleAsset.display_name, "临时装置"),
      cooldownMs: 1800,
      mediaKey: "sample",
      behaviorAbi: asObject(sampleAsset.runtime_behavior_abi),
      meta(battle, behaviorAbi) {
        return [
          battle.sampleDelivered ? `剩余 ${battle.sampleUses ?? 0}` : "封装中",
          asString(
            sampleAsset.toolbar_effect_label,
            effectSummary(behaviorAbi, "临时效果"),
          ),
        ];
      },
      locked(battle) {
        return !battle.sampleDelivered;
      },
    });
  }

  const supportAsset = asObject(config.support_asset);
  if (Object.keys(supportAsset).length) {
    defs.push({
      id: "support",
      assetKind: "support_item",
      objectId: asString(supportAsset.runtime_object_id || supportAsset.stable_internal_id, ""),
      name: asString(supportAsset.display_name, "支援装置"),
      cooldownMs: 9000,
      mediaKey: "support",
      meta(battle, behaviorAbi) {
        return [costLabel(behaviorAbi, "材料 15"), `剩余 ${battle.supportUses ?? 0}`];
      },
      locked() {
        return false;
      },
    });
  }

  return defs;
}

function asString(value, fallback = "") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function defaultToolForRuntimeObject(object, toolDefs) {
  return (
    toolDefs.find((tool) => tool.objectId && tool.objectId === object.object_id) ||
    toolDefs.find(
      (tool) =>
        explicitHotbarId(object) === tool.id &&
        (object.asset_kind === tool.assetKind || tool.id === "sample"),
    ) ||
    null
  );
}

function toolIdForRuntimeObject(object) {
  const ui = asObject(asObject(object.behavior_abi).ui);
  const raw = (
    object.tool_id ||
    object.hotbar_id ||
    ui.tool_id ||
    ui.hotbar_id ||
    object.object_id ||
    object.asset_kind ||
    "runtime_tool"
  );
  const safe = String(raw).replace(/[^A-Za-z0-9_:-]/g, "_").slice(0, 96);
  return safe || "runtime_tool";
}

function allocateUniqueToolId(baseId, usedIds) {
  if (!usedIds.has(baseId)) {
    usedIds.add(baseId);
    return baseId;
  }
  let suffix = 2;
  let uniqueId = "";
  do {
    const suffixText = `_${suffix}`;
    uniqueId = `${baseId.slice(0, Math.max(1, 96 - suffixText.length))}${suffixText}`;
    suffix += 1;
  } while (usedIds.has(uniqueId));
  usedIds.add(uniqueId);
  return uniqueId;
}

function cooldownMsFromAbi(behaviorAbi, fallback) {
  const cooldown = asObject(asObject(behaviorAbi).cooldown);
  const milliseconds = Number(cooldown.milliseconds ?? cooldown.ms);
  if (Number.isFinite(milliseconds) && milliseconds >= 0) return milliseconds;
  const seconds = Number(cooldown.seconds);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;
  return fallback;
}

function costFromAbi(behaviorAbi) {
  return asObject(asObject(behaviorAbi).cost);
}

function resourceName(resource) {
  const key = String(resource || "").toLowerCase();
  if (key === "materials" || key === "material") return "材料";
  if (key === "light" || key === "lamp_light") return "灯火";
  if (key === "power" || key === "electricity") return "电力";
  return resource ? String(resource) : "材料";
}

function costLabel(behaviorAbi, fallback) {
  const cost = costFromAbi(behaviorAbi);
  const amount = safeNumber(cost.amount, NaN, 0, 999);
  if (!Number.isFinite(amount)) return fallback;
  return `${resourceName(cost.resource)} ${amount}`;
}

function effectSummary(behaviorAbi, fallback) {
  const first = asList(asObject(behaviorAbi).effect_blocks)[0];
  const kind = String((first && first.kind) || "");
  if (kind === "slow") return "减速";
  if (kind === "damage") return Number(first.radius_cells) > 0 ? "范围打击" : "打击";
  if (kind === "aura") return "光环";
  if (kind === "reveal") return "揭示";
  return fallback;
}

function mediaForTool(tool, media) {
  if (!media) return "";
  if (typeof media === "function") return media(tool.id, tool);
  if (typeof media.getToolImage === "function") return media.getToolImage(tool.id, tool) || "";
  const images = asObject(media.toolImages);
  return media[tool.mediaKey] || media[`${tool.mediaKey}Img`] || images[tool.id] || "";
}

function buildTool(tool, battle, runtimeObjects, media) {
  const runtimeObject = hotbarObjectForTool(tool, runtimeObjects);
  return buildToolFromRuntimeObject({
    tool,
    runtimeObject,
    battle,
    media,
    runtimeOnly: false,
  });
}

function dynamicToolFromRuntimeObject(runtimeObject) {
  return {
    id: toolIdForRuntimeObject(runtimeObject),
    assetKind: runtimeObject.asset_kind || "support_item",
    objectId: runtimeObject.object_id || toolIdForRuntimeObject(runtimeObject),
    name: runtimeObject.display_name || runtimeObject.object_id || "临时装置",
    cooldownMs: 1000,
    mediaKey: runtimeObject.object_id || runtimeObject.asset_kind || "runtime_tool",
    meta(_battle, behaviorAbi) {
      return [costLabel(behaviorAbi, "待装配"), effectSummary(behaviorAbi, "新装置")];
    },
    locked(_battle, behaviorAbi) {
      const lifecycle = asObject(runtimeObject.lifecycle);
      return lifecycle.deployable === false || !asList(behaviorAbi.ui_surfaces).includes("battle_hotbar");
    },
  };
}

function buildToolFromRuntimeObject({ tool, runtimeObject, battle, media, runtimeOnly }) {
  const behaviorAbi = runtimeObject
    ? asObject(runtimeObject.behavior_abi)
    : asObject(tool.behaviorAbi);
  const mediaRefs = runtimeObject ? asObject(runtimeObject.media_refs) : {};
  const directIcon = asObject(mediaRefs.icon).url || "";
  return {
    id: tool.id,
    name: (runtimeObject && runtimeObject.display_name) || tool.name,
    img: directIcon || mediaForTool(tool, media),
    meta: tool.meta(battle, behaviorAbi),
    locked: tool.locked(battle, behaviorAbi),
    assetKind: (runtimeObject && runtimeObject.asset_kind) || tool.assetKind,
    objectId: (runtimeObject && runtimeObject.object_id) || tool.objectId,
    behaviorAbi,
    mediaRefs,
    cost: costFromAbi(behaviorAbi),
    cooldownMs: cooldownMsFromAbi(behaviorAbi, tool.cooldownMs),
    runtimeOnly: Boolean(runtimeOnly),
  };
}

export function findBattleToolProjection(toolId, projection) {
  return projectionTools(projection).find((tool) => tool && tool.id === toolId) || null;
}

const NEUTRAL_TOOL_ASSET_KINDS = {
  basic: "tower_blueprint",
  sample: "temporary_trap_sample",
  support: "support_item",
};

export function assetKindForToolId(toolId, projection) {
  const projected = findBattleToolProjection(toolId, projection);
  if (projected && projected.assetKind) return projected.assetKind;
  return NEUTRAL_TOOL_ASSET_KINDS[toolId] || "support_item";
}

export function buildBattleToolProjection({
  battle,
  battleConfig,
  activatedRuntimeBundle,
  media,
} = {}) {
  const battleState = asObject(battle);
  const toolDefs = toolDefsFromBattleConfig(battleConfig);
  const runtimeObjects = runtimeHotbarObjects(activatedRuntimeBundle, battleConfig);
  const defaults = toolDefs.map((tool) =>
    buildTool(tool, battleState, runtimeObjects, media),
  );
  const usedObjectIds = new Set(defaults.map((tool) => tool.objectId).filter(Boolean));
  const usedToolIds = new Set(defaults.map((tool) => tool.id));
  const dynamicTools = runtimeObjects
    .filter((object) => object && object.object_id && !usedObjectIds.has(object.object_id))
    .filter((object) => !defaultToolForRuntimeObject(object, toolDefs))
    .map((object) => {
      const tool = dynamicToolFromRuntimeObject(object);
      tool.id = allocateUniqueToolId(tool.id, usedToolIds);
      return buildToolFromRuntimeObject({
        tool,
        runtimeObject: object,
        battle: battleState,
        media,
        runtimeOnly: true,
      });
    });
  return [...defaults, ...dynamicTools];
}
