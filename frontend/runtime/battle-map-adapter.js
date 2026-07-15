import {
  allPathRoutesFromRuntime,
  mapGridFromRuntime,
  mapObjectivesFromRuntime,
  normalizeMapTarget,
  pathWaypointsFromRuntime,
  runtimeSemanticList,
} from "./map-runtime-accessors.js";
import {
  distanceToPath as distanceToPathRule,
  enemyWaypoints as enemyWaypointsRule,
  isOccupied as isOccupiedRule,
  pathCells as pathCellsRule,
  routeForSpawn as routeForSpawnRule,
  routePointAtT as routePointAtTRule,
  routeSamplesBetween as routeSamplesBetweenRule,
  slotAt as slotAtRule,
} from "./battle-rules.js";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function createBattleMapAdapter({
  getBattle,
  getMapPackage,
  getBattleConfig,
} = {}) {
  const dependencies = { getBattle, getMapPackage, getBattleConfig };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleMapAdapter requires ${name}`);
    }
  }

  function mapPackage() {
    return getMapPackage() || {};
  }

  function battleConfig() {
    return getBattleConfig() || {};
  }

  function mapGrid() {
    return mapGridFromRuntime({ mapPackage: mapPackage(), battleConfig: battleConfig() });
  }

  function mapObjectives() {
    return mapObjectivesFromRuntime({ mapPackage: mapPackage(), battleConfig: battleConfig() });
  }

  function normalizeTarget(target, fallbackId) {
    return normalizeMapTarget(target, fallbackId);
  }

  function buildSlots() {
    return Array.isArray(mapPackage().build_slots) ? mapPackage().build_slots : [];
  }

  function mapResourceNodes() {
    return runtimeSemanticList(mapPackage(), "resource_nodes");
  }

  function mapHazardZones() {
    return runtimeSemanticList(mapPackage(), "hazard_zones");
  }

  function mapDefenseAnchors() {
    return runtimeSemanticList(mapPackage(), "defense_anchors");
  }

  function mapBlockedAreas() {
    return runtimeSemanticList(mapPackage(), "blocked_areas");
  }

  function pathWaypoints(routeId = null) {
    return pathWaypointsFromRuntime({
      mapPackage: mapPackage(),
      battleConfig: battleConfig(),
      routeId,
    });
  }

  function allPathRoutes() {
    return allPathRoutesFromRuntime({ mapPackage: mapPackage(), battleConfig: battleConfig() });
  }

  function pathCells() {
    return pathCellsRule(allPathRoutes());
  }

  function distanceToPath(cell) {
    return distanceToPathRule(cell, pathCells());
  }

  function routeForSpawn(spawnIndex) {
    return routeForSpawnRule(spawnIndex, allPathRoutes(), mapPackage().spawn_points || []);
  }

  function enemyWaypoints(enemy) {
    return enemyWaypointsRule(enemy, pathWaypoints);
  }

  function routePointAtT(route, t) {
    return routePointAtTRule(route, t);
  }

  function routeSamplesBetween(route, startT, endT, count = 7) {
    return routeSamplesBetweenRule(route, startT, endT, count);
  }

  function slotAt(cell) {
    return slotAtRule(cell, buildSlots);
  }

  function isOccupied(cell) {
    return isOccupiedRule(cell, getBattle());
  }

  function isCellInGrid(cell) {
    const grid = mapGrid();
    return Boolean(
      cell &&
      cell.x >= 0 &&
      cell.y >= 0 &&
      cell.x < grid.width_cells &&
      cell.y < grid.height_cells,
    );
  }

  function rawProject(x, y, tileW, tileH) {
    return {
      x: (x - y) * (tileW / 2),
      y: (x + y) * (tileH / 2),
    };
  }

  function battleCanvasSafeArea(width, height) {
    if (width <= 760) {
      const top = Math.min(116, height * 0.14);
      const bottom = Math.min(156, height * 0.19);
      return { left: 8, right: 8, top, bottom, mapShiftY: -46 };
    }
    if (width <= 1120) {
      return { left: 78, right: 24, top: 92, bottom: 110, mapShiftY: 8 };
    }
    return { left: 76, right: 76, top: 86, bottom: 112, mapShiftY: 10 };
  }

  function battleFitLogicalPoints() {
    const grid = mapGrid();
    const maxX = Math.max(0, grid.width_cells - 1);
    const maxY = Math.max(0, grid.height_cells - 1);
    const points = [
      { x: -0.9, y: -0.9 },
      { x: maxX + 0.9, y: -0.9 },
      { x: -0.9, y: maxY + 0.9 },
      { x: maxX + 0.9, y: maxY + 0.9 },
    ];
    for (const route of allPathRoutes()) points.push(...(route.waypoints || []));
    for (const slot of buildSlots()) {
      if (slot.position) points.push(slot.position);
    }
    const objectives = mapObjectives();
    if ((objectives.core_target || {}).position) points.push(objectives.core_target.position);
    for (const target of objectives.optional_targets || []) {
      if (target.position) points.push(target.position);
    }
    for (const spawn of mapPackage().spawn_points || []) {
      if (spawn.position) points.push(spawn.position);
    }
    return points;
  }

  function battleFitBounds(tileW, tileH) {
    const marginX = tileW * 0.58;
    const marginY = tileH * 1.54;
    const points = battleFitLogicalPoints().map((point) => rawProject(point.x, point.y, tileW, tileH));
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const minX = Math.min(...xs) - marginX;
    const maxX = Math.max(...xs) + marginX;
    const minY = Math.min(...ys) - marginY;
    const maxY = Math.max(...ys) + marginY;
    return {
      minX,
      maxX,
      minY,
      maxY,
      width: maxX - minX,
      height: maxY - minY,
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2,
    };
  }

  function computeBattleMetrics(width, height) {
    const grid = mapGrid();
    const baseWidth = 1280;
    const baseHeight = 720;
    const sum = grid.width_cells + grid.height_cells;
    const baseTileW = clamp(
      Math.min(((baseWidth - 80) * 2) / sum, ((baseHeight - 110) * 4) / sum),
      38,
      112,
    );
    const baseTileH = baseTileW * 0.52;
    const raw = [
      rawProject(0, 0, baseTileW, baseTileH),
      rawProject(grid.width_cells - 1, 0, baseTileW, baseTileH),
      rawProject(0, grid.height_cells - 1, baseTileW, baseTileH),
      rawProject(grid.width_cells - 1, grid.height_cells - 1, baseTileW, baseTileH),
    ];
    const minX = Math.min(...raw.map((point) => point.x));
    const maxX = Math.max(...raw.map((point) => point.x));
    const minY = Math.min(...raw.map((point) => point.y));
    const maxY = Math.max(...raw.map((point) => point.y));
    const safe = battleCanvasSafeArea(width, height);
    const fitBounds = battleFitBounds(baseTileW, baseTileH);
    const availableWidth = Math.max(260, width - safe.left - safe.right);
    const availableHeight = Math.max(220, height - safe.top - safe.bottom);
    const fitScale = Math.min(
      availableWidth / Math.max(1, fitBounds.width),
      availableHeight / Math.max(1, fitBounds.height),
    );
    const coverScale = Math.max(width / baseWidth, height / baseHeight);
    const scale = clamp(Math.min(coverScale * 1.04, fitScale * 1.08), 0.34, 1.34);
    const safeCenterX = safe.left + availableWidth / 2;
    const safeCenterY = safe.top + availableHeight / 2 + safe.mapShiftY;
    const baseOffsetX = (baseWidth - (maxX - minX)) / 2 - minX;
    const baseOffsetY = (baseHeight - (maxY - minY)) / 2 - minY + 6;
    const designFitCenterX = fitBounds.centerX + baseOffsetX;
    const designFitCenterY = fitBounds.centerY + baseOffsetY;
    return {
      width,
      height,
      grid,
      baseWidth,
      baseHeight,
      imageWidth: baseWidth * scale,
      imageHeight: baseHeight * scale,
      scale,
      tileW: baseTileW * scale,
      tileH: baseTileH * scale,
      baseTileW,
      baseTileH,
      baseOffsetX,
      baseOffsetY,
      imageOffsetX: safeCenterX - designFitCenterX * scale,
      imageOffsetY: safeCenterY - designFitCenterY * scale,
      safeArea: safe,
    };
  }

  function projectCell(x, y) {
    const metrics = (getBattle() || {}).metrics;
    if (!metrics) return { x: 0, y: 0 };
    const raw = rawProject(x, y, metrics.baseTileW, metrics.baseTileH);
    return {
      x: metrics.imageOffsetX + (raw.x + metrics.baseOffsetX) * metrics.scale,
      y: metrics.imageOffsetY + (raw.y + metrics.baseOffsetY) * metrics.scale,
    };
  }

  function screenToCell(screenX, screenY) {
    const metrics = (getBattle() || {}).metrics;
    if (!metrics) return null;
    const designX = (screenX - metrics.imageOffsetX) / metrics.scale;
    const designY = (screenY - metrics.imageOffsetY) / metrics.scale;
    const xRaw = designX - metrics.baseOffsetX;
    const yRaw = designY - metrics.baseOffsetY;
    const gridX = yRaw / metrics.baseTileH + xRaw / metrics.baseTileW;
    const gridY = yRaw / metrics.baseTileH - xRaw / metrics.baseTileW;
    return { x: Math.round(gridX), y: Math.round(gridY), fx: gridX, fy: gridY };
  }

  function cellFromCanvasEvent(event) {
    const battle = getBattle();
    if (!battle || !battle.canvas || !battle.metrics) return null;
    const rect = battle.canvas.getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientY < rect.top ||
      event.clientX > rect.right ||
      event.clientY > rect.bottom
    ) {
      return null;
    }
    const cell = screenToCell(event.clientX - rect.left, event.clientY - rect.top);
    return cell && isCellInGrid(cell) ? { x: cell.x, y: cell.y } : null;
  }

  return {
    allPathRoutes,
    battleCanvasSafeArea,
    battleFitBounds,
    battleFitLogicalPoints,
    buildSlots,
    cellFromCanvasEvent,
    computeBattleMetrics,
    distanceToPath,
    enemyWaypoints,
    isCellInGrid,
    isOccupied,
    mapBlockedAreas,
    mapDefenseAnchors,
    mapGrid,
    mapHazardZones,
    mapObjectives,
    mapResourceNodes,
    normalizeTarget,
    pathCells,
    pathWaypoints,
    projectCell,
    rawProject,
    routeForSpawn,
    routePointAtT,
    routeSamplesBetween,
    screenToCell,
    slotAt,
  };
}
