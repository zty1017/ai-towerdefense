function setToast(setBattleToast, text) {
  if (typeof setBattleToast === "function") setBattleToast(text);
}

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

function toolCostAmount(tool, fallback) {
  return safeNumber(((tool || {}).cost || {}).amount, fallback, 0, 999);
}

function toolCooldownMs(tool, fallback) {
  return safeNumber((tool || {}).cooldownMs, fallback, 0, 120000);
}

function behaviorAbi(tool) {
  return asObject((tool || {}).behaviorAbi);
}

function effectBlocks(tool) {
  return asList(behaviorAbi(tool).effect_blocks);
}

function placementMode(tool) {
  return String(asObject(behaviorAbi(tool).placement).mode || "");
}

function isFreePointTool(tool) {
  return ["free_point", "area_point"].includes(placementMode(tool));
}

function runtimeActionKind(tool) {
  const assetKind = String((tool || {}).assetKind || "");
  const mode = placementMode(tool);
  if (assetKind === "support_item" || isFreePointTool(tool)) return "support";
  if (assetKind === "tower_blueprint") return "defense";
  if (
    assetKind === "temporary_trap_sample" ||
    assetKind.includes("trap") ||
    assetKind.includes("device") ||
    ["path_area", "path_adjacent_or_slot"].includes(mode)
  ) {
    return "trap";
  }
  return "support";
}

function resourceField(resource) {
  const key = String(resource || "").toLowerCase();
  if (["power", "electricity", "light", "lamp_light"].includes(key)) return "power";
  return "resources";
}

function toolCost(tool, fallbackAmount = 0, fallbackResource = "materials") {
  const cost = asObject((tool || {}).cost);
  return {
    field: resourceField(cost.resource || fallbackResource),
    amount: safeNumber(cost.amount, fallbackAmount, 0, 999),
  };
}

function canPayCost(battle, tool, fallbackAmount = 0, fallbackResource = "materials") {
  const cost = toolCost(tool, fallbackAmount, fallbackResource);
  return Number(battle[cost.field] || 0) >= cost.amount;
}

function spendCost(battle, tool, fallbackAmount = 0, fallbackResource = "materials") {
  const cost = toolCost(tool, fallbackAmount, fallbackResource);
  battle[cost.field] = Number(battle[cost.field] || 0) - cost.amount;
  return cost;
}

function cooldownKey(tool, fallback) {
  return (tool && tool.id) || fallback;
}

function cooldownReady(battle, tool, fallback) {
  return Number((battle.cooldowns || {})[cooldownKey(tool, fallback)] || 0) <= 0;
}

function setCooldown(battle, tool, fallbackKey, fallbackMs) {
  const key = cooldownKey(tool, fallbackKey);
  battle.cooldowns[key] = toolCooldownMs(tool, fallbackMs);
}

function firstEffectOf(tool, kind) {
  return effectBlocks(tool).find((effect) => effect && effect.kind === kind) || null;
}

function normalizedDamage(tool, fallback = 1) {
  const damage = firstEffectOf(tool, "damage");
  const amount = safeNumber(damage && damage.amount, fallback * 8, 0, 40);
  return clamp(Math.max(1, Math.ceil(amount / 8)), 1, 5);
}

function slowDurationMs(tool, fallback = 1800) {
  const slow = firstEffectOf(tool, "slow");
  return safeNumber(slow && slow.duration_ms, fallback, 0, 10000);
}

function trapActiveDurationMs(tool, fallback = 7800) {
  const explicit = safeNumber(behaviorAbi(tool).active_duration_ms, 0, 0, 15000);
  if (explicit > 0) return explicit;
  const aura = firstEffectOf(tool, "aura");
  const auraDuration = safeNumber(aura && aura.duration_ms, 0, 0, 15000);
  if (auraDuration > 0) return auraDuration;
  return fallback;
}

function targetRadius(tool, fallback = 1.6) {
  const targeting = asObject(behaviorAbi(tool).targeting);
  return safeNumber(targeting.radius_cells || targeting.range_cells, fallback, 0.3, 5);
}

function effectColor(tool, fallback) {
  const kind = String((effectBlocks(tool)[0] || {}).kind || "");
  if (kind === "damage") return "#ffd37a";
  if (kind === "slow") return "#9edcff";
  if (kind === "aura") return "#8fcf83";
  if (kind === "reveal") return "#c8ffd6";
  return fallback;
}

function pushDeployedAssetId(battle, tool, fallback) {
  const id = (tool && (tool.objectId || tool.id)) || fallback;
  if (!Array.isArray(battle.deployedAssetIds)) battle.deployedAssetIds = [];
  if (id) battle.deployedAssetIds.push(id);
}

function displayName(tool, fallback) {
  return (tool && tool.name) || fallback;
}

export function toolUnavailableText(tool) {
  const id = typeof tool === "string" ? tool : (tool || {}).id;
  if (id === "basic") return "材料或冷却不足";
  if (id === "sample") return "样品尚未送达";
  if (id === "support") return "支援尚未就绪";
  return "暂不可用";
}

export function placeBasicDefense({
  battle,
  cell,
  tool,
  canPlaceToolAt,
  addEffect,
  setBattleToast,
} = {}) {
  if (!battle || !cell) return false;
  const cost = toolCostAmount(tool, 20);
  if (
    battle.basicUses <= 0 ||
    !canPayCost(battle, tool, cost, "materials") ||
    !cooldownReady(battle, tool, "basic")
  ) {
    setToast(setBattleToast, "材料或冷却不足");
    return false;
  }
  if (typeof canPlaceToolAt !== "function" || !canPlaceToolAt("basic", cell)) {
    setToast(setBattleToast, "灯栏需要放在可部署基座");
    return false;
  }
  battle.basicUses -= 1;
  spendCost(battle, tool, cost, "materials");
  setCooldown(battle, tool, "basic", 3600);
  battle.defenses.push({
    key: `${cell.x},${cell.y}`,
    x: cell.x,
    y: cell.y,
    hp: 1,
    until:
      battle.elapsedMs +
      Math.max(10000, ((battle.config || {}).basic_defense || {}).duration_ms * 2 || 10000),
    shotAt: 0,
    name: displayName(tool, "基础灯栏"),
    assetKind: "tower_blueprint",
    objectId: (tool && tool.objectId) || "basic_lantern_tower_001",
    behaviorAbi: behaviorAbi(tool),
    mediaRefs: (tool && tool.mediaRefs) || {},
    range: targetRadius(tool, 2.6),
    damage: normalizedDamage(tool, 1),
    attackIntervalMs: 760,
    attackColor: effectColor(tool, "#ffd37a"),
  });
  pushDeployedAssetId(battle, tool, "basic_lantern_barricade");
  if (typeof addEffect === "function") addEffect("ring", cell.x, cell.y, effectColor(tool, "#ffd37a"), 820);
  setToast(setBattleToast, "基础灯栏已立起");
  return true;
}

export function placeSampleTrap({
  battle,
  cell,
  tool,
  canPlaceToolAt,
  addEffect,
  setBattleToast,
} = {}) {
  if (!battle || !cell) return false;
  if (!battle.sampleDelivered || battle.sampleUses <= 0 || battle.cooldowns.sample > 0) {
    setToast(setBattleToast, "样品尚不可用");
    return false;
  }
  if (typeof canPlaceToolAt !== "function" || !canPlaceToolAt("sample", cell)) {
    setToast(setBattleToast, "绊索需要放在可部署基座");
    return false;
  }
  battle.sampleUses -= 1;
  setCooldown(battle, tool, "sample", 1800);
  battle.traps.push({
    key: `${cell.x},${cell.y}`,
    x: cell.x,
    y: cell.y,
    armed: true,
    activeUntil: 0,
    expired: false,
    name: displayName(tool, "折光绊索"),
    assetKind: "temporary_trap_sample",
    objectId: (tool && tool.objectId) || "sample_trap_7f3a",
    behaviorAbi: behaviorAbi(tool),
    mediaRefs: (tool && tool.mediaRefs) || {},
    radius: targetRadius(tool, 1.65),
    slowDurationMs: slowDurationMs(tool, 900),
    activeDurationMs: trapActiveDurationMs(tool, 7800),
    color: effectColor(tool, "#9edcff"),
  });
  pushDeployedAssetId(battle, tool, "sample_trap_7f3a");
  if (typeof addEffect === "function") addEffect("ring", cell.x, cell.y, effectColor(tool, "#9edcff"), 1000);
  setToast(setBattleToast, `${displayName(tool, "折光绊索")}已部署`);
  return true;
}

export function useSupportPulse({
  battle,
  cell,
  tool,
  addEffect,
  addFloating,
  setBattleToast,
} = {}) {
  if (!battle || !cell) return false;
  const cost = toolCostAmount(tool, 15);
  if (
    battle.supportUses <= 0 ||
    !cooldownReady(battle, tool, "support") ||
    !canPayCost(battle, tool, cost, "materials")
  ) {
    setToast(setBattleToast, "支援尚未就绪");
    return false;
  }
  battle.supportUses -= 1;
  spendCost(battle, tool, cost, "materials");
  setCooldown(battle, tool, "support", 9000);
  for (const enemy of battle.enemies || []) {
    const dist = Math.hypot(enemy.x - cell.x, enemy.y - cell.y);
    if (dist < targetRadius(tool, 2.1)) {
      enemy.hp -= normalizedDamage(tool, 1);
      enemy.slowUntil = Math.max(enemy.slowUntil, battle.elapsedMs + slowDurationMs(tool, 2600));
    }
  }
  pushDeployedAssetId(battle, tool, "guardian_support_001");
  if (typeof addEffect === "function") addEffect("ring", cell.x, cell.y, effectColor(tool, "#8fcf83"), 1200, 1.6);
  if (typeof addFloating === "function") addFloating(cell.x, cell.y, displayName(tool, "守灯支援"), "#c8ffd6");
  setToast(setBattleToast, "守灯支援已落点");
  return true;
}

export function canPreviewRuntimeToolAt({ tool, cell, canPlaceToolAt } = {}) {
  if (!tool || !cell) return false;
  if (tool.locked) return false;
  if (runtimeActionKind(tool) === "support") return true;
  return typeof canPlaceToolAt === "function" ? canPlaceToolAt(tool.id, cell) : false;
}

export function deployRuntimeTool({
  battle,
  cell,
  tool,
  canPlaceToolAt,
  addEffect,
  addFloating,
  setBattleToast,
} = {}) {
  if (!battle || !cell || !tool) return false;
  if (tool.locked) {
    setToast(setBattleToast, "尚未装配完成");
    return false;
  }
  const deliveredSample = tool.id === "sample";
  if (deliveredSample && (!battle.sampleDelivered || Number(battle.sampleUses || 0) <= 0)) {
    setToast(setBattleToast, "样品尚不可用");
    return false;
  }
  const key = cooldownKey(tool, tool.id);
  const fallbackCost = runtimeActionKind(tool) === "support" ? 0 : 10;
  if (
    !cooldownReady(battle, tool, key) ||
    (!deliveredSample && !canPayCost(battle, tool, fallbackCost, "materials"))
  ) {
    setToast(setBattleToast, "材料或冷却不足");
    return false;
  }
  const actionKind = runtimeActionKind(tool);
  if (actionKind !== "support" && !canPreviewRuntimeToolAt({ tool, cell, canPlaceToolAt })) {
    setToast(setBattleToast, "需要放在可部署位置");
    return false;
  }

  if (!deliveredSample) spendCost(battle, tool, fallbackCost, "materials");
  if (deliveredSample) battle.sampleUses -= 1;
  setCooldown(battle, tool, key, 1000);
  pushDeployedAssetId(battle, tool, tool.id);

  if (actionKind === "defense") {
    battle.defenses.push({
      key: `${cell.x},${cell.y}`,
      x: cell.x,
      y: cell.y,
      hp: 1,
      until: battle.elapsedMs + 14000,
      shotAt: 0,
      name: displayName(tool, "临时塔"),
      assetKind: tool.assetKind,
      objectId: tool.objectId || tool.id,
      runtimeToolId: tool.id,
      behaviorAbi: behaviorAbi(tool),
      mediaRefs: tool.mediaRefs || {},
      range: targetRadius(tool, 2.6),
      damage: normalizedDamage(tool, 1),
      attackIntervalMs: 760,
      attackColor: effectColor(tool, "#ffd37a"),
    });
    if (typeof addEffect === "function") addEffect("ring", cell.x, cell.y, effectColor(tool, "#ffd37a"), 900);
    setToast(setBattleToast, `${displayName(tool, "临时塔")}已部署`);
    return true;
  }

  if (actionKind === "trap") {
    battle.traps.push({
      key: `${cell.x},${cell.y}`,
      x: cell.x,
      y: cell.y,
      armed: true,
      activeUntil: 0,
      expired: false,
      name: displayName(tool, "临时装置"),
      assetKind: tool.assetKind,
      objectId: tool.objectId || tool.id,
      runtimeToolId: tool.id,
      behaviorAbi: behaviorAbi(tool),
      mediaRefs: tool.mediaRefs || {},
      radius: targetRadius(tool, 1.65),
      slowDurationMs: slowDurationMs(tool, 900),
      activeDurationMs: trapActiveDurationMs(tool, 7800),
      color: effectColor(tool, "#9edcff"),
    });
    if (typeof addEffect === "function") addEffect("ring", cell.x, cell.y, effectColor(tool, "#9edcff"), 1000);
    setToast(setBattleToast, `${displayName(tool, "临时装置")}已部署`);
    return true;
  }

  const radius = targetRadius(tool, 2);
  for (const enemy of battle.enemies || []) {
    if (Math.hypot(enemy.x - cell.x, enemy.y - cell.y) >= radius) continue;
    if (firstEffectOf(tool, "damage")) enemy.hp -= normalizedDamage(tool, 1);
    if (firstEffectOf(tool, "slow") || firstEffectOf(tool, "aura")) {
      enemy.slowUntil = Math.max(enemy.slowUntil, battle.elapsedMs + slowDurationMs(tool, 2200));
    }
  }
  if (typeof addEffect === "function") addEffect("ring", cell.x, cell.y, effectColor(tool, "#8fcf83"), 1100, Math.max(1, radius / 1.4));
  if (typeof addFloating === "function") addFloating(cell.x, cell.y, displayName(tool, "临时支援"), "#c8ffd6");
  setToast(setBattleToast, `${displayName(tool, "临时支援")}已释放`);
  return true;
}
