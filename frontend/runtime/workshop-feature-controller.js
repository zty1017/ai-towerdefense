const PROPOSAL_DEFAULTS = {
  gray_lantern_station: {
    summary: "灯光编织的临时绊线，可让经过的影潮短暂迟滞。",
    material: "灯芯碎片 x2 / 导线丝 x1",
    constraint: "样品会在第一波中途送达，需要部署在路径转角附近。",
    risk: "稳定性偏低，强雾中效果可能衰减。",
    npc: "守灯人认为它能争取第一波后的喘息。",
  },
  lamp_wick_store: {
    summary: "把灯灰压入旧灯壳，形成短促爆鸣和灰灯护幕。",
    material: "灯灰 x2 / 灯芯碎片 x1 / 辉晶线索",
    constraint: "适合放在双路径汇合点附近，误放会浪费爆鸣窗口。",
    risk: "爆鸣范围可观，但材料消耗高，密集敌潮后容易出现空档。",
    npc: "补线人建议先护住补给线接点，再用爆鸣处理聚集影潮。",
  },
  old_signal_tower: {
    summary: "让旧塔回光穿过棱镜，短暂显形来敌并压低路径压力。",
    material: "辉晶 x1 / 导线丝 x1 / 回光玻片样本",
    constraint: "需要靠近旧塔回光范围，离核心太远会失去显形效果。",
    risk: "回光能稳定短时间，但可能引来新的分潮线。",
    npc: "北路斥候建议把它当作稳定器，而不是长期防线。",
  },
};

const INTENT_PRESETS = [
  {
    id: "slow",
    label: "迟滞敌群",
    intent: "我想做一个能在道路转角拖慢影潮的临时陷阱。",
  },
  {
    id: "attack",
    label: "持续打击",
    intent: "我想做一座能持续攻击影潮的聚光灯塔。",
  },
  {
    id: "support",
    label: "应急支援",
    intent: "我想做一个能在危急时支援整片战场的灯火脉冲。",
  },
];

export function createWorkshopFeatureController({
  root,
  getState,
  getBriefing,
  getBattleConfig,
  getCurrentNodeId,
  getCurrentNodeDisplayName,
  screenHeader,
  safeText,
  imageTag,
  npcPortraitUrl,
  materialName,
  getSurfaceContributions,
} = {}) {
  const dependencies = {
    getState,
    getBriefing,
    getBattleConfig,
    getCurrentNodeId,
    getCurrentNodeDisplayName,
    screenHeader,
    safeText,
    imageTag,
    npcPortraitUrl,
    materialName,
    getSurfaceContributions,
  };
  if (!root) throw new TypeError("createWorkshopFeatureController requires root");
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createWorkshopFeatureController requires ${name}`);
    }
  }

  function currentProposal() {
    const state = getState();
    if (["idle", "stale", "proposing"].includes(state.research.status)) return null;
    const sample = (getBattleConfig().sample_asset) || {};
    const text = PROPOSAL_DEFAULTS[getCurrentNodeId()] || PROPOSAL_DEFAULTS.gray_lantern_station;
    const compiled = surfaceContributions().find((item) => item.kind === "proposal_hint");
    const compiledPayload = (compiled && compiled.payload) || {};
    const proposalRecord = state.research.proposal || {};
    const proposalKind =
      (((proposalRecord.compiler_metadata || {}).compiled_object || {}).candidate_kind) ||
      compiledPayload.candidate_kind ||
      "temporary_trap_sample";
    const expectedEffects = {
      tower_blueprint: "在可部署平台建造一座持续攻击的试作装置。",
      temporary_trap_sample: "在敌人路径附近布置一次性迟滞装置。",
      support_item: "在指定区域释放一次应急支援效果。",
    };
    const placementConstraints = {
      tower_blueprint: "样品会在战斗中途送达，只能安装在现有防御平台。",
      temporary_trap_sample: text.constraint,
      support_item: "样品会在战斗中途送达，可在战场内选择释放位置。",
    };
    const npcReviews = {
      tower_blueprint: "守灯人建议把射界对准道路转角，同时保留核心照明的供能余量。",
      temporary_trap_sample: text.npc,
      support_item: "守灯人建议把它留到防线出现缺口时再使用。",
    };
    const hasProposal = Boolean(
      proposalRecord.proposal_id || compiled || state.research.status === "proposed",
    );
    if (!hasProposal) return null;
    return {
      name:
        proposalRecord.display_name ||
        compiledPayload.title ||
        "现场试作草案",
      summary: proposalRecord.summary || compiledPayload.summary || text.summary,
      effect:
        compiledPayload.effect_summary ||
        expectedEffects[proposalKind] ||
        sample.effect_summary ||
        "形成一件可在当前战场验证的试作品。",
      material: text.material,
      constraint:
        compiledPayload.constraint ||
        placementConstraints[proposalKind] ||
        text.constraint,
      risk: proposalRecord.risk_note || text.risk,
      npc: compiledPayload.npc_review || npcReviews[proposalKind] || text.npc,
      kind: proposalKind,
    };
  }

  function surfaceContributions() {
    return getSurfaceContributions(getCurrentNodeId());
  }

  function renderWorkshop() {
    const state = getState();
    const briefing = getBriefing();
    const proposal = currentProposal();
    const hasProposal = Boolean(proposal);
    const materials = briefing.available_materials || state.data.materials || [];
    const targets = briefing.protection_targets || [];
    const threat = briefing.threat || {};
    const contributions = surfaceContributions();
    const participants = contributions.filter((item) => item.kind === "participant_notice");
    const materialNotices = contributions.filter((item) => item.kind === "material_notice");
    const primaryTarget = targets[0] || {};
    const proposalKinds = {
      tower_blueprint: "固定防御装置",
      temporary_trap_sample: "路径试作陷阱",
      support_item: "战场支援道具",
    };
    const proposalBusy = state.research.status === "proposing";
    root.innerHTML = `
      <main class="screen">
        ${screenHeader(`${getCurrentNodeDisplayName()}应急改造间`, briefing.summary || "影潮正在接近。", "现场试作")}
        <section class="workshop-shell">
          <div class="workshop-context-bar" aria-label="当前危机摘要">
            <div><span>来敌</span><strong>${safeText(threat.enemy_traits || "高速、低耐久。")}</strong></div>
            <div><span>守护</span><strong>${safeText(primaryTarget.display_name || "节点核心")}</strong></div>
            <div><span>试作窗口</span><strong>${safeText((briefing.constraints || {}).research_budget || "只允许一次现场试作。")}</strong></div>
          </div>
          <div class="workshop-stage">
            <section class="panel workshop-bench">
              <div class="workshop-section-heading">
                <div>
                  <div class="eyebrow">构想工作台</div>
                  <h2>你想让这件装置解决什么？</h2>
                </div>
                <span class="workshop-step">01 构想</span>
              </div>
              <textarea class="workshop-input" data-field="intent" placeholder="说出目标、攻击方式或希望利用的材料……">${safeText(state.intentText)}</textarea>
              <div class="workshop-focus-row">
                <span>快速方向</span>
                <div class="workshop-focus-options" role="group" aria-label="快速构想方向">
                  ${INTENT_PRESETS.map((preset) => `<button class="workshop-focus-button" data-action="intent-preset" data-intent="${safeText(preset.intent)}">${safeText(preset.label)}</button>`).join("")}
                </div>
              </div>
              <div class="workshop-bench-info">
                <div class="workshop-npc-note">
                  <div class="workshop-npc-avatar">${imageTag(npcPortraitUrl("npc_workshop_mentor"), "在场评审者")}</div>
                  <div>
                    <span>${safeText((participants[0] && participants[0].payload.display_name) || "驿站守灯人")}</span>
                    <p>${safeText((participants[0] && participants[0].payload.summary) || "先说明你要解决的战场问题，我会判断现场条件是否支撑试作。")}</p>
                  </div>
                </div>
                <div class="workshop-material-shelf">
                  <span>本次可调用材料</span>
                  <div>
                    ${materials.map((item) => `<span class="material-token"><b>${safeText(materialName(item.material_id || item.resource_id || item.stable_internal_id))}</b><i>${safeText(item.quantity ?? item.amount ?? item.default_quantity ?? 0)}</i></span>`).join("")}
                  </div>
                </div>
              </div>
              ${materialNotices.map((item) => `<p class="workshop-material-notice">${safeText(item.payload.summary || `${materialName(item.payload.material_id)}可用数量 ${item.payload.quantity ?? 0}`)}</p>`).join("")}
              <div class="workshop-primary-action">
                <button class="${hasProposal ? "ghost-button" : "primary-button"}" data-action="proposal-refresh" ${proposalBusy ? "disabled" : ""}>${proposalBusy ? "正在推演" : hasProposal ? "重新推演方案" : "推演一个方案"}</button>
              </div>
            </section>
            <aside class="panel workshop-review ${hasProposal ? "has-proposal" : "is-empty"}">
              ${
                proposal
                  ? `<div class="workshop-review-heading">
                      <div><div class="eyebrow">现场评审结果</div><h2>${safeText(proposal.name)}</h2></div>
                      <span class="workshop-step">02 方案</span>
                    </div>
                    <p class="workshop-proposal-summary">${safeText(proposal.summary)}</p>
                    <div class="workshop-proposal-kind"><span>建议形态</span><strong>${safeText(proposalKinds[proposal.kind] || "临时试作品")}</strong></div>
                    <div class="workshop-review-list">
                      <div><span>预期作用</span><p>${safeText(proposal.effect)}</p></div>
                      <div><span>建议投入</span><p>${safeText(proposal.material)}</p></div>
                      <div><span>现场约束</span><p>${safeText(proposal.constraint)}</p></div>
                      <div class="is-risk"><span>仍不确定</span><p>${safeText(proposal.risk)}</p></div>
                    </div>
                    <blockquote>${safeText(proposal.npc)}</blockquote>
                    <button class="primary-button workshop-confirm" data-action="confirm-prototype" ${["confirming"].includes(state.research.status) ? "disabled" : ""}>${state.research.status === "confirming" ? "正在登记试作" : "投入试作"}</button>`
                  : `<div class="workshop-review-empty">
                      <span class="workshop-step">02 方案</span>
                      <div class="proposal-empty-mark" aria-hidden="true"></div>
                      <div>
                        <div class="eyebrow">等待构想</div>
                        <h2>${proposalBusy ? "在场人员正在推演" : "方案席仍是空的"}</h2>
                        <p>${proposalBusy ? "他们正在结合来敌、地形和现有材料整理一个可试作方案。" : "先在工作台留下构想。只有形成方案后，这里才会出现预期作用与代价。"}</p>
                      </div>
                    </div>`
              }
            </aside>
          </div>
        </section>
      </main>
    `;
  }

  return { currentProposal, renderWorkshop, surfaceContributions };
}
