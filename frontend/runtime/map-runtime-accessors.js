function asList(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function battleConfigFromData(data) {
  return asObject(asObject(data).battleConfig);
}

export function activatedRuntimeBundleFromData(data) {
  return asObject(data).activatedRuntimeBundle || null;
}

export function mapRuntimePackageFromData(data) {
  return asObject(asObject(data).mapRuntimePackage);
}

export function mapGridFromRuntime({ mapPackage, battleConfig } = {}) {
  return (
    asObject(mapPackage).grid ||
    asObject(battleConfig).grid || {
      width_cells: 16,
      height_cells: 9,
    }
  );
}

export function normalizeMapTarget(target, fallbackId) {
  const data = asObject(target);
  return {
    target_id: data.target_id || data.stable_internal_id || fallbackId,
    display_name: data.display_name || "防守目标",
    position: data.position || { x: 0, y: 0 },
    durability: data.durability || 1,
  };
}

export function mapObjectivesFromRuntime({ mapPackage, battleConfig } = {}) {
  const fromPackage = asObject(asObject(mapPackage).objectives);
  if (fromPackage.core_target) return fromPackage;
  const config = asObject(battleConfig);
  return {
    core_target: normalizeMapTarget(config.core_target, "target_node_core"),
    optional_targets: asList(config.optional_targets).map((target, index) =>
      normalizeMapTarget(target, `optional_target_${index + 1}`),
    ),
  };
}

export function pathWaypointsFromRuntime({ mapPackage, battleConfig, routeId = null } = {}) {
  const routes = asList(asObject(mapPackage).path_routes);
  const configPaths = asList(asObject(battleConfig).paths);
  const matchedRoute = routeId
    ? routes.find((route) => route.route_id === routeId) ||
      configPaths.find((route) => route.stable_internal_id === routeId)
    : null;
  const firstRoute = matchedRoute || routes[0] || configPaths[0] || {};
  return asList(firstRoute.waypoints).map((p) => ({ x: p.x, y: p.y }));
}

export function allPathRoutesFromRuntime({ mapPackage, battleConfig } = {}) {
  const routes = asList(asObject(mapPackage).path_routes);
  if (routes.length) return routes;
  return asList(asObject(battleConfig).paths).map((route) => ({
    route_id: route.stable_internal_id,
    waypoints: route.waypoints || [],
  }));
}

export function runtimeSemanticList(mapPackage, key) {
  return asList(asObject(mapPackage)[key]);
}

export function mapRenderPlanBundleFromData(data) {
  return asObject(asObject(data).mapRenderPlanBundle);
}

export function mapRenderPlanFromBundle(bundle) {
  return asObject(asObject(bundle).procedural_map_render_plan);
}

export function mapRenderPlanLayersFromPlan(plan) {
  return asList(asObject(plan).layers);
}

export function mapRenderPlanLayerFromPlan(plan, kind) {
  return mapRenderPlanLayersFromPlan(plan).find((layer) => layer && layer.kind === kind) || null;
}

export function mapRenderPlanOperationsFromPlan(plan, kind) {
  const layer = mapRenderPlanLayerFromPlan(plan, kind);
  return asList(layer && layer.operations);
}

export function mapRenderPlanOperationFromPlan(plan, kind, semanticKind, semanticId) {
  return (
    mapRenderPlanOperationsFromPlan(plan, kind).find((operation) => {
      const ref = asObject(operation && operation.semantic_ref);
      return ref.kind === semanticKind && ref.id === semanticId;
    }) || null
  );
}

export function renderGeometryNumber(operation, key, fallback, min, max) {
  const raw = operation && operation.geometry ? operation.geometry[key] : null;
  const value = Number(raw);
  if (!Number.isFinite(value)) return fallback;
  return clamp(value, min, max);
}

export function routeRoadWidthCellsFromPlan(plan, route) {
  const operation = mapRenderPlanOperationFromPlan(
    plan,
    "road_band",
    "path_route",
    (route || {}).route_id || null,
  );
  return renderGeometryNumber(operation, "width_cells", 0.48, 0.42, 0.95);
}

export function routeShoulderWidthScaleFromPlan(plan, route) {
  const operation = mapRenderPlanOperationFromPlan(
    plan,
    "road_edge",
    "path_route",
    (route || {}).route_id || null,
  );
  const widthCells = renderGeometryNumber(operation, "shoulder_width_cells", 0.25, 0.12, 0.44);
  return clamp(widthCells / 0.25, 0.72, 1.58);
}

export function buildSlotPlatformOperationFromPlan(plan, slot) {
  return mapRenderPlanOperationFromPlan(
    plan,
    "build_slot_platform",
    "build_slot",
    (slot || {}).slot_id || null,
  );
}

export function slotFootprintScaleFromPlan(plan, slot, axis) {
  const operation = buildSlotPlatformOperationFromPlan(plan, slot);
  const footprint = operation && operation.geometry ? operation.geometry.footprint : null;
  const raw = footprint && footprint[axis === "height" ? "height_cells" : "width_cells"];
  const value = Number(raw);
  if (!Number.isFinite(value)) return 1;
  return clamp(value, 0.72, 1.45);
}

export function mapStylePackFromBundle(bundle) {
  return asObject(asObject(bundle).map_style_pack);
}

export function mapStylePaletteFromPack(stylePack) {
  return asObject(asObject(stylePack).palette);
}

export function hexToRgbValue(hex) {
  const value = String(hex || "").trim();
  const match = /^#?([0-9a-fA-F]{6})$/.exec(value);
  if (!match) return null;
  const raw = match[1];
  return {
    r: parseInt(raw.slice(0, 2), 16),
    g: parseInt(raw.slice(2, 4), 16),
    b: parseInt(raw.slice(4, 6), 16),
  };
}

export function colorFromStylePack(stylePack, key, fallback) {
  const value = mapStylePaletteFromPack(stylePack)[key];
  return hexToRgbValue(value) ? value : fallback;
}

export function rgbaFromStylePack(stylePack, key, alpha, fallback) {
  const rgb = hexToRgbValue(mapStylePaletteFromPack(stylePack)[key]);
  if (!rgb) return fallback;
  return `rgba(${rgb.r},${rgb.g},${rgb.b},${alpha})`;
}

export function mapRenderPlanHasLayerInPlan(plan, kind) {
  return Boolean(mapRenderPlanLayerFromPlan(plan, kind));
}
