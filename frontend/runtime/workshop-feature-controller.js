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
  sampleIconUrl,
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
    sampleIconUrl,
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
    const sample = (getBattleConfig().sample_asset) || {};
    const text = PROPOSAL_DEFAULTS[getCurrentNodeId()] || PROPOSAL_DEFAULTS.gray_lantern_station;
    const compiled = surfaceContributions().find((item) => item.kind === "proposal_hint");
    const compiledPayload = (compiled && compiled.payload) || {};
    return {
      name: compiledPayload.title || sample.display_name || "折光绊索",
      summary: compiledPayload.summary || text.summary,
      effect: sample.effect_summary || "范围内敌人短暂减速。",
      material: text.material,
      constraint: text.constraint,
      risk: text.risk,
      npc: text.npc,
    };
  }

  function surfaceContributions() {
    return getSurfaceContributions(getCurrentNodeId());
  }

  function renderWorkshop() {
    const state = getState();
    const briefing = getBriefing();
    const proposal = currentProposal();
    const materials = briefing.available_materials || state.data.materials || [];
    const targets = briefing.protection_targets || [];
    const threat = briefing.threat || {};
    const contributions = surfaceContributions();
    const participants = contributions.filter((item) => item.kind === "participant_notice");
    const materialNotices = contributions.filter((item) => item.kind === "material_notice");
    root.innerHTML = `
      <main class="screen">
        ${screenHeader(`${getCurrentNodeDisplayName()}应急改造间`, briefing.summary || "影潮正在接近。", "现场试作")}
        <section class="workshop-grid">
          <aside class="panel">
            <h2 class="panel-title">当前危机</h2>
            <div class="brief-list">
              <div class="brief-item"><strong>敌潮</strong><span>${safeText(threat.enemy_traits || "高速、低耐久。")}</span></div>
              <div class="brief-item"><strong>方向</strong><span>${safeText(threat.approach_direction || "东南方向。")}</span></div>
              ${targets.map((target) => `<div class="brief-item"><strong>${safeText(target.display_name)}</strong><span>${safeText(target.summary)}</span></div>`).join("")}
            </div>
          </aside>
          <section class="panel">
            <h2 class="panel-title">构想</h2>
            <textarea class="workshop-input" data-field="intent">${safeText(state.intentText)}</textarea>
            <div class="screen-actions" style="margin-top:12px">
              <button class="ghost-button" data-action="proposal-refresh" ${state.research.status === "proposing" ? "disabled" : ""}>${state.research.status === "proposing" ? "校准中" : "校准方案"}</button>
              <button class="primary-button" data-action="confirm-prototype" ${["proposing", "confirming"].includes(state.research.status) ? "disabled" : ""}>确认试作</button>
            </div>
            <article class="proposal-card">
              <div class="proposal-art">${imageTag(sampleIconUrl(), proposal.name)}</div>
              <div class="proposal-body">
                <h3>${safeText(proposal.name)}</h3>
                <p class="panel-text">${safeText(proposal.summary)}</p>
                <div class="tag-row">
                  <span class="tag">减速：中</span><span class="tag">持续：短</span>
                  <span class="tag">稳定性：偏低</span><span class="tag">次数：2</span>
                </div>
                <div class="event-list">
                  <div class="event-item"><strong>预期作用</strong><span>${safeText(proposal.effect)}</span></div>
                  <div class="event-item"><strong>建议投入</strong><span>${safeText(proposal.material)}</span></div>
                  <div class="event-item"><strong>已知约束</strong><span>${safeText(proposal.constraint)}</span></div>
                  <div class="event-item"><strong>不确定性</strong><span>${safeText(proposal.risk)}</span></div>
                  <div class="event-item"><strong>NPC 初判</strong><span>${safeText(proposal.npc)}</span></div>
                </div>
              </div>
            </article>
          </section>
          <aside class="panel">
            <div class="side-avatar">${imageTag(npcPortraitUrl("npc_workshop_mentor"), "临时工坊老师傅")}</div>
            <h2 class="panel-title">参与者与条件</h2>
            <div class="material-grid">
              ${materials.map((item) => `<div class="meter-row"><span>${safeText(materialName(item.material_id || item.resource_id))}</span><b>${safeText(item.quantity ?? item.amount ?? 0)}</b></div>`).join("")}
            </div>
            <div class="event-list" style="margin-top:12px">
              ${participants.map((item) => `<div class="event-item"><strong>${safeText(item.payload.display_name || "在场参与者")}</strong><span>${safeText(item.payload.summary || "参与当前试作。")}</span></div>`).join("")}
              ${materialNotices.map((item) => `<div class="event-item"><strong>${safeText(item.payload.display_name || materialName(item.payload.material_id))}</strong><span>${safeText(item.payload.summary || `可用数量 ${item.payload.quantity ?? 0}`)}</span></div>`).join("")}
              <div class="event-item"><strong>设施</strong><span>${safeText((briefing.facility_state || {}).summary || "临时工坊可用。")}</span></div>
              <div class="event-item"><strong>限制</strong><span>${safeText((briefing.constraints || {}).sample_delivery || "样品在战斗中途送达。")}</span></div>
            </div>
          </aside>
        </section>
      </main>
    `;
  }

  return { currentProposal, renderWorkshop, surfaceContributions };
}
