function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function battleWaveLabel(battle) {
  const active = (battle.enemies || []).reduce(
    (max, enemy) => Math.max(max, enemy.waveIndex || 1),
    1,
  );
  const spawned = battle.spawned || 0;
  if (spawned <= 0) return "待接敌";
  return `${active}/${((battle.config || {}).waves || []).length}`;
}

export function sampleProgressMessage({ battle, battleConfig }) {
  const sample = (battleConfig || {}).sample_asset || {};
  const messages = sample.delivery_progress_messages || ["现场试作中。"];
  const ratio = clamp((battle.elapsedMs || 0) / (battle.sampleDeliveryMs || 1), 0, 0.99);
  return messages[Math.floor(ratio * messages.length)] || messages[0];
}

export function nextWaveText(battle) {
  const next = (battle.spawnSchedule || []).find((entry, index) => index >= battle.spawned);
  if (!next) return (battle.enemies || []).length ? "场上残敌" : "敌潮将尽";
  const delay = Math.max(0, Math.ceil((next.at - battle.elapsedMs) / 1000));
  return `${next.wave.display_name || "下一波"} · ${delay}s`;
}

export function toolCooldownFill({ battle, tool }) {
  const max = Number(tool && tool.cooldownMs) || 1;
  const current = Number(((battle || {}).cooldowns || {})[(tool || {}).id] || 0);
  return `${clamp(100 - Math.round((current / max) * 100), 0, 100)}%`;
}

export function buildBattleToolbarViewModel({ battle, tools, isToolReady }) {
  return (tools || []).map((tool) => {
    const ready = typeof isToolReady === "function" ? isToolReady(tool.id) : true;
    return {
      ...tool,
      ready,
      isSelected: battle.selectedTool === tool.id,
      isDragging: battle.draggingTool === tool.id,
      isLocked: Boolean(tool.locked || !ready),
      cooldownFill: toolCooldownFill({ battle, tool }),
    };
  });
}

const NEUTRAL_SAMPLE_DELIVERED_TEXT = "临时装置已送达。";
const NEUTRAL_ENVIRONMENT_TEXT = "当前节点战场条件尚未明确记录。";
const NEUTRAL_ENEMY_WEAKNESS = "观察敌潮走向，优先守住核心。";
const NEUTRAL_NPC_ADVICE = "在主路边缘部署防御，别让第一波直冲核心。";
const NEUTRAL_NPC_AVATAR_ALT = "节点联络人";

function asString(value, fallback = "") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function buildBattleHudViewModel({
  battle,
  objectives,
  sampleProgressText,
  nextWaveLabel,
  npcAvatarUrl,
  npcAvatarAlt,
  sampleDeliveredText,
  tacticalHints,
  toolbarTools,
}) {
  const coreTarget = (objectives || {}).core_target || {};
  const optionalTarget = ((objectives || {}).optional_targets || [])[0] || {};
  const hints = asObject(tacticalHints);
  const sampleText = asString(sampleDeliveredText, NEUTRAL_SAMPLE_DELIVERED_TEXT);
  const coreName = asString(coreTarget.display_name, "核心");
  const optionalName = asString(optionalTarget.display_name, "附属设施");
  return {
    stats: [
      { label: "波次", value: battleWaveLabel(battle) },
      { label: "核心", value: `${battle.coreHp}/${coreTarget.durability || 10}` },
      { label: "电力", value: battle.power },
      { label: "材料", value: battle.resources },
      { label: "漏失", value: battle.leaks },
    ],
    tasksTitle: "本场目标",
    taskItems: [
      { title: `守住${coreName}`, text: (battle.config || {}).victory_condition || "" },
      { title: "保护目标", text: `${optionalName} · 当前耐久 ${battle.optionalHp}/${optionalTarget.durability || 4}` },
      {
        title: "现场状态",
        text: battle.sampleDelivered ? sampleText : sampleProgressText,
      },
      { title: "环境影响", text: asString(hints.fieldCondition, NEUTRAL_ENVIRONMENT_TEXT) },
    ],
    info: {
      avatarUrl: npcAvatarUrl,
      avatarAlt: asString(npcAvatarAlt, NEUTRAL_NPC_AVATAR_ALT),
      title: "战术面板",
      items: [
        { title: "下一波", text: nextWaveLabel },
        { title: "敌人弱点", text: asString(hints.enemyWeakness, NEUTRAL_ENEMY_WEAKNESS) },
        {
          title: "NPC 建议",
          text: asString(hints.npcAdvice, NEUTRAL_NPC_ADVICE),
        },
      ],
    },
    toolbarTools: toolbarTools || [],
    toastText: battle.toastUntil && battle.elapsedMs > battle.toastUntil ? "" : battle.toast || "",
    pauseText: battle.paused ? "继续" : "暂停",
    speedText: `${battle.speed}x`,
  };
}
