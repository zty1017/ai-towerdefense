function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function cellInGrid(cell, grid) {
  return (
    Boolean(cell) &&
    Boolean(grid) &&
    cell.x >= 0 &&
    cell.y >= 0 &&
    cell.x < grid.width_cells &&
    cell.y < grid.height_cells
  );
}

function resolveSlots(slots) {
  return typeof slots === "function" ? asList(slots()) : asList(slots);
}

export function buildSpawnSchedule(config) {
  let t = 0;
  const schedule = [];
  for (const wave of asList(config && config.waves)) {
    t += wave.delay_before_wave_ms || 0;
    for (let i = 0; i < wave.count; i += 1) {
      schedule.push({ at: t + i * (wave.spawn_interval_ms || 1000), wave });
    }
    t += (wave.count || 0) * (wave.spawn_interval_ms || 1000);
  }
  return schedule;
}

export function routePointAtT(route, t) {
  const waypoints = asList(route && route.waypoints);
  if (!waypoints.length) return null;
  if (waypoints.length === 1) return { x: waypoints[0].x, y: waypoints[0].y };
  const clamped = clamp(Number(t) || 0, 0, 1);
  const segments = [];
  let total = 0;
  for (let i = 0; i < waypoints.length - 1; i += 1) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    const length = Math.hypot((b.x || 0) - (a.x || 0), (b.y || 0) - (a.y || 0));
    if (length <= 0) continue;
    segments.push({ a, b, length });
    total += length;
  }
  if (!segments.length || total <= 0) return { x: waypoints[0].x, y: waypoints[0].y };
  let distance = clamped * total;
  for (const segment of segments) {
    if (distance <= segment.length) {
      const localT = distance / segment.length;
      return {
        x: segment.a.x + (segment.b.x - segment.a.x) * localT,
        y: segment.a.y + (segment.b.y - segment.a.y) * localT,
      };
    }
    distance -= segment.length;
  }
  const last = waypoints[waypoints.length - 1];
  return { x: last.x, y: last.y };
}

export function routeSamplesBetween(route, startT, endT, count = 7) {
  const start = clamp(Number(startT) || 0, 0, 1);
  const end = clamp(Number(endT) || start, start, 1);
  const sampleCount = Math.max(2, count);
  const samples = [];
  for (let i = 0; i < sampleCount; i += 1) {
    const t = start + ((end - start) * i) / (sampleCount - 1);
    const point = routePointAtT(route, t);
    if (point) samples.push(point);
  }
  return samples;
}

export function pathCells(routes) {
  const cells = [];
  for (const route of asList(routes)) {
    const points = asList(route && route.waypoints).map((p) => ({ x: p.x, y: p.y }));
    for (let i = 0; i < points.length - 1; i += 1) {
      const a = points[i];
      const b = points[i + 1];
      const dx = Math.sign(b.x - a.x);
      const dy = Math.sign(b.y - a.y);
      let x = a.x;
      let y = a.y;
      cells.push(`${x},${y}`);
      while (x !== b.x || y !== b.y) {
        if (x !== b.x) x += dx;
        if (y !== b.y) y += dy;
        cells.push(`${x},${y}`);
      }
    }
  }
  return [...new Set(cells)].map((key) => {
    const [x, y] = key.split(",").map(Number);
    return { x, y };
  });
}

export function distanceToPath(cell, cells) {
  const path = asList(cells);
  if (!path.length) return Infinity;
  return Math.min(...path.map((pathCell) => Math.hypot(pathCell.x - cell.x, pathCell.y - cell.y)));
}

export function routeForSpawn(spawnIndex, routes, spawnPoints) {
  const routeList = asList(routes);
  const spawns = asList(spawnPoints).filter((spawn) => spawn.position);
  if (!routeList.length) return null;
  const spawn = spawns.length ? spawns[spawnIndex % spawns.length] : null;
  if (spawn && spawn.route_id) {
    const route = routeList.find((item) => item.route_id === spawn.route_id);
    if (route) return route;
  }
  return routeList[spawnIndex % routeList.length] || routeList[0];
}

export function enemyWaypoints(enemy, pathWaypointsFn) {
  if (typeof pathWaypointsFn !== "function") return [];
  return pathWaypointsFn(enemy && enemy.routeId);
}

export function slotAt(cell, slots) {
  return resolveSlots(slots).find(
    (slot) => slot.position && slot.position.x === cell.x && slot.position.y === cell.y,
  );
}

export function isOccupied(cell, battle) {
  const key = `${cell.x},${cell.y}`;
  return (
    asList(battle && battle.defenses).some((item) => item.key === key) ||
    asList(battle && battle.traps).some((item) => item.key === key && !item.expired)
  );
}

export function canPlaceToolAt({
  tool,
  cell,
  grid,
  occupied,
  slots,
  distanceToPathValue,
  assetKind,
} = {}) {
  if (!cellInGrid(cell, grid) || occupied) return false;
  const slotList = asList(slots);
  if (!slotList.length) {
    const maxDistance = tool === "sample" ? 0.75 : 1.5;
    return distanceToPathValue <= maxDistance;
  }
  const slot = slotAt(cell, slotList);
  if (!slot) return false;
  const allowed = slot.allowed_asset_kinds || [];
  return allowed.includes(assetKind);
}

function projectedCostAmount(toolProjection, fallback) {
  const amount = Number(((toolProjection || {}).cost || {}).amount);
  if (!Number.isFinite(amount)) return fallback;
  return clamp(amount, 0, 999);
}

function projectedCostField(toolProjection) {
  const resource = String((((toolProjection || {}).cost || {}).resource) || "").toLowerCase();
  if (["power", "electricity", "light", "lamp_light"].includes(resource)) return "power";
  return "resources";
}

function canPayProjectedCost(battle, toolProjection, fallbackAmount, fallbackField = "resources") {
  const amount = projectedCostAmount(toolProjection, fallbackAmount);
  const field = toolProjection && toolProjection.cost ? projectedCostField(toolProjection) : fallbackField;
  return Number((battle || {})[field] || 0) >= amount;
}

function cooldownReady(battle, key) {
  return Number(((battle || {}).cooldowns || {})[key] || 0) <= 0;
}

export function toolReady(tool, battle, toolProjection = null) {
  if (tool === "basic") {
    return (
      battle.basicUses > 0 &&
      canPayProjectedCost(battle, toolProjection, 20) &&
      cooldownReady(battle, "basic")
    );
  }
  if (tool === "sample") {
    return battle.sampleDelivered && battle.sampleUses > 0 && cooldownReady(battle, "sample");
  }
  if (tool === "support") {
    return (
      battle.supportUses > 0 &&
      canPayProjectedCost(battle, toolProjection, 15) &&
      cooldownReady(battle, "support")
    );
  }
  if (!toolProjection || toolProjection.locked) return false;
  return canPayProjectedCost(battle, toolProjection, 0) && cooldownReady(battle, toolProjection.id || tool);
}

export function fallbackToolCooldownMs(tool) {
  return tool === "basic" ? 3600 : tool === "sample" ? 1800 : 9000;
}

export function createBattleStateFactory({
  config,
  objectives,
  mapPackage,
  flowVisualSmoke,
  sampleDeliveryMsOverride,
  spawnSchedule,
} = {}) {
  const battleConfig = config || {};
  const battleObjectives = objectives || {};
  const sample = battleConfig.sample_asset || {};
  const defaultSampleDeliveryMs = flowVisualSmoke
    ? Math.min(1800, sample.delivery_delay_ms || 30000)
    : sample.delivery_delay_ms || 30000;
  return {
    config: battleConfig,
    mapPackage,
    elapsedMs: 0,
    speed: flowVisualSmoke ? 4 : 1,
    paused: false,
    enemies: [],
    defenses: [],
    traps: [],
    effects: [],
    resources: 115,
    power: 8,
    coreHp: (battleObjectives.core_target || {}).durability || 10,
    optionalHp: (asList(battleObjectives.optional_targets)[0] || {}).durability || 4,
    leaks: 0,
    kills: 0,
    selectedTool: "basic",
    draggingTool: null,
    dragPointer: null,
    hoverCell: null,
    basicUses: (battleConfig.basic_defense || {}).uses_per_battle || 3,
    sampleUses: 0,
    supportUses: 1,
    sampleDelivered: false,
    sampleDeliveryMs:
      sampleDeliveryMsOverride === undefined ? defaultSampleDeliveryMs : sampleDeliveryMsOverride,
    cooldowns: {
      basic: 0,
      sample: 0,
      support: 0,
    },
    spawned: 0,
    spawnSchedule: spawnSchedule || buildSpawnSchedule(battleConfig),
    finishing: false,
    deployedAssetIds: [],
    selectedObject: null,
    toast: "样品封装中",
    dialogueOpen: false,
    dialogueWasPaused: false,
    metrics: null,
  };
}
