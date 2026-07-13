const DEFAULT_NODE_ID = "gray_lantern_station";

const NODE_VISUAL_PROFILES = {
  gray_lantern_station: {
    soil: ["#23251a", "#18231e", "#111817", "#171118"],
    patchPalette: [
      "rgba(103,112,78,0.22)",
      "rgba(118,97,58,0.18)",
      "rgba(51,86,74,0.18)",
      "rgba(92,78,56,0.20)",
    ],
    roadside: ["reed", "stone", "lamp_marker", "scrap"],
    glow: "rgba(255,211,122,0.18)",
  },
  lamp_wick_store: {
    soil: ["#252217", "#20251c", "#111918", "#18120f"],
    patchPalette: [
      "rgba(135,108,55,0.18)",
      "rgba(95,118,74,0.17)",
      "rgba(74,88,72,0.18)",
      "rgba(118,77,47,0.14)",
    ],
    roadside: ["crate", "stone", "pipe", "lamp_marker"],
    glow: "rgba(255,190,97,0.16)",
  },
  old_signal_tower: {
    soil: ["#1d2221", "#1b2227", "#121617", "#18151b"],
    patchPalette: [
      "rgba(75,103,109,0.18)",
      "rgba(100,88,67,0.17)",
      "rgba(52,78,88,0.16)",
      "rgba(96,72,93,0.13)",
    ],
    roadside: ["signal_stake", "stone", "scrap", "pipe"],
    glow: "rgba(158,220,255,0.13)",
  },
};

export function hashSceneryString(value) {
  let hash = 2166136261;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function createSeededRandom(seed) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let mixed = value;
    mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
    mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

export function createBattleSceneryGenerator({
  getBattle,
  getCurrentNodeId,
  getMapRuntimePackage,
  getMapGrid,
  getMapObjectives,
  getMapStylePack,
  getRoutes,
  getBuildSlots,
  isCellInGrid,
  distanceToPath,
  slotAt,
  colorFromStyle,
  rgbaFromStyle,
  mapRenderPlanHasLayer,
  fallbackNodeId = DEFAULT_NODE_ID,
}) {
  const clamp = (value, minimum, maximum) =>
    Math.max(minimum, Math.min(maximum, value));

  function runtimeMapSeed() {
    const pkg = getMapRuntimePackage() || {};
    return hashSceneryString(
      `${pkg.package_id || ""}|${pkg.node_id || getCurrentNodeId() || fallbackNodeId}`,
    );
  }

  function battleNodeVisualProfile() {
    const pkg = getMapRuntimePackage() || {};
    const nodeId = String(pkg.node_id || getCurrentNodeId() || fallbackNodeId);
    const fallback = NODE_VISUAL_PROFILES[nodeId] || NODE_VISUAL_PROFILES[DEFAULT_NODE_ID];
    const pack = getMapStylePack();
    if (!pack || pack.schema_version !== "map_style_pack.v0.1") return fallback;
    return {
      ...fallback,
      soil: [
        colorFromStyle("terrain_base", fallback.soil[0]),
        colorFromStyle("terrain_detail", fallback.soil[1]),
        colorFromStyle("road_base", fallback.soil[2]),
        colorFromStyle("fog", fallback.soil[3]),
      ],
      patchPalette: [
        rgbaFromStyle("terrain_detail", 0.2, fallback.patchPalette[0]),
        rgbaFromStyle("road_base", 0.16, fallback.patchPalette[1]),
        rgbaFromStyle("resource", 0.15, fallback.patchPalette[2]),
        rgbaFromStyle("hazard", 0.13, fallback.patchPalette[3]),
      ],
      glow: rgbaFromStyle("accent", 0.18, fallback.glow),
      road: {
        shadow: rgbaFromStyle("hazard", 0.38, "rgba(18,13,10,0.54)"),
        base: rgbaFromStyle("road_base", 0.86, "rgba(82,62,37,0.86)"),
        crown: rgbaFromStyle("road_edge", 0.58, "rgba(143,112,64,0.64)"),
        highlight: rgbaFromStyle("accent", 0.2, "rgba(201,169,103,0.18)"),
        shoulderDark: rgbaFromStyle("terrain_base", 0.58, "rgba(61,69,46,0.62)"),
        shoulderSoft: rgbaFromStyle("terrain_detail", 0.42, "rgba(33,41,32,0.46)"),
        groundBlend: rgbaFromStyle("terrain_base", 0.36, "rgba(28,34,25,0.36)"),
        edgeStain: rgbaFromStyle("road_base", 0.22, "rgba(111,77,56,0.22)"),
        pebbleWarm: rgbaFromStyle("road_edge", 0.24, "rgba(196,164,102,0.24)"),
        rut: rgbaFromStyle("road_base", 0.28, "rgba(62,45,27,0.24)"),
        flow: rgbaFromStyle("accent", 0.14, "rgba(255,213,126,0.14)"),
      },
      platform: {
        fillTop: rgbaFromStyle("build_slot", 0.48, "rgba(115,104,68,0.54)"),
        stroke: rgbaFromStyle("build_slot", 0.34, "rgba(179,153,94,0.18)"),
        active: rgbaFromStyle("accent", 0.68, "rgba(255,225,161,0.68)"),
      },
      objective: {
        core: colorFromStyle("objective", "#ffd37a"),
        optional: colorFromStyle("resource", "#9edcff"),
      },
      spawn: {
        glow: colorFromStyle("spawn", "#8f7cff"),
        stroke: rgbaFromStyle("spawn", 0.36, "rgba(187,166,255,0.36)"),
      },
      renderPlanLayersReady:
        mapRenderPlanHasLayer("road_band") &&
        mapRenderPlanHasLayer("build_slot_platform") &&
        mapRenderPlanHasLayer("objective_foundation") &&
        mapRenderPlanHasLayer("spawn_atmosphere"),
    };
  }

  function objectiveAtCell(cell) {
    const objectives = getMapObjectives();
    const targets = [
      objectives.core_target,
      ...(objectives.optional_targets || []),
    ].filter(Boolean);
    return targets.some(
      (target) =>
        target.position &&
        target.position.x === cell.x &&
        target.position.y === cell.y,
    );
  }

  function buildScenicRidges(random, grid) {
    const ridges = [];
    const maxX = Math.max(1, grid.width_cells - 1);
    const maxY = Math.max(1, grid.height_cells - 1);
    const anchors = [
      { x: -1.6, y: -0.4, w: 5.8, h: 1.4, side: "top" },
      { x: maxX * 0.34, y: -1.1, w: 6.2, h: 1.25, side: "top" },
      { x: maxX - 3.1, y: -0.5, w: 5.6, h: 1.35, side: "top" },
      { x: maxX + 0.4, y: maxY * 0.18, w: 1.6, h: 4.6, side: "right" },
      { x: maxX + 0.1, y: maxY * 0.58, w: 1.8, h: 4.2, side: "right" },
      { x: maxX * 0.2, y: maxY + 0.4, w: 5.8, h: 1.55, side: "bottom" },
      { x: maxX * 0.62, y: maxY + 0.2, w: 6.4, h: 1.5, side: "bottom" },
      { x: -1.3, y: maxY * 0.52, w: 1.7, h: 4.4, side: "left" },
    ];
    for (const anchor of anchors) {
      ridges.push({
        x: anchor.x + (random() - 0.5) * 0.8,
        y: anchor.y + (random() - 0.5) * 0.55,
        width: anchor.w * (0.86 + random() * 0.22),
        height: anchor.h * (0.86 + random() * 0.26),
        side: anchor.side,
        alpha: 0.18 + random() * 0.16,
        warm: random() > 0.56,
      });
    }
    return ridges;
  }

  function buildFieldEdgeProps(random) {
    const props = [];
    const edgeCount = 8;
    for (let index = 0; index < edgeCount; index += 1) {
      const count = 4 + Math.floor(random() * 3);
      for (let itemIndex = 0; itemIndex < count; itemIndex += 1) {
        if (random() < 0.18) continue;
        props.push({
          edgeIndex: index,
          t: (itemIndex + 0.16 + random() * 0.68) / count,
          angleJitter: (random() - 0.5) * 0.5,
          scale: 0.58 + random() * 0.92,
          kind: random() < 0.42 ? "stone" : random() < 0.76 ? "timber" : "reed",
          alpha: 0.18 + random() * 0.18,
        });
      }
    }
    return props;
  }

  function buildRoadsideProps(random, profile) {
    const props = [];
    for (const route of getRoutes()) {
      const waypoints = route.waypoints || [];
      for (let index = 0; index < waypoints.length - 1; index += 1) {
        const start = waypoints[index];
        const end = waypoints[index + 1];
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length = Math.max(1, Math.hypot(dx, dy));
        const normalX = -dy / length;
        const normalY = dx / length;
        const count = Math.max(2, Math.floor(length * 1.35));
        for (let itemIndex = 0; itemIndex < count; itemIndex += 1) {
          if (random() < 0.18) continue;
          const t = (itemIndex + 0.18 + random() * 0.64) / count;
          const side = random() < 0.5 ? -1 : 1;
          const kind = profile.roadside[Math.floor(random() * profile.roadside.length)];
          props.push({
            routeId: route.route_id || "route",
            x: start.x + dx * t + normalX * side * (0.58 + random() * 0.42),
            y: start.y + dy * t + normalY * side * (0.58 + random() * 0.42),
            kind,
            scale: 0.68 + random() * 0.52,
            rotation: (random() - 0.5) * 0.72,
            warm: random() > 0.45,
          });
        }
      }
    }
    return props;
  }

  function nearestPointOnRoutes(cell) {
    let best = null;
    for (const route of getRoutes()) {
      const points = route.waypoints || [];
      for (let index = 0; index < points.length - 1; index += 1) {
        const start = points[index];
        const end = points[index + 1];
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const lengthSquared = dx * dx + dy * dy;
        if (!lengthSquared) continue;
        const t = clamp(
          ((cell.x - start.x) * dx + (cell.y - start.y) * dy) / lengthSquared,
          0,
          1,
        );
        const x = start.x + dx * t;
        const y = start.y + dy * t;
        const distance = Math.hypot(cell.x - x, cell.y - y);
        if (!best || distance < best.distance) best = { x, y, distance };
      }
    }
    return best;
  }

  function buildSlotAccessTrails() {
    const trails = [];
    for (const slot of getBuildSlots()) {
      const cell = slot.position || slot;
      if (!isCellInGrid(cell)) continue;
      const nearest = nearestPointOnRoutes(cell);
      if (!nearest || nearest.distance > 1.65) continue;
      trails.push({
        slotId: slot.slot_id || `${cell.x},${cell.y}`,
        from: { x: cell.x, y: cell.y },
        to: { x: nearest.x, y: nearest.y },
      });
    }
    return trails;
  }

  function terrainFeatureSet() {
    const battle = getBattle();
    const grid = getMapGrid();
    const pkg = getMapRuntimePackage() || {};
    const key = `${pkg.package_id || getCurrentNodeId()}:${grid.width_cells}x${grid.height_cells}`;
    if (battle && battle.terrainFeatureSet && battle.terrainFeatureSet.key === key) {
      return battle.terrainFeatureSet;
    }

    const seed = runtimeMapSeed();
    const random = createSeededRandom(seed ^ hashSceneryString("procedural-battlefield"));
    const profile = battleNodeVisualProfile();
    const palette = profile.patchPalette;
    const bands = Array.from({ length: 8 }, (_, index) => ({
      y: -0.08 + index * 0.155 + (random() - 0.5) * 0.03,
      height: 0.18 + random() * 0.09,
      lean: (random() - 0.5) * 0.16,
      alpha: 0.035 + random() * 0.045,
      warm: random() > 0.48,
    }));
    const patches = Array.from({ length: 13 }, () => ({
      x: random(),
      y: random(),
      rx: 0.12 + random() * 0.22,
      ry: 0.06 + random() * 0.14,
      rotation: (random() - 0.5) * 0.9,
      color: palette[Math.floor(random() * palette.length)],
      wobble: Array.from({ length: 9 }, () => 0.78 + random() * 0.48),
    }));
    const specks = Array.from({ length: 260 }, () => ({
      x: random(),
      y: random(),
      size: 0.7 + random() * 2.8,
      alpha: 0.05 + random() * 0.13,
      warm: random() > 0.46,
    }));
    const debris = [];
    let attempts = 0;
    while (debris.length < 88 && attempts < 260) {
      attempts += 1;
      const x = random() * (grid.width_cells + 1.6) - 0.8;
      const y = random() * (grid.height_cells + 1.6) - 0.8;
      const cell = { x: Math.round(x), y: Math.round(y) };
      if (!isCellInGrid(cell)) continue;
      if (distanceToPath(cell) < 1.15 || slotAt(cell) || objectiveAtCell(cell)) continue;
      debris.push({
        x,
        y,
        dx: (random() - 0.5) * 0.62,
        dy: (random() - 0.5) * 0.62,
        size: 0.55 + random() * 1.4,
        rotation: random() * Math.PI,
        kind: random() < 0.52 ? "stone" : random() < 0.82 ? "reed" : "scrap",
        shade: random(),
      });
    }
    const darkPools = [];
    attempts = 0;
    while (darkPools.length < 9 && attempts < 180) {
      attempts += 1;
      const x = random() * grid.width_cells;
      const y = random() * grid.height_cells;
      const cell = { x: Math.round(x), y: Math.round(y) };
      if (!isCellInGrid(cell)) continue;
      if (distanceToPath(cell) < 1.05 || objectiveAtCell(cell)) continue;
      darkPools.push({
        x,
        y,
        rx: 0.34 + random() * 0.52,
        ry: 0.18 + random() * 0.28,
        rotation: (random() - 0.5) * 0.7,
        alpha: 0.12 + random() * 0.12,
      });
    }
    const landmarks = [];
    const landmarkKinds = ["collapsed_wall", "signal_scrap", "supply_cache", "lamp_relic"];
    attempts = 0;
    while (landmarks.length < 14 && attempts < 260) {
      attempts += 1;
      const x = Math.floor(random() * grid.width_cells);
      const y = Math.floor(random() * grid.height_cells);
      const cell = { x, y };
      if (!isCellInGrid(cell)) continue;
      if (distanceToPath(cell) < 1.2 || slotAt(cell) || objectiveAtCell(cell)) continue;
      landmarks.push({
        x: x + (random() - 0.5) * 0.42,
        y: y + (random() - 0.5) * 0.42,
        kind: landmarkKinds[Math.floor(random() * landmarkKinds.length)],
        scale: 0.78 + random() * 0.48,
        rotation: (random() - 0.5) * 0.45,
        warm: random() > 0.58,
      });
    }
    const wisps = Array.from({ length: 12 }, () => ({
      edge: Math.floor(random() * 4),
      offset: random(),
      sway: random(),
      width: 38 + random() * 88,
      alpha: 0.035 + random() * 0.045,
    }));
    const features = {
      key,
      seed,
      profile,
      bands,
      patches,
      specks,
      debris,
      darkPools,
      landmarks,
      scenicRidges: buildScenicRidges(random, grid),
      fieldEdgeProps: buildFieldEdgeProps(random),
      wisps,
      roadsideProps: buildRoadsideProps(random, profile),
      accessTrails: buildSlotAccessTrails(),
    };
    if (battle) battle.terrainFeatureSet = features;
    return features;
  }

  return {
    battleNodeVisualProfile,
    hashString: hashSceneryString,
    makeSeededRandom: createSeededRandom,
    runtimeMapSeed,
    terrainFeatureSet,
  };
}
