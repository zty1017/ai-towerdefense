const NPC_FALLBACK_NAMES = {
  engineer_001: "驿站守灯人",
  scout_002: "北路斥候",
  npc_wire_mender_003: "补线人",
  npc_road_scout: "北路斥候",
};

const ROLE_FALLBACK_NAMES = {
  field_engineer: "现场改造",
  route_repair: "补给线抢修",
  material_adjustment: "材料替换",
  field_review: "试作评审",
  path_prediction: "路径预判",
  weakness_hint: "敌情提示",
  scouting_reliability: "侦察校准",
  scout: "侦察",
};

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function uniqueCards(cards, limit) {
  const seen = new Set();
  return cards
    .filter((card) => {
      const key = card.id || `${card.title}|${card.summary}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, limit);
}

export function createStrategicMapProjection({
  getMapData,
  getRunWorldState,
  getProfile,
  getSelectedNodeId,
  getCurrentNodeId,
  fallbackNodeId,
  getSurfaceContributions = () => [],
} = {}) {
  const dependencies = {
    getMapData,
    getRunWorldState,
    getProfile,
    getSelectedNodeId,
    getCurrentNodeId,
    getSurfaceContributions,
  };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createStrategicMapProjection requires ${name}`);
    }
  }

  function mapData() {
    return asObject(getMapData());
  }

  function runWorldState() {
    return asObject(getRunWorldState());
  }

  function nodeState(node) {
    const runNode = asList(runWorldState().map_nodes).find(
      (item) => item.node_id === node.stable_internal_id,
    );
    if (runNode && runNode.visibility === "hidden") return "hidden";
    if (runNode && runNode.status) return runNode.status;
    if (asObject(getProfile()).completedBattle && node.stable_internal_id === fallbackNodeId) {
      return "secured";
    }
    return node.state;
  }

  function mapNodeVisible(node) {
    return nodeState(node) !== "hidden";
  }

  function selectedMapNode() {
    const nodes = asList(mapData().nodes);
    return (
      nodes.find((node) => node.stable_internal_id === getSelectedNodeId()) ||
      nodes.find((node) => node.stable_internal_id === getCurrentNodeId()) ||
      nodes.find((node) => node.stable_internal_id === fallbackNodeId) ||
      nodes[0] ||
      null
    );
  }

  function surfaceContributions(nodeId) {
    return asList(getSurfaceContributions(nodeId));
  }

  function objectiveCards(map = mapData()) {
    const world = runWorldState();
    const compiled = surfaceContributions(getCurrentNodeId())
      .filter((item) => item.kind === "objective_card" || item.kind === "map_notice")
      .map((item) => ({
        id: item.contributionId,
        title: item.payload.title || "局势变化",
        summary: item.payload.summary || "",
        source: "activated_runtime",
      }));
    const cards = [...compiled];
    asList(world.tasks)
      .filter((task) => ["active", "available", "running", "queued"].includes(task.status))
      .slice(-3)
      .forEach((task) => cards.push({ id: task.task_id, title: task.title || "当前任务", summary: task.summary || "", source: "world_state" }));
    asList(world.random_events)
      .filter((event) => ["available", "pending"].includes(event.status))
      .slice(-2)
      .forEach((event) => cards.push({
        id: event.random_event_id,
        title: event.event_type === "threat_warning" ? "随机预警" : "临机事件",
        summary: event.summary || "",
        source: "world_state",
      }));
    asList(world.event_log).slice(-2).forEach((event) => cards.push({
      id: event.event_id,
      title: event.kind === "battle" ? "战报" : "局势变化",
      summary: event.summary || "",
      source: "world_state",
    }));
    if (!cards.length) {
      asList(map.floating_events).forEach((event) => cards.push({
        id: event.stable_internal_id,
        title: event.display_name || "当前目标",
        summary: event.summary || "",
        source: "map_runtime",
      }));
    }
    return uniqueCards(cards, 4);
  }

  function roleName(role) {
    if (role && typeof role === "object") return role.display_name || role.role_id || "现场建议";
    return ROLE_FALLBACK_NAMES[role] || role || "现场建议";
  }

  function npcName(npc) {
    const source = asObject(npc);
    return source.display_name || NPC_FALLBACK_NAMES[source.npc_id] || source.npc_id || "在场者";
  }

  function participantCards(nodeId) {
    const compiled = surfaceContributions(nodeId)
      .filter((item) => item.kind === "node_participant")
      .map((item) => ({
        id: item.payload.npc_id || item.contributionId,
        title: item.payload.display_name || npcName({ npc_id: item.payload.npc_id }),
        summary:
          item.payload.summary ||
          `可提供${asList(item.payload.gameplay_roles).map(roleName).join(" / ") || "现场建议"}`,
        source: "activated_runtime",
      }));
    const world = asList(runWorldState().npcs)
      .filter((npc) => npc.location_node_id === nodeId && npc.availability !== "absent")
      .map((npc) => ({
        id: npc.npc_id,
        title: npcName(npc),
        summary: `可提供${asList(npc.gameplay_roles).slice(0, 2).map(roleName).join(" / ") || "现场建议"}`,
        source: "world_state",
      }));
    return uniqueCards([...compiled, ...world], 2);
  }

  function nodeBadges(nodeId) {
    return surfaceContributions(nodeId)
      .filter((item) => item.kind === "node_badge")
      .map((item) => ({
        id: item.contributionId,
        label: item.payload.label,
        tone: item.payload.tone || "neutral",
      }))
      .slice(0, 3);
  }

  function snapshot() {
    const map = mapData();
    const selected = selectedMapNode();
    return {
      map,
      nodes: asList(map.nodes),
      selected,
      objectives: objectiveCards(map),
      participants: selected ? participantCards(selected.stable_internal_id) : [],
      badges: selected ? nodeBadges(selected.stable_internal_id) : [],
    };
  }

  return {
    mapNodeVisible,
    nodeBadges,
    nodeState,
    objectiveCards,
    participantCards,
    selectedMapNode,
    snapshot,
  };
}
