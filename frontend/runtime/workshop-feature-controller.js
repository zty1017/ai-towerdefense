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

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function effectSummary(candidate, fallback) {
  const effects = asList(asObject(candidate.gameplay).effect_blocks);
  const labels = effects.slice(0, 3).map((effect) => {
    if (effect.type === "area_damage") return `造成 ${effect.amount ?? "一定"} 点范围伤害`;
    if (effect.type === "damage") return `造成 ${effect.amount ?? "一定"} 点伤害`;
    if (effect.type === "slow") return `使敌人减速 ${Math.round(Number(effect.slow_ratio || 0) * 100)}%`;
    if (effect.type === "shield") return `提供 ${effect.shield_amount ?? "短时"} 点护盾`;
    if (effect.type === "chain") return "攻击可在相邻目标间传递";
    if (effect.type === "power_cost") return `持续消耗 ${effect.power_per_second ?? "额外"} 点供能`;
    return "产生一种受控战场效果";
  });
  return labels.length ? `${labels.join("，")}。` : fallback;
}

function constraintSummary(candidate, kind) {
  const constraints = asObject(asObject(candidate.gameplay).constraints);
  const parts = [];
  if (constraints.max_instances != null) parts.push(`本场最多部署 ${constraints.max_instances} 次`);
  if (constraints.requires_power_grid) parts.push("需要接入稳定供能");
  if (kind === "tower_blueprint") parts.push("只能安装在可用防御平台");
  if (kind === "temporary_trap_sample") parts.push("需要放在允许布置的道路附近");
  if (kind === "support_item") parts.push("可在战场范围内选择释放位置");
  return parts.join("；") || "样品将在战斗中途送达，部署条件以战场提示为准。";
}

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
    const briefing = getBriefing();
    const sample = getBattleConfig().sample_asset || {};
    const contributions = surfaceContributions();
    const compiled = contributions.find((item) => item.kind === "proposal_hint");
    const participant = contributions.find((item) => item.kind === "participant_notice");
    const compiledPayload = asObject(compiled && compiled.payload);
    const proposalRecord = state.research.proposal || {};
    const candidate = asObject(proposalRecord.compiled_candidate);
    const presentation = asObject(candidate.presentation);
    const gameplay = asObject(candidate.gameplay);
    const proposalKind =
      gameplay.asset_type ||
      (((proposalRecord.compiler_metadata || {}).compiled_object || {}).candidate_kind) ||
      compiledPayload.candidate_kind ||
      "temporary_trap_sample";
    const hasProposal = Boolean(
      proposalRecord.proposal_id || compiled || state.research.status === "proposed",
    );
    if (!hasProposal) return null;
    const candidateMaterialIds = asList(asObject(candidate.provenance).material_ids);
    const availableMaterials = asList(briefing.available_materials || state.data.materials);
    const materialEntries = candidateMaterialIds.length
      ? candidateMaterialIds.map((id) => materialName(id))
      : availableMaterials.slice(0, 3).map((item) => {
          const id = item.material_id || item.resource_id || item.stable_internal_id;
          const quantity = item.quantity ?? item.amount ?? item.default_quantity;
          return `${materialName(id)}${quantity == null ? "" : ` x${quantity}`}`;
        });
    const defaultEffects = {
      tower_blueprint: "在防御平台上形成一座可持续参与战斗的试作装置。",
      temporary_trap_sample: "在敌人路径附近形成一次性战场效果。",
      support_item: "在指定区域释放一次应急支援效果。",
    };
    return {
      name:
        presentation.name ||
        proposalRecord.display_name ||
        compiledPayload.title ||
        "现场试作草案",
      summary:
        presentation.short_description ||
        proposalRecord.summary ||
        compiledPayload.summary ||
        "当前构想已经被整理为一件可进入实战验证的试作品。",
      effect:
        compiledPayload.effect_summary ||
        effectSummary(candidate, defaultEffects[proposalKind] || sample.effect_summary),
      material: materialEntries.join(" / ") || "使用当前节点允许调用的材料",
      constraint:
        compiledPayload.constraint ||
        constraintSummary(candidate, proposalKind),
      risk:
        proposalRecord.risk_note ||
        "当前仅确认了可运行边界，隐藏缺陷需要在本场实战后继续记录。",
      npc:
        compiledPayload.npc_review ||
        asObject(participant && participant.payload).summary ||
        "在场人员确认方案符合当前危机，但建议保留材料余量应对变化。",
      kind: proposalKind,
      source: candidate.id ? "compiled_candidate" : "runtime_fallback",
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
    const participantPayload = asObject(participants[0] && participants[0].payload);
    const briefingNpcIds = asList(briefing.npcs_present);
    const compiledNpc = asList(state.data.npcs).find((item) => {
      const id = item && (item.stable_internal_id || item.npc_id || item.id);
      return briefingNpcIds.includes(id);
    }) || {};
    const participantId =
      participantPayload.npc_id ||
      compiledNpc.stable_internal_id ||
      compiledNpc.npc_id ||
      compiledNpc.id ||
      "";
    const participantName =
      participantPayload.display_name || compiledNpc.display_name || "节点联络人";
    const participantSummary =
      compiledNpc.voice ||
      compiledNpc.player_summary ||
      participantPayload.summary ||
      "先说明你要解决的战场问题，我会判断现场条件是否支撑试作。";
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
                  <div class="workshop-npc-avatar">${imageTag(npcPortraitUrl(participantId), participantName)}</div>
                  <div>
                    <span>${safeText(participantName)}</span>
                    <p>${safeText(participantSummary)}</p>
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
              ${state.research.errorMessage ? `<p class="workshop-material-notice">方案尚未完成登记，请稍后重试。</p>` : ""}
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
