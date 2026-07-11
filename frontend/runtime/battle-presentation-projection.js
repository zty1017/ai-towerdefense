function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asString(value, fallback = "") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

const NEUTRAL_NODE_DISPLAY_NAME = "当前节点";
const NEUTRAL_NPC_DISPLAY_NAME = "节点联络人";
const NEUTRAL_NPC_PORTRAIT_ID = "";
const NEUTRAL_INTRO_LINE = "影潮正在逼近，先稳住当前节点防线。";
const NEUTRAL_ENEMY_WEAKNESS = "观察敌潮走向，优先守住核心。";
const NEUTRAL_NPC_ADVICE_BEFORE = "在主路边缘部署防御，别让第一波直冲核心。";
const NEUTRAL_NPC_ADVICE_AFTER = "把临时装置压在转角，能拖延后续波次。";
const NEUTRAL_ENVIRONMENT = "当前节点战场条件尚未明确记录。";
const NEUTRAL_SAMPLE_DELIVERED_TEXT = "临时装置已送达。";
const NEUTRAL_SAMPLE_DISPLAY_NAME = "临时装置";

function presentationFromBattleConfig(battleConfig) {
  const config = asObject(battleConfig);
  return asObject(config.presentation);
}

function sampleAssetFromBattleConfig(battleConfig) {
  const config = asObject(battleConfig);
  return asObject(config.sample_asset);
}

function introDialogue(presentation, nodeId, narrativeIntro) {
  if (narrativeIntro && narrativeIntro.name && narrativeIntro.line) {
    return {
      name: narrativeIntro.name,
      line: narrativeIntro.line,
      portraitId: narrativeIntro.portraitId || asString(presentation.npc_portrait_id, NEUTRAL_NPC_PORTRAIT_ID),
      contributionId: narrativeIntro.contributionId || null,
    };
  }
  const dialogue = asObject(presentation.intro_dialogue);
  if (dialogue.line || dialogue.name) {
    return {
      name: asString(dialogue.name, asString(presentation.npc_display_name, NEUTRAL_NPC_DISPLAY_NAME)),
      line: asString(dialogue.line, NEUTRAL_INTRO_LINE),
      portraitId: asString(dialogue.portrait_id, asString(presentation.npc_portrait_id, NEUTRAL_NPC_PORTRAIT_ID)),
      contributionId: null,
    };
  }
  return {
    name: asString(presentation.npc_display_name, NEUTRAL_NPC_DISPLAY_NAME),
    line: NEUTRAL_INTRO_LINE,
    portraitId: asString(presentation.npc_portrait_id, NEUTRAL_NPC_PORTRAIT_ID),
    contributionId: null,
  };
}

function tacticalHints(presentation, battle) {
  const hints = asObject(presentation.tactical_hints);
  const sampleDelivered = Boolean(battle && battle.sampleDelivered);
  const advice = sampleDelivered
    ? asString(hints.npc_advice_after_sample, NEUTRAL_NPC_ADVICE_AFTER)
    : asString(hints.npc_advice_before_sample, NEUTRAL_NPC_ADVICE_BEFORE);
  return {
    enemyWeakness: asString(hints.enemy_weakness, NEUTRAL_ENEMY_WEAKNESS),
    npcAdvice: advice,
    fieldCondition: asString(hints.field_condition, NEUTRAL_ENVIRONMENT),
  };
}

export function buildBattlePresentation({
  nodeId = "",
  battleConfig = {},
  battle = {},
  narrativeIntro = null,
} = {}) {
  const presentation = presentationFromBattleConfig(battleConfig);
  const config = asObject(battleConfig);
  const sampleAsset = sampleAssetFromBattleConfig(battleConfig);
  const hints = tacticalHints(presentation, battle);
  const intro = introDialogue(presentation, nodeId, narrativeIntro);
  const sampleDisplayName = asString(
    sampleAsset.display_name,
    asString(presentation.sample_display_name, NEUTRAL_SAMPLE_DISPLAY_NAME),
  );
  const sampleDeliveredText = asString(
    presentation.sample_delivered_text,
    `${sampleDisplayName}已送达。`,
  );
  return {
    nodeId: asString(config.node_id, nodeId),
    nodeDisplayName: asString(config.display_name, NEUTRAL_NODE_DISPLAY_NAME),
    npcPortraitId: asString(presentation.npc_portrait_id, NEUTRAL_NPC_PORTRAIT_ID),
    npcDisplayName: asString(presentation.npc_display_name, NEUTRAL_NPC_DISPLAY_NAME),
    npcAvatarAlt: asString(presentation.npc_display_name, NEUTRAL_NPC_DISPLAY_NAME),
    introDialogue: intro,
    tacticalHints: hints,
    sampleDisplayName,
    sampleDeliveredText,
  };
}

export function neutralPresentation(nodeId = "") {
  return buildBattlePresentation({ nodeId, battleConfig: {}, battle: {} });
}
