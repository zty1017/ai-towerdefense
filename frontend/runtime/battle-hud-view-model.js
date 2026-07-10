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

export function buildBattleHudViewModel({
  battle,
  objectives,
  sampleProgressText,
  nextWaveLabel,
  npcAvatarUrl,
  toolbarTools,
}) {
  const coreTarget = (objectives || {}).core_target || {};
  const optionalTarget = ((objectives || {}).optional_targets || [])[0] || {};
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
      { title: "守住核心", text: (battle.config || {}).victory_condition || "" },
      { title: "保护信标", text: `当前耐久 ${battle.optionalHp}/${optionalTarget.durability || 4}` },
      {
        title: "现场状态",
        text: battle.sampleDelivered ? "折光绊索已送达。" : sampleProgressText,
      },
      { title: "环境影响", text: "低雾压在路径转角，迟滞场更容易成形。" },
    ],
    info: {
      avatarUrl: npcAvatarUrl,
      avatarAlt: "灰灯驿站守灯人",
      title: "战术面板",
      items: [
        { title: "下一波", text: nextWaveLabel },
        { title: "敌人弱点", text: "低耐久，受灯栏打击后容易散开。" },
        {
          title: "NPC 建议",
          text: battle.sampleDelivered
            ? "把绊索压在主路转角，能拖住第二波残影。"
            : "先在主路边缘立灯栏，别让第一波直冲核心。",
        },
      ],
    },
    toolbarTools: toolbarTools || [],
    toastText: battle.toastUntil && battle.elapsedMs > battle.toastUntil ? "" : battle.toast || "",
    pauseText: battle.paused ? "继续" : "暂停",
    speedText: `${battle.speed}x`,
  };
}
