const SETTLEMENT_TEXT = {
  gray_lantern_station: {
    victory: "灰灯驿站守住，首战样品被送回中枢复盘。",
    defeat: "灰灯驿站灯火摇晃，但折光绊索仍留下有效迟滞数据。",
    sample: "折光绊索对高速影潮有效，但稳定性偏低，适合进入后续正式研发。",
    npc: "守灯人记录了迟滞场偏移；补线人和北路斥候随后加入局势评估。",
    delta: "补给线与灯芯仓被纳入下一轮防守，北路侦察事件被触发。",
  },
  lamp_wick_store: {
    victory: "灯芯仓守住，旧补给线恢复，灰烬下发现可用辉晶。",
    defeat: "灯芯仓库存受损，但爆鸣塔的清场能力被确认。",
    sample: "灯灰爆鸣塔能处理聚集敌人，也暴露出材料消耗和误触风险。",
    npc: "补线人确认补给线可维持下一轮防守，并建议把爆鸣塔整理为正式蓝图。",
    delta: "旧信号塔回光压力变成新的可处理节点，北路斥候提供路径预测。",
  },
  old_signal_tower: {
    victory: "旧信号塔短暂稳定，回流方向被记录为后续测标线索。",
    defeat: "旧塔回光失稳，但棱镜中继塔的显形效果仍被记录。",
    sample: "回光棱镜中继塔能短暂显形并减速敌群，但会牵出新的分潮风险。",
    npc: "北路斥候提醒中枢：这次稳定不是终点，而是下一条分潮线的开端。",
    delta: "本章三处防线完成，北路分潮线留作后续版本的开放节点。",
  },
};

export function createSettlementFeatureController({
  root,
  getState,
  getCurrentNodeId,
  displayNameForNodeId,
  screenHeader,
  safeText,
  imageTag,
  npcPortraitUrl,
  getSurfaceContributions,
} = {}) {
  const dependencies = {
    getState,
    getCurrentNodeId,
    displayNameForNodeId,
    screenHeader,
    safeText,
    imageTag,
    npcPortraitUrl,
    getSurfaceContributions,
  };
  if (!root) throw new TypeError("createSettlementFeatureController requires root");
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createSettlementFeatureController requires ${name}`);
    }
  }

  function buildLocalSettlement(outcome, nodeId = getCurrentNodeId()) {
    const text = SETTLEMENT_TEXT[nodeId] || SETTLEMENT_TEXT.gray_lantern_station;
    return {
      node_id: nodeId,
      result: outcome.result,
      battle_summary: outcome.result === "victory" ? text.victory : text.defeat,
      sample_performance: text.sample,
      npc_feedback: text.npc,
      world_delta: { summary: text.delta },
    };
  }

  function evidenceMarkup() {
    const state = getState();
    const evidence = state.evidence;
    const settlement = state.settlement || {};
    const actualAsset = settlement.primary_deployed_asset || null;
    const actualName = actualAsset && actualAsset.display_name;
    if (!evidence) {
      return `
        <details class="evidence-drawer">
          <summary>留档片段</summary>
          <div class="log-lines">
            <span>实战对象：${safeText(actualName || "未部署试作品")}</span><span>试作：${actualAsset ? "已部署" : "未部署"}</span>
            <span>战斗：${safeText((state.battleOutcome || {}).result || "完成")}</span>
          </div>
        </details>
      `;
    }
    const job = evidence.research_job || {};
    const battle = evidence.battle_result || {};
    return `
      <details class="evidence-drawer">
        <summary>留档片段</summary>
        <div class="log-lines">
          <span>实战对象：${safeText(actualName || "未部署试作品")}</span>
          <span>试作：${safeText(job.status || (actualAsset ? "已部署" : "未登记"))}</span>
          <span>战斗：${safeText(((battle.settlement || {}).result) || (state.battleOutcome || {}).result || "完成")}</span>
          <span>封存：${safeText(((evidence.audit_summary || {}).overall_status) || "通过")}</span>
        </div>
      </details>
    `;
  }

  function surfaceContributions(nodeId = getCurrentNodeId()) {
    return getSurfaceContributions(nodeId).filter((item) => item.kind === "settlement_note");
  }

  function projectSettlement(settlement) {
    const baseWorldDelta =
      settlement.world_delta && typeof settlement.world_delta === "object"
        ? settlement.world_delta
        : {};
    const projected = {
      ...settlement,
      world_delta: { ...baseWorldDelta },
    };
    const contributions = surfaceContributions(settlement.node_id);
    const resultSummary = contributions.find((item) => item.slot === "result_summary");
    const worldDelta = contributions.find((item) => item.slot === "world_delta");
    if (resultSummary && resultSummary.payload.summary) {
      projected.battle_summary = resultSummary.payload.summary;
    }
    if (worldDelta && worldDelta.payload.summary) {
      projected.world_delta.summary = worldDelta.payload.summary;
    }
    return projected;
  }

  function renderSettlement() {
    const state = getState();
    const settlement = projectSettlement(
      state.settlement || buildLocalSettlement(state.battleOutcome || {}),
    );
    const outcome = state.battleOutcome || {};
    const isVictory = settlement.result !== "defeat";
    root.innerHTML = `
      <main class="screen">
        ${screenHeader("战后结算", "战斗结果已经反映到局势变化与后续研发线索。", displayNameForNodeId(settlement.node_id))}
        <section class="settlement-grid">
          <article class="settlement-card">
            <div class="result-banner"><h2>${isVictory ? "节点守住" : "节点濒危"}</h2><p class="panel-text">${safeText(settlement.battle_summary || "")}</p></div>
            <div class="event-list" style="margin-top:14px">
              <div class="event-item"><strong>核心耐久</strong><span>${safeText(outcome.protected_core_hp ?? "-")}</span></div>
              <div class="event-item"><strong>漏失数量</strong><span>${safeText(outcome.leaked_enemy_count ?? 0)}</span></div>
              <div class="event-item"><strong>样品表现</strong><span>${safeText(settlement.sample_performance || "")}</span></div>
              <div class="event-item"><strong>世界变化</strong><span>${safeText(((settlement.world_delta || {}).summary) || "驿站状态改变，新的研究线索出现。")}</span></div>
              ${settlement.interlude_summary ? `<div class="event-item"><strong>后续演化</strong><span>${safeText(settlement.interlude_summary)}</span></div>` : ""}
            </div>
            ${evidenceMarkup()}
          </article>
          <aside class="settlement-card">
            <div class="side-avatar">${imageTag(npcPortraitUrl("npc_workshop_mentor"), "临时工坊老师傅")}</div>
            <h2 class="panel-title">NPC 反馈</h2>
            <p class="panel-text">${safeText(settlement.npc_feedback || "")}</p>
            <div class="tag-row"><span class="tag">光幕干扰</span><span class="tag">正式研发线索</span><span class="tag">样品缺陷已暴露</span></div>
            <div class="screen-actions" style="margin-top:16px">
              <button class="primary-button" data-action="return-map">返回大地图</button>
              <button class="ghost-button" data-action="restart-battle">重放战斗</button>
            </div>
          </aside>
        </section>
      </main>
    `;
  }

  return {
    buildLocalSettlement,
    evidenceMarkup,
    projectSettlement,
    renderSettlement,
    surfaceContributions,
  };
}
