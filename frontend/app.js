import { queryFlag } from "./runtime/api-client.js";
import { createAppFlowOrchestrator } from "./runtime/app-flow-orchestrator.js";
import { DEFAULT_WORLD_CONFIG, NODE_ID } from "./runtime/content-registry.js";
import { createFrontendDataRuntime } from "./runtime/frontend-data-runtime.js";
import { createFrontendMediaCatalog } from "./runtime/frontend-media-catalog.js";
import { createFeatureGateRegistry } from "./runtime/feature-gates.js";
import { createNarrativeFeatureProjection } from "./runtime/narrative-feature-projection.js";
import { createOnboardingFeatureController } from "./runtime/onboarding-feature-controller.js";
import { createRootEventRouter } from "./runtime/root-event-router.js";
import { createSettlementFeatureController } from "./runtime/settlement-feature-controller.js";
import { createWorkshopFeatureController } from "./runtime/workshop-feature-controller.js";
import {
  createStrategicMapController,
  STRATEGIC_MAP_MAX_ZOOM,
  STRATEGIC_MAP_MIN_ZOOM,
} from "./runtime/strategic-map-controller.js";
import { createStrategicMapFeatureController } from "./runtime/strategic-map-feature-controller.js";
import { createStrategicMapProjection } from "./runtime/strategic-map-projection.js";
import {
  buildSpawnSchedule as buildSpawnScheduleRule,
  canPlaceToolAt as canPlaceToolAtRule,
  createBattleStateFactory,
  fallbackToolCooldownMs as fallbackToolCooldownMsRule,
  toolReady as toolReadyRule,
} from "./runtime/battle-rules.js";
import {
  assetKindForToolId,
  buildBattleToolProjection,
  findBattleToolProjection,
} from "./runtime/runtime-projection-adapter.js";
import {
  activatedRuntimeBundleFromData,
  battleConfigFromData,
  buildSlotPlatformOperationFromPlan,
  colorFromStylePack,
  hexToRgbValue,
  mapRenderPlanBundleFromData,
  mapRenderPlanHasLayerInPlan,
  mapRenderPlanLayerFromPlan,
  mapRenderPlanLayersFromPlan,
  mapRenderPlanOperationFromPlan,
  mapRenderPlanOperationsFromPlan,
  mapRenderPlanFromBundle,
  mapRuntimePackageFromData,
  mapStylePackFromBundle,
  mapStylePaletteFromPack,
  renderGeometryNumber as renderGeometryNumberFromPlan,
  rgbaFromStylePack,
  routeRoadWidthCellsFromPlan,
  routeShoulderWidthScaleFromPlan,
  slotFootprintScaleFromPlan,
} from "./runtime/map-runtime-accessors.js";
import {
  beginToolDrag as handleBeginToolDrag,
  cancelToolDrag as handleCancelToolDrag,
  finishToolDrag as handleFinishToolDrag,
  onBattleCanvasClick as handleBattleCanvasClick,
  onBattleCanvasPointerLeave as handleBattleCanvasPointerLeave,
  onBattleCanvasPointerMove as handleBattleCanvasPointerMove,
  updateToolDrag as handleUpdateToolDrag,
} from "./runtime/battle-input-controller.js";
import { createBattleOrchestrator } from "./runtime/battle-orchestrator.js";
import { createBattleMapAdapter } from "./runtime/battle-map-adapter.js";
import { createBattleDeploymentRenderer } from "./runtime/battle-deployment-renderer.js";
import { createBattleDomController } from "./runtime/battle-dom-controller.js";
import { createBattleEntityRenderer } from "./runtime/battle-entity-renderer.js";
import { createBattleRoadRenderer } from "./runtime/battle-road-renderer.js";
import { createBattleSemanticRenderer } from "./runtime/battle-semantic-renderer.js";
import { createBattleTerrainRenderer } from "./runtime/battle-terrain-renderer.js";
import { createBattleWorldRenderer } from "./runtime/battle-world-renderer.js";
import { drawBattleFrame } from "./runtime/battle-renderer.js";
import {
  addEffect as addBattleEffect,
  addFloating as addBattleFloating,
  advanceBattleStep,
  resolveBattleOutcome,
  spawnEnemies as spawnEnemiesStep,
  updateDefenses as updateDefensesStep,
  updateEffects as updateEffectsStep,
  updateEnemies as updateEnemiesStep,
  updateTraps as updateTrapsStep,
} from "./runtime/battle-simulation.js";
import {
  battleWaveLabel as buildBattleWaveLabel,
  buildBattleHudViewModel,
  buildBattleToolbarViewModel,
  nextWaveText as buildNextWaveText,
  sampleProgressMessage as buildSampleProgressMessage,
  toolCooldownFill as buildToolCooldownFill,
} from "./runtime/battle-hud-view-model.js";
import {
  canPreviewRuntimeToolAt,
  deployRuntimeTool as deployRuntimeToolAction,
  placeBasicDefense as placeBasicDefenseAction,
  placeSampleTrap as placeSampleTrapAction,
  toolUnavailableText as toolUnavailableTextAction,
  useSupportPulse as useSupportPulseAction,
} from "./runtime/battle-actions.js";

(() => {
  "use strict";

  const ROOT = document.getElementById("app");
  const STORE_KEY = "ai_compiled_td_frontend_profile_v1";

  const state = {
    view: "loading",
    dataMode: "loading",
    apiBase: "",
    sessionId: "",
    selectedNodeId: NODE_ID,
    selectedMapNodeId: NODE_ID,
    selectedOptions: {
      creativity_mode: "stable",
      player_origin: "lampwright_apprentice",
      visual_style_id: "old_chinese_lantern_frontier_pseudo3d",
    },
    data: {},
    campaignPrefetch: null,
    profile: {},
    openingIndex: 0,
    intentText: "我想做一个能拖慢影潮的临时装置。",
    research: {
      status: "idle",
      proposal: null,
      proposalIntent: "",
      job: null,
      jobPromise: null,
    },
    battle: null,
    battleOutcome: null,
    settlement: null,
    evidence: null,
    mapCamera: {
      zoom: 1,
      centerX: 640,
      centerY: 360,
    },
    mapCameraMode: "auto",
    mapDrag: null,
    suppressMapClick: false,
  };

  const safeText = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  function loadProfile() {
    try {
      state.profile = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
      state.sessionId = state.profile.sessionId || "";
      state.selectedOptions = {
        ...state.selectedOptions,
        ...(state.profile.selectedOptions || {}),
      };
    } catch {
      state.profile = {};
    }
  }

  function saveProfile(patch = {}) {
    state.profile = {
      ...state.profile,
      sessionId: state.sessionId,
      selectedOptions: state.selectedOptions,
      dataMode: state.dataMode,
      ...patch,
    };
    localStorage.setItem(STORE_KEY, JSON.stringify(state.profile));
  }

  function renderLoading(text = "点灯中") {
    ROOT.innerHTML = `
      <main class="loading-cover">
        <section class="loading-box">
          <div class="loading-ring" aria-hidden="true"></div>
          <h1 class="panel-title">${safeText(text)}</h1>
          <p class="panel-text">正在整理档案与战场素材。</p>
        </section>
      </main>
    `;
  }

  function renderError(text) {
    ROOT.innerHTML = `
      <main class="loading-cover">
        <section class="loading-box">
          <h1 class="panel-title">档案未能展开</h1>
          <p class="panel-text">${safeText(text)}</p>
          <div class="screen-actions" style="justify-content:center;margin-top:16px">
            <button class="primary-button" data-action="boot">重试</button>
          </div>
        </section>
      </main>
    `;
  }

  const dataRuntime = createFrontendDataRuntime({ state, saveProfile, location: window.location });
  const {
    advanceStaticCampaignProgress,
    apiGet,
    apiPost,
    battleDialogueSmokeMode,
    battleVisualHoldMode,
    battleVisualSmokeMode,
    currentNodeDisplayName,
    currentNodeId,
    detectApiBase,
    displayNameForNodeId,
    ensureSession,
    flowVisualSmokeMode,
    isApiMode,
    isCurrentNode,
    loadBattleConfig,
    loadBriefing,
    loadCampaignRoute,
    loadData,
    loadFeatureRuntime,
    loadMap,
    nodePlayable,
    resolveAssetUrl,
    routeCurrent,
    routeNext,
    sessionApiPath,
    staticCampaignComplete,
    staticNodePathsFor,
  } = dataRuntime;
  const mediaCatalog = createFrontendMediaCatalog({
    getData: () => state.data,
    getBattle: () => state.battle,
    getMapRuntimePackage: () => mapRuntimePackage(),
    getCurrentNodeId: () => currentNodeId(),
    resolveAssetUrl: (url) => resolveAssetUrl(url),
    createImage: () => new Image(),
    fallbackNodeId: NODE_ID,
  });
  const featureGateRegistry = createFeatureGateRegistry({
    getBundle: () => activatedRuntimeBundle(),
  });
  const narrativeFeatureProjection = createNarrativeFeatureProjection({
    getSurfaceContributions: (nodeId) =>
      featureGateRegistry.surfaceContributions("narrative", {
        surface: "dialogue_modal",
        nodeId,
      }),
  });
  const strategicMapProjection = createStrategicMapProjection({
    getMapData: () => mapData(),
    getRunWorldState: () => state.data.runWorldState || {},
    getProfile: () => state.profile || {},
    getSelectedNodeId: () => state.selectedMapNodeId,
    getCurrentNodeId: () => currentNodeId(),
    fallbackNodeId: NODE_ID,
    getSurfaceContributions: (nodeId) =>
      featureGateRegistry.surfaceContributions("strategic_map", {
        surface: "strategic_map",
        nodeId,
      }),
  });
  const battleMapAdapter = createBattleMapAdapter({
    getBattle: () => state.battle,
    getMapPackage: () => mapRuntimePackage(),
    getBattleConfig: () => battleConfig(),
  });
  const onboardingFeatureController = createOnboardingFeatureController({
    root: ROOT,
    getState: () => state,
    getWorldConfig: () => worldConfig(),
    defaultWorldConfig: DEFAULT_WORLD_CONFIG,
    screenHeader: (...args) => screenHeader(...args),
    safeText: (value) => safeText(value),
    getProfilePreviewUrl: () =>
      resolveAssetUrl("/assets/map_visual_reference/strategic_region_map_clean_v0_1.png"),
    getWorldPreviewUrl: () => mediaCatalog.layeredMapVisualUrl("composited"),
    getOpeningSceneUrl: (scene) =>
      scene === "player_awakening"
        ? mediaCatalog.layeredMapVisualUrl("composited")
        : resolveAssetUrl("/assets/map_visual_reference/strategic_region_map_clean_v0_1.png"),
    navigate: (view) => setPlayerView(view),
    renderApp: () => render(),
  });
  const workshopFeatureController = createWorkshopFeatureController({
    root: ROOT,
    getState: () => state,
    getBriefing: () => briefingData(),
    getBattleConfig: () => battleConfig(),
    getCurrentNodeId: () => currentNodeId(),
    getCurrentNodeDisplayName: () => currentNodeDisplayName(),
    screenHeader: (...args) => screenHeader(...args),
    safeText: (value) => safeText(value),
    imageTag: (...args) => imageTag(...args),
    npcPortraitUrl: (npcId) => npcPortraitUrl(npcId),
    materialName: (materialId) => materialName(materialId),
    getSurfaceContributions: (nodeId) =>
      featureGateRegistry.surfaceContributions("workshop", {
        surface: "prototype_workshop",
        nodeId,
      }),
  });
  const settlementFeatureController = createSettlementFeatureController({
    root: ROOT,
    getState: () => state,
    getCurrentNodeId: () => currentNodeId(),
    displayNameForNodeId: (nodeId) => displayNameForNodeId(nodeId),
    screenHeader: (...args) => screenHeader(...args),
    safeText: (value) => safeText(value),
    imageTag: (...args) => imageTag(...args),
    npcPortraitUrl: (npcId) => npcPortraitUrl(npcId),
    getSurfaceContributions: (nodeId) =>
      featureGateRegistry.surfaceContributions("settlement", {
        surface: "settlement_panel",
        nodeId,
      }),
  });
  const strategicMapController = createStrategicMapController({
    state,
    root: ROOT,
    getMapData: () => mapData(),
    isNodeVisible: (node) => strategicMapProjection.mapNodeVisible(node),
  });
  const {
    activeStrategicMapCamera,
    beginStrategicMapDrag,
    finishStrategicMapDrag,
    handleStrategicMapWheel,
    resetStrategicMapCamera,
    setStrategicMapCamera,
    strategicMapViewBox,
    updateStrategicMapDrag,
    zoomStrategicMapBy,
  } = strategicMapController;
  const strategicMapFeatureController = createStrategicMapFeatureController({
    root: ROOT,
    projection: strategicMapProjection,
    camera: {
      active: (map) => activeStrategicMapCamera(map),
      set: (camera, options) => setStrategicMapCamera(camera, options),
      viewBox: (camera) => strategicMapViewBox(camera),
      mode: () => state.mapCameraMode,
      minZoom: STRATEGIC_MAP_MIN_ZOOM,
      maxZoom: STRATEGIC_MAP_MAX_ZOOM,
    },
    runtime: {
      currentNodeId: () => currentNodeId(),
      isCurrentNode: (nodeId) => isCurrentNode(nodeId),
      nodePlayable: (nodeId) => nodePlayable(nodeId),
      routeCurrent: () => routeCurrent(),
      routeNext: () => routeNext(),
    },
    presentation: {
      routePath: (from, to) => strategicRoutePath(from, to),
      darkRegionMarkup: (region) => strategicDarkRegionMarkup(region),
      threatEdgeMarkup: (edge) => strategicThreatEdgeMarkup(edge),
      markerPreloadUrls: () => strategicMarkerPreloadUrls(),
      getImage: (url) => getImage(url),
      assetUrl: (url) => assetUrl(url),
      safeText: (value) => safeText(value),
      nodeColor: (kind, stateName) => mapNodeColor(kind, stateName),
      nodeMarkerMarkup: (node, color, stateName) => strategicNodeMarkerMarkup(node, color, stateName),
      nodeLabel: (node, color) => strategicNodeLabel(node, color),
      screenHeader: (...args) => screenHeader(...args),
    },
  });
  const battleOrchestrator = createBattleOrchestrator({
    getBattle: () => state.battle,
    requestFrame: (callback) => window.requestAnimationFrame(callback),
    cancelFrame: (frameId) => window.cancelAnimationFrame(frameId),
    isSimulationHeld: () => battleVisualHoldMode(),
    advanceBattleStep,
    onSampleDelivered: () => handleBattleSampleDelivered(),
    spawnEnemies: ({ battle }) => spawnEnemiesStep({ battle, routeForSpawn, pathWaypoints }),
    updateEnemies: ({ battle, dt }) => updateEnemiesStep({ battle, dt, enemyWaypoints }),
    updateDefenses: ({ battle }) => updateDefensesStep({ battle }),
    updateTraps: ({ battle }) => updateTrapsStep({ battle }),
    updateEffects: ({ battle, dt }) => updateEffectsStep({ battle, dt }),
    resolveBattleOutcome: ({ battle }) =>
      resolveBattleOutcome({ battle, flowVisualSmoke: flowVisualSmokeMode() }),
    finishBattle: (outcome) => finishBattle(outcome),
    drawBattle: () => drawBattle(),
    updateBattleDom: () => updateBattleDom(),
  });
  const battleEntityRenderer = createBattleEntityRenderer({
    getBattle: () => state.battle,
    projectCell: (x, y) => projectCell(x, y),
    mediaSpriteRef: (assetId, role, runtime) => mediaSpriteRef(assetId, role, runtime),
    getImage: (url) => getImage(url),
    resolveToolSpriteRef: (toolId) => battleToolSpriteRef(toolId),
  });
  const battleTerrainRenderer = createBattleTerrainRenderer({
    getBattle: () => state.battle,
    getLayeredBackdropImage: () => layeredMapBackdropImage(),
    terrainFeatureSet: () => terrainFeatureSet(),
    mapGrid: () => mapGrid(),
    runtimeMapSeed: () => runtimeMapSeed(),
    projectCell: (x, y) => projectCell(x, y),
    mapComponentImage: (role, variant) => mapComponentImage(role, variant),
    hashString: (value) => hashString(value),
    makeSeededRandom: (seed) => makeSeededRandom(seed),
  });
  const battleRoadRenderer = createBattleRoadRenderer({
    getBattle: () => state.battle,
    getVisualProfile: () => battleNodeVisualProfile(),
    getRoutes: () => allPathRoutes(),
    projectCell: (x, y) => projectCell(x, y),
    routeRoadWidthCells: (route) => routeRoadWidthCells(route),
    routeShoulderWidthScale: (route) => routeShoulderWidthScale(route),
    runtimeMapSeed: () => runtimeMapSeed(),
    hashString: (value) => hashString(value),
    makeSeededRandom: (seed) => makeSeededRandom(seed),
    drawComponentTextureEllipse: (...args) => drawComponentTextureEllipse(...args),
    terrainFeatureSet: () => terrainFeatureSet(),
  });
  const battleWorldRenderer = createBattleWorldRenderer({
    getBattle: () => state.battle,
    getObjectives: () => mapObjectives(),
    getVisualProfile: () => battleNodeVisualProfile(),
    terrainFeatureSet: () => terrainFeatureSet(),
    projectCell: (x, y) => projectCell(x, y),
    drawComponentTextureEllipse: (...args) => drawComponentTextureEllipse(...args),
    drawGroundGlow: (...args) => drawGroundGlow(...args),
    drawSprite: (...args) => drawSprite(...args),
    drawTowerMuzzle: (...args) => drawTowerMuzzle(...args),
    mapSpriteSize: (...args) => mapSpriteSize(...args),
    mediaSpriteRef: (...args) => mediaSpriteRef(...args),
    resolveBattleObjectSpriteRef: (object) => battleObjectSpriteRef(object),
    hashString: (value) => hashString(value),
  });
  const battleDeploymentRenderer = createBattleDeploymentRenderer({
    getBattle: () => state.battle,
    getSlots: () => buildSlots(),
    isCellInGrid: (cell) => isCellInGrid(cell),
    projectCell: (x, y) => projectCell(x, y),
    makeSeededRandom: (seed) => makeSeededRandom(seed),
    runtimeMapSeed: () => runtimeMapSeed(),
    hashString: (value) => hashString(value),
    slotFootprintScale: (slot, axis) => slotFootprintScale(slot, axis),
    getVisualProfile: () => battleNodeVisualProfile(),
    drawComponentTextureEllipse: (...args) => drawComponentTextureEllipse(...args),
    canPreviewToolAt: (tool, cell) => canPreviewToolAt(tool, cell),
    drawSprite: (...args) => drawSprite(...args),
    drawGroundGlow: (...args) => drawGroundGlow(...args),
    mapSpriteSize: (...args) => mapSpriteSize(...args),
    resolveToolSpriteRef: (toolId) => battleToolSpriteRef(toolId),
    getToolProjection: (toolId) => findBattleToolProjection(toolId, battleToolProjection()),
  });
  const battleSemanticRenderer = createBattleSemanticRenderer({
    getBattle: () => state.battle,
    getResourceNodes: () => mapResourceNodes(),
    getHazardZones: () => mapHazardZones(),
    getDefenseAnchors: () => mapDefenseAnchors(),
    getBlockedAreas: () => mapBlockedAreas(),
    getVisualProfile: () => battleNodeVisualProfile(),
    getRoutes: () => allPathRoutes(),
    projectCell: (x, y) => projectCell(x, y),
    routeSamplesBetween: (...args) => routeSamplesBetween(...args),
    routeRoadWidthCells: (route) => routeRoadWidthCells(route),
    traceRoutePath: (...args) => traceRoutePath(...args),
    drawGroundGlow: (...args) => drawGroundGlow(...args),
    drawComponentTextureEllipse: (...args) => drawComponentTextureEllipse(...args),
    drawCollapsedWall: (...args) => battleWorldRenderer.drawCollapsedWall(...args),
    hashString: (value) => hashString(value),
    isCellInGrid: (cell) => isCellInGrid(cell),
  });
  const battleDomController = createBattleDomController({
    getBattle: () => state.battle,
    ensureBattle: () => {
      state.battle = state.battle || createBattleState();
      return state.battle;
    },
    documentRef: document,
    windowRef: window,
    onCanvasClick: (event) => onBattleCanvasClick(event),
    onCanvasPointerMove: (event) => onBattleCanvasPointerMove(event),
    onCanvasPointerLeave: (event) => onBattleCanvasPointerLeave(event),
    computeMetrics: (width, height) => computeBattleMetrics(width, height),
    installSmokeProbe: () => installBattleSmokeProbe(),
    preloadImages: () => preloadBattleImages(),
    shouldShowInitialDialogue: () => !flowVisualSmokeMode(),
    getInitialDialogue: () =>
      narrativeFeatureProjection.battleIntro(currentNodeId(), {
        name: "灰灯驿站守灯人",
        line: "第一波很快就会撞进来。样品还在封装，先用基础灯栏争取时间。",
        portraitId: "npc_gray_lantern_keeper_portrait",
      }),
    resolvePortraitUrl: (portraitId) =>
      mediaUrl(portraitId, "portrait", true) || mediaUrl(portraitId, "icon", true),
    buildHudViewModel: () => battleHudViewModel(),
    renderToolbar: (tools) => battleToolsMarkup(tools),
    imageTag: (url, alt) => imageTag(url, alt),
    safeText: (value) => safeText(value),
    startLoop: () => battleOrchestrator.start(),
    stopLoop: () => battleOrchestrator.stop(),
  });
  const appFlowOrchestrator = createAppFlowOrchestrator({
    getView: () => state.view,
    setView: (view) => {
      state.view = view;
    },
    stopCurrentActivity: () => stopBattleLoop(),
    renderers: {
      loading: () => renderLoading(),
      profile: () => renderProfile(),
      "world-config": () => renderWorldConfig(),
      opening: () => renderOpening(),
      map: () => renderMap(),
      workshop: () => renderWorkshop(),
      battle: () => renderBattle(),
      settlement: () => renderSettlement(),
    },
  });

  function requestNextPrefetch() {
    if (!isApiMode()) return;
    apiPost(sessionApiPath("/campaign-router/prefetch-next"), {}, 2600)
      .then((response) => {
        state.campaignPrefetch = response.prefetch_request || null;
        if (response.campaign_router) {
          state.data.campaignRouter = response.campaign_router;
          const nodeId = (response.campaign_router.current || {}).node_id;
          if (nodeId) state.selectedNodeId = nodeId;
        }
      })
      .catch(() => {
        state.campaignPrefetch = { status: "silent_fallback" };
      });
  }

  async function boot() {
    renderLoading();
    loadProfile();
    state.apiBase = await detectApiBase();
    state.dataMode = state.apiBase ? "api" : "static";
    try {
      await loadData();
      saveProfile();
      if (battleVisualSmokeMode() || battleDialogueSmokeMode()) {
        saveProfile({ worldCreated: true, completedBattle: false });
        state.battle = null;
        setPlayerView("battle");
        render();
        return;
      }
      setPlayerView("profile");
      render();
    } catch (error) {
      if (isApiMode()) {
        try {
          state.dataMode = "static";
          state.apiBase = "";
          await loadData();
          saveProfile();
          setPlayerView("profile");
          render();
          return;
        } catch {
          // Fall through to the user-safe error below.
        }
      }
      renderError("请确认已从仓库根目录启动静态服务，或先启动中枢服务。");
    }
  }

  function dataBadge() {
    const local = state.dataMode !== "api";
    return `
      <div class="status-pill">
        <i class="status-dot ${local ? "local" : ""}"></i>
        <span>${local ? "本机档案" : "中枢档案"}</span>
      </div>
    `;
  }

  function screenHeader(title, subtitle, eyebrow = "长夜灯火") {
    return `
      <header class="screen-header">
        <div class="brand-stack">
          <div class="eyebrow">${safeText(eyebrow)}</div>
          <h1 class="screen-title">${safeText(title)}</h1>
          ${subtitle ? `<p class="screen-subtitle">${safeText(subtitle)}</p>` : ""}
        </div>
        ${dataBadge()}
      </header>
    `;
  }

  function worldConfig() {
    return state.data.worldConfig || DEFAULT_WORLD_CONFIG;
  }

  function mapData() {
    return state.data.map || {};
  }

  function briefingData() {
    return state.data.briefing || {};
  }

  function battleConfig() {
    return battleConfigFromData(state.data);
  }

  function activatedRuntimeBundle() {
    return activatedRuntimeBundleFromData(state.data);
  }

  function mapRuntimePackage() {
    return mapRuntimePackageFromData(state.data);
  }

  function mapGrid() {
    return battleMapAdapter.mapGrid();
  }

  function mapObjectives() {
    return battleMapAdapter.mapObjectives();
  }

  function normalizeTarget(target, fallbackId) {
    return battleMapAdapter.normalizeTarget(target, fallbackId);
  }

  function assetUrl(url) {
    return mediaCatalog.assetUrl(url);
  }

  function mediaUrl(assetId, role, runtime = false) {
    return mediaCatalog.mediaUrl(assetId, role, runtime);
  }

  function mediaSpriteRef(assetId, role, runtime = false) {
    return mediaCatalog.mediaSpriteRef(assetId, role, runtime);
  }

  function battleObjectSpriteRef(object = {}) {
    return mediaCatalog.battleObjectSpriteRef(object);
  }

  function battleToolSpriteRef(toolId) {
    const tool = findBattleToolProjection(toolId, battleToolProjection());
    return battleObjectSpriteRef(tool || { id: toolId, objectId: toolId });
  }

  function battleObjectPreloadUrls() {
    const objects = featureGateRegistry.capabilityList("battle_objects", "battle");
    return mediaCatalog.battleObjectPreloadUrls(objects);
  }

  function mediaPreloadUrls(assetId, role, runtime = false) {
    return mediaCatalog.mediaPreloadUrls(assetId, role, runtime);
  }

  function mapVisualUrl(role, options = {}) {
    return mediaCatalog.mapVisualUrl(role, options);
  }

  function mapComponentImage(role, variant = 0) {
    return mediaCatalog.mapComponentImage(role, variant);
  }

  function mapComponentPreloadUrls() {
    return mediaCatalog.mapComponentPreloadUrls();
  }

  function strategicMarkerAtlas() {
    return mediaCatalog.strategicMarkerAtlas();
  }

  function strategicMarkerItem(kind, stateName) {
    return mediaCatalog.strategicMarkerItem(kind, stateName);
  }

  function strategicMarkerPreloadUrls() {
    return mediaCatalog.strategicMarkerPreloadUrls();
  }

  function layeredMapBackdropImage() {
    return mediaCatalog.layeredMapBackdropImage();
  }

  function layeredMapBackdropReady() {
    return imageRenderable(layeredMapBackdropImage());
  }

  function layeredMapVisualPreloadUrls() {
    return mediaCatalog.layeredMapVisualPreloadUrls();
  }

  function mapRenderPlanBundle() {
    return mapRenderPlanBundleFromData(state.data);
  }

  function mapRenderPlan() {
    return mapRenderPlanFromBundle(mapRenderPlanBundle());
  }

  function mapRenderPlanLayers() {
    return mapRenderPlanLayersFromPlan(mapRenderPlan());
  }

  function mapRenderPlanLayer(kind) {
    return mapRenderPlanLayerFromPlan(mapRenderPlan(), kind);
  }

  function mapRenderPlanOperations(kind) {
    return mapRenderPlanOperationsFromPlan(mapRenderPlan(), kind);
  }

  function mapRenderPlanOperation(kind, semanticKind, semanticId) {
    return mapRenderPlanOperationFromPlan(mapRenderPlan(), kind, semanticKind, semanticId);
  }

  function renderGeometryNumber(operation, key, fallback, min, max) {
    return renderGeometryNumberFromPlan(operation, key, fallback, min, max);
  }

  function routeRoadWidthCells(route) {
    return routeRoadWidthCellsFromPlan(mapRenderPlan(), route);
  }

  function routeShoulderWidthScale(route) {
    return routeShoulderWidthScaleFromPlan(mapRenderPlan(), route);
  }

  function buildSlotPlatformOperation(slot) {
    return buildSlotPlatformOperationFromPlan(mapRenderPlan(), slot);
  }

  function slotFootprintScale(slot, axis) {
    return slotFootprintScaleFromPlan(mapRenderPlan(), slot, axis);
  }

  function mapStylePack() {
    return mapStylePackFromBundle(mapRenderPlanBundle());
  }

  function mapStylePalette() {
    return mapStylePaletteFromPack(mapStylePack());
  }

  function hexToRgb(hex) {
    return hexToRgbValue(hex);
  }

  function colorFromStyle(key, fallback) {
    return colorFromStylePack(mapStylePack(), key, fallback);
  }

  function rgbaFromStyle(key, alpha, fallback) {
    return rgbaFromStylePack(mapStylePack(), key, alpha, fallback);
  }

  function mapRenderPlanHasLayer(kind) {
    return mapRenderPlanHasLayerInPlan(mapRenderPlan(), kind);
  }

  function allowsDebugMapVisuals() {
    const params = new URLSearchParams(window.location.search);
    return ["mapVisualDebug", "debugMapVisuals", "evidence"].some((key) =>
      ["1", "true", "yes"].includes((params.get(key) || "").toLowerCase()),
    );
  }

  function debugBattleMapVisualUrls() {
    if (!allowsDebugMapVisuals()) return [];
    return [
      mapVisualUrl("battle_reference_board"),
      mapVisualUrl("battle_control_sketch"),
    ].filter(Boolean);
  }

  function imageTag(url, alt) {
    if (!url) return `<span aria-hidden="true">✦</span>`;
    return `<img src="${safeText(url)}" alt="${safeText(alt)}" loading="lazy" />`;
  }

  function getImage(url) {
    return mediaCatalog.getImage(url);
  }

  function render() {
    return appFlowOrchestrator.renderCurrent();
  }

  function setPlayerView(view) {
    return appFlowOrchestrator.setCurrentView(view);
  }

  function renderProfile() {
    onboardingFeatureController.renderProfile();
  }

  function renderWorldConfig() {
    onboardingFeatureController.renderWorldConfig();
  }

  function openingSegment() {
    return onboardingFeatureController.openingSegment();
  }

  function renderOpening() {
    onboardingFeatureController.renderOpening();
  }

  function mapNodeColor(kind, stateName) {
    if (stateName === "secured") return "#92d28a";
    if (kind === "battle_hotspot") return "#ee7568";
    if (kind === "main_city") return "#f0bd58";
    if (kind === "research_facility") return "#76d8ca";
    if (kind === "resource_storage") return "#a5ce78";
    if (kind === "route_facility") return "#d8b46a";
    if (kind === "scouting_point") return "#98a9e8";
    return "#d8c58a";
  }

  function strategicRoutePath(from, to) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const bend = clamp(Math.hypot(dx, dy) * 0.18, 44, 96);
    const c1x = from.x + dx * 0.34;
    const c1y = from.y + dy * 0.18 - bend;
    const c2x = from.x + dx * 0.70;
    const c2y = from.y + dy * 0.82 + bend * 0.26;
    return `M ${from.x} ${from.y} C ${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${to.x} ${to.y}`;
  }

  function strategicNodeGlyph(node, color, stateName) {
    const x = Number(node.position.x) || 0;
    const y = Number(node.position.y) || 0;
    const kind = node.kind || "node";
    const controlled = stateName === "controlled" || stateName === "secured";
    const scale = kind === "main_city" ? 1.12 : kind === "battle_hotspot" ? 1.04 : 0.92;
    const active = node.stable_internal_id === currentNodeId();
    const symbolOpacity = controlled ? ".92" : ".78";
    const base = `
      <g class="strategic-node-marker" transform="translate(${x} ${y}) scale(${scale})">
        <ellipse class="node-ground" cx="0" cy="14" rx="28" ry="10" />
        <circle class="node-halo" cx="0" cy="0" r="${active ? 29 : 25}" fill="${color}" />
        <circle class="node-ring" cx="0" cy="0" r="20" stroke="${color}" />
        <circle class="node-core" cx="0" cy="0" r="13" fill="${color}" />
    `;
    if (kind === "main_city") {
      return `
        ${base}
        <path class="node-symbol" d="M -8 -7 H 8 M -5 9 H 5 M -6 -7 L -4 8 H 4 L 6 -7 M -9 0 H 9" opacity="${symbolOpacity}" />
        <path class="node-flame" d="M 0 -2 C -4 2 -2 7 0 9 C 4 6 4 2 0 -2 Z" />
      </g>
      `;
    }
    if (kind === "battle_hotspot") {
      return `
        ${base}
        <path class="node-symbol" d="M -10 8 L 0 -10 L 10 8 M 0 -4 V 2 M 0 7 V 8" opacity="${symbolOpacity}" />
        <path class="node-alert" d="M -15 12 Q 0 19 15 12" />
      </g>
      `;
    }
    if (kind === "research_facility") {
      return `
        ${base}
        <path class="node-symbol" d="M -10 6 H 10 M -7 6 L -5 -9 H 5 L 7 6 M -5 -2 H 5 M -2 -9 V -13 H 8" opacity="${symbolOpacity}" />
      </g>
      `;
    }
    if (kind === "resource_storage") {
      return `
        ${base}
        <path class="node-symbol" d="M -9 -6 Q 0 -11 9 -6 V 7 Q 0 12 -9 7 Z M -9 -6 Q 0 0 9 -6 M -6 4 H 6" opacity="${symbolOpacity}" />
      </g>
      `;
    }
    if (kind === "route_facility") {
      return `
        ${base}
        <path class="node-symbol" d="M -12 5 C -5 -7 5 -7 12 5 M -8 8 H 8 M -4 1 H 4 M -1 -9 V 10" opacity="${symbolOpacity}" />
      </g>
      `;
    }
    if (kind === "scouting_point") {
      return `
        ${base}
        <path class="node-symbol" d="M -12 2 Q 0 -10 12 2 Q 0 12 -12 2 Z M 0 -3 A 5 5 0 1 1 0 7 A 5 5 0 1 1 0 -3" opacity="${symbolOpacity}" />
      </g>
      `;
    }
    return `
      ${base}
      <circle class="node-symbol-fill" cx="0" cy="0" r="5" opacity="${controlled ? ".85" : ".62"}" />
    </g>
    `;
  }

  function strategicNodeMarkerMarkup(node, color, stateName) {
    const atlas = strategicMarkerAtlas();
    const item = strategicMarkerItem(node.kind || "generic", stateName);
    const frame = (item && item.atlas_frame) || {};
    if (!atlas || !item || !frame.width || !frame.height) {
      return strategicNodeGlyph(node, color, stateName);
    }
    const frameWidth = Math.max(1, Number(frame.width) || 1);
    const frameHeight = Math.max(1, Number(frame.height) || 1);
    const displayWidth = Math.max(1, Number(frame.display_width) || 40);
    const displayHeight = Math.max(1, Number(frame.display_height) || displayWidth);
    const anchorX = displayWidth * (Math.max(0, Number(frame.anchor_x) || 0) / frameWidth);
    const anchorY = displayHeight * (Math.max(0, Number(frame.anchor_y) || 0) / frameHeight);
    const x = (Number(node.position.x) || 0) - anchorX;
    const y = (Number(node.position.y) || 0) - anchorY;
    return `
      <svg class="strategic-node-marker strategic-node-marker--atlas" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${displayWidth.toFixed(2)}" height="${displayHeight.toFixed(2)}" viewBox="${Number(frame.x) || 0} ${Number(frame.y) || 0} ${frameWidth} ${frameHeight}" overflow="hidden" aria-hidden="true">
        <image href="${safeText(assetUrl(atlas.url))}" x="0" y="0" width="${Number(atlas.width) || frameWidth}" height="${Number(atlas.height) || frameHeight}" preserveAspectRatio="none" />
      </svg>
    `;
  }

  function strategicNodeLabel(node, color) {
    const x = Number(node.position.x) || 0;
    const y = Number(node.position.y) || 0;
    const text = safeText(node.display_name || "节点");
    const width = Math.max(88, Math.min(158, String(node.display_name || "").length * 17 + 42));
    const placeLeft = x > 1010;
    const labelX = placeLeft ? x - width - 34 : x + 34;
    const labelY = y - 28;
    return `
      <g class="map-node-label" transform="translate(${labelX} ${labelY})">
        <path d="M ${placeLeft ? width : 0} 27 L ${x - labelX} ${y - labelY + 6}" stroke="${color}" stroke-opacity=".32" stroke-width="1.5" stroke-linecap="round" />
        <rect x="0" y="0" width="${width}" height="34" rx="7" fill="rgba(6,10,8,.66)" stroke="${color}" stroke-opacity=".32" />
        <text x="14" y="25">${text}</text>
      </g>
    `;
  }

  function strategicDarkRegionMarkup(region) {
    const id = String(region.stable_internal_id || "");
    if (id.includes("north")) {
      return `
        <path class="map-dark-region" filter="url(#strategicRegionBlur)" d="M -40 -30 H 1320 V 120 C 1080 178 890 132 682 170 C 464 210 244 154 -40 198 Z" />
      `;
    }
    const points = (region.polygon || []).filter(Boolean);
    const xs = points.map((point) => Number(point.x) || 0);
    const ys = points.map((point) => Number(point.y) || 0);
    const cx = xs.length ? xs.reduce((sum, value) => sum + value, 0) / xs.length : 1040;
    const cy = ys.length ? ys.reduce((sum, value) => sum + value, 0) / ys.length : 610;
    return `
      <ellipse class="map-dark-region" filter="url(#strategicRegionBlur)" cx="${cx}" cy="${cy}" rx="310" ry="150" />
    `;
  }

  function strategicThreatEdgeMarkup(edge) {
    const x = Number(edge && edge.position ? edge.position.x : 0) || 0;
    const y = Number(edge && edge.position ? edge.position.y : 0) || 0;
    const severity = safeText(edge.severity || "unknown");
    return `
      <g class="map-threat-edge map-threat-edge--${severity}" transform="translate(${x} ${y}) rotate(-8)">
        <ellipse class="map-threat-fog map-threat-fog--outer" cx="0" cy="0" rx="176" ry="78" />
        <ellipse class="map-threat-fog map-threat-fog--inner" cx="-10" cy="-5" rx="118" ry="48" />
        <ellipse class="map-threat-ash" cx="-68" cy="18" rx="7" ry="2.4" />
        <ellipse class="map-threat-ash" cx="-14" cy="-18" rx="5" ry="1.8" />
        <ellipse class="map-threat-ash" cx="54" cy="10" rx="8" ry="2.2" />
      </g>
    `;
  }

  function selectedMapNode() {
    return strategicMapProjection.selectedMapNode();
  }

  function renderMap() {
    strategicMapFeatureController.renderMap();
  }

  function materialName(id) {
    const names = {
      lamp_shard: "灯芯碎片",
      conductor_filament: "导线丝",
      lamp_oil: "灯油",
      iron_scrap: "铁料",
      rationed_food: "口粮",
      lantern_ash: "灯灰",
      glow_crystal: "辉晶",
    };
    return names[id] || id;
  }

  function npcPortraitUrl(npcId) {
    if (npcId === "npc_workshop_mentor") {
      return mediaUrl("npc_workshop_mentor_portrait", "portrait", true);
    }
    return mediaUrl("npc_gray_lantern_keeper_portrait", "portrait", true);
  }

  function sampleIconUrl() {
    const sample = state.data.sampleDeliveryAsset;
    if (!sample) return "";
    const sampleId = sample.stable_internal_id;
    return mediaUrl(sampleId, "icon", false) || mediaUrl(sampleId, "ui_card", false);
  }

  function currentProposal() {
    return workshopFeatureController.currentProposal();
  }

  function renderWorkshop() {
    workshopFeatureController.renderWorkshop();
  }

  async function beginWorld() {
    renderLoading("点亮本局档案");
    saveProfile({ selectedOptions: state.selectedOptions });
    if (isApiMode()) {
      try {
        const response = await apiPost(
          sessionApiPath("/world-instance"),
          { selected_options: state.selectedOptions },
          5000,
        );
        state.data.worldInstance = response.world_instance;
        state.data.runWorldState = response.run_world_state;
      } catch {
        // Continue with loaded fixture content if the write path is unavailable.
      }
    }
    saveProfile({ worldCreated: true, completedBattle: false, staticCampaignStageIndex: 0 });
    state.openingIndex = 0;
    setPlayerView("opening");
    render();
  }

  async function startNewArchive() {
    localStorage.removeItem(STORE_KEY);
    state.sessionId = "";
    state.profile = {};
    state.selectedOptions = {
      creativity_mode: "stable",
      player_origin: "lampwright_apprentice",
      visual_style_id: "old_chinese_lantern_frontier_pseudo3d",
    };
    state.research = {
      status: "idle",
      proposal: null,
      proposalIntent: "",
      job: null,
      jobPromise: null,
    };
    state.battle = null;
    state.settlement = null;
    state.data.runWorldState = null;
    if (isApiMode()) {
      await ensureSession();
    }
    setPlayerView("world-config");
    render();
  }

  async function resetDemo() {
    renderLoading("重置档案");
    if (isApiMode() && state.sessionId) {
      try {
        await apiPost(sessionApiPath("/reset"), {}, 3000);
      } catch {
        // Resetting local progress is enough for the fallback path.
      }
    }
    saveProfile({ worldCreated: false, completedBattle: false, staticCampaignStageIndex: 0 });
    state.research = {
      status: "idle",
      proposal: null,
      proposalIntent: "",
      job: null,
      jobPromise: null,
    };
    state.battle = null;
    state.settlement = null;
    setPlayerView("profile");
    render();
  }

  async function refreshProposal() {
    const intent = state.intentText.trim() || "我想做一个能拖慢影潮的临时装置。";
    state.research.status = "proposing";
    renderWorkshop();
    if (isApiMode()) {
      try {
        await createResearchProposal(intent);
      } catch {
        state.research.proposal = null;
        state.research.proposalIntent = "";
      }
    } else {
      await sleep(260);
    }
    state.research.status = "proposed";
    if (state.view === "workshop") renderWorkshop();
  }

  async function createResearchProposal(intent) {
    const proposal = await apiPost(
      sessionApiPath("/research/proposals"),
      { intent_text: intent, node_id: currentNodeId() },
      4200,
    );
    state.research.proposal = proposal;
    state.research.proposalIntent = intent;
    await loadFeatureRuntime(currentNodeId());
    return proposal;
  }

  async function enterCurrentNode() {
    renderLoading("整理节点");
    if (isApiMode()) {
      try {
        await loadCampaignRoute();
      } catch {
        // Keep the last known route.
      }
    }
    const selected = selectedMapNode();
    if (selected && isCurrentNode(selected.stable_internal_id)) {
      state.selectedNodeId = selected.stable_internal_id;
    }
    try {
      await Promise.all([loadBriefing(), loadBattleConfig()]);
    } catch {
      // Static fallback content is already loaded.
    }
    if (state.data.suggestedInput) {
      state.intentText = state.data.suggestedInput;
    }
    requestNextPrefetch();
    setPlayerView("workshop");
    render();
  }

  async function confirmPrototype() {
    state.research.status = "confirming";
    renderWorkshop();
    const intent = state.intentText.trim() || "我想做一个能拖慢影潮的临时装置。";
    if (isApiMode()) {
      try {
        const existingProposal = state.research.proposal;
        const proposal =
          existingProposal &&
          existingProposal.node_id === currentNodeId() &&
          state.research.proposalIntent === intent
            ? existingProposal
            : await createResearchProposal(intent);
        state.research.jobPromise = apiPost(
          sessionApiPath(
            `/research/proposals/${encodeURIComponent(proposal.proposal_id)}/confirm`,
          ),
          {},
          20000,
        )
          .then(async (job) => {
            state.research.job = job;
            await loadFeatureRuntime(currentNodeId());
            return job;
          })
          .catch(() => null);
      } catch {
        state.research.proposal = null;
      }
    }
    state.research.status = "in_progress";
    state.battle = null;
    requestNextPrefetch();
    setPlayerView("battle");
    render();
  }

  function renderBattle() {
    ROOT.innerHTML = `
      <main class="battle-screen">
        <section class="battle-shell">
          <div class="battle-top">
            <div class="battle-status">
              <button class="mini-map" data-action="back-to-map" aria-label="查看态势"></button>
              <div class="top-stat"><span>节点</span><strong>${safeText(battleConfig().display_name || "灰灯驿站")}</strong></div>
            </div>
            <div class="battle-status" id="battleStats"></div>
            <div class="battle-controls">
              <button class="ghost-button" data-action="toggle-pause" id="pauseButton">暂停</button>
              <button class="ghost-button" data-action="cycle-speed" id="speedButton">1x</button>
            </div>
          </div>
          <aside class="battle-side battle-left" id="battleTasks"></aside>
          <section class="battle-stage">
            <canvas id="battleCanvas"></canvas>
            <div class="battle-toast" id="battleToast"></div>
          </section>
          <aside class="battle-side battle-right" id="battleInfo"></aside>
          <div class="battle-tools" id="battleTools"></div>
          <div id="dialogueLayer"></div>
        </section>
      </main>
    `;
    setupBattle();
  }

  function setupBattle() {
    return battleDomController.setupBattle();
  }

  function installBattleSmokeProbe() {
    if (!battleVisualSmokeMode() && !flowVisualSmokeMode()) return;
    window.__AI_TD_BATTLE_SMOKE__ = {
      snapshot: battleSmokeSnapshot,
      deploymentPoint: battleSmokeDeploymentPoint,
    };
  }

  function battleSmokeDeploymentPoint(tool = "basic") {
    const battle = state.battle;
    if (!battle || !battle.canvas || !battle.metrics) return null;
    const rect = battle.canvas.getBoundingClientRect();
    const toolbar = document.querySelector(".battle-tools");
    const assetKind = assetKindForTool(tool);
    const candidates = buildSlots()
      .filter((slot) => {
        const position = slot.position || slot;
        const allowed = slot.allowed_asset_kinds || [];
        return position && allowed.includes(assetKind) && !isOccupied(position);
      })
      .map((slot) => {
        const cell = slot.position || slot;
        const point = projectCell(cell.x, cell.y);
        const clientX = rect.left + point.x;
        const clientY = rect.top + point.y;
        return {
          slot_id: slot.slot_id || slot.id || null,
          cell: { x: cell.x, y: cell.y },
          canvas_x: Math.round(point.x),
          canvas_y: Math.round(point.y),
          client_x: Math.round(clientX),
          client_y: Math.round(clientY),
        };
      });
    const visible = candidates.find((candidate) => {
      const hit = document.elementFromPoint(candidate.client_x, candidate.client_y);
      if (!hit) return false;
      if (toolbar && toolbar.contains(hit)) return false;
      return Boolean(hit.closest("#battleCanvas, .battle-stage"));
    });
    return visible || candidates[0] || null;
  }

  function battleSmokeSnapshot() {
    const battle = state.battle || {};
    const canvas = battle.canvas;
    const rect = canvas ? canvas.getBoundingClientRect() : null;
    return {
      ok: Boolean(canvas && battle.metrics),
      view: state.view,
      mode: "battleVisualSmoke",
      selectedTool: battle.selectedTool || null,
      draggingTool: battle.draggingTool || null,
      hoverCell: battle.hoverCell || null,
      resources: battle.resources ?? null,
      power: battle.power ?? null,
      basicUses: battle.basicUses ?? null,
      sampleDelivered: Boolean(battle.sampleDelivered),
      sampleUses: battle.sampleUses ?? null,
      supportUses: battle.supportUses ?? null,
      defensesCount: Array.isArray(battle.defenses) ? battle.defenses.length : 0,
      trapsCount: Array.isArray(battle.traps) ? battle.traps.length : 0,
      effectsCount: Array.isArray(battle.effects) ? battle.effects.length : 0,
      deployedAssetIds: Array.isArray(battle.deployedAssetIds) ? [...battle.deployedAssetIds] : [],
      deployedAssetCount: Array.isArray(battle.deployedAssetIds) ? battle.deployedAssetIds.length : 0,
      toast: battle.toast || "",
      deploymentPoint: battleSmokeDeploymentPoint(battle.selectedTool || "basic"),
      canvas: rect
        ? {
            left: Math.round(rect.left),
            top: Math.round(rect.top),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            bitmapWidth: canvas.width,
            bitmapHeight: canvas.height,
          }
        : null,
    };
  }

  function stopBattleLoop() {
    battleDomController.stopBattleLoop();
  }

  function createBattleState() {
    const config = battleConfig();
    const objectives = mapObjectives();
    return {
      ...createBattleStateFactory({
        config,
        mapPackage: mapRuntimePackage(),
        objectives,
        flowVisualSmoke: flowVisualSmokeMode(),
        spawnSchedule: buildSpawnSchedule(config),
      }),
      selectedTool: "basic",
      draggingTool: null,
      dragPointer: null,
      hoverCell: null,
    };
  }

  function buildSpawnSchedule(config) {
    return buildSpawnScheduleRule(config);
  }

  function preloadBattleImages() {
    [
      ...mediaPreloadUrls("enemy_shadow_tide_runner", "unit_sprite", true),
      ...mediaPreloadUrls("enemy_shadow_tide_shade", "unit_sprite", true),
      ...mediaPreloadUrls("enemy_shadow_tide_cluster", "unit_sprite", true),
      ...mediaPreloadUrls("objective_station_core", "objective_sprite", true),
      ...mediaPreloadUrls("objective_signal_beacon", "objective_sprite", true),
      ...mediaPreloadUrls("defense_basic_lantern_barricade", "defense_sprite", true),
      ...battleObjectPreloadUrls(),
      sampleIconUrl(),
      ...layeredMapVisualPreloadUrls(),
      ...mapComponentPreloadUrls(),
      ...debugBattleMapVisualUrls(),
      npcPortraitUrl("npc_gray_lantern_keeper"),
      npcPortraitUrl("npc_workshop_mentor"),
    ].forEach((url) => getImage(url));
  }

  function resizeBattleCanvas() {
    battleDomController.resizeBattleCanvas();
  }

  function computeBattleMetrics(width, height) {
    return battleMapAdapter.computeBattleMetrics(width, height);
  }

  function battleCanvasSafeArea(width, height) {
    return battleMapAdapter.battleCanvasSafeArea(width, height);
  }

  function battleFitBounds(tileW, tileH) {
    return battleMapAdapter.battleFitBounds(tileW, tileH);
  }

  function battleFitLogicalPoints() {
    return battleMapAdapter.battleFitLogicalPoints();
  }

  function rawProject(x, y, tileW, tileH) {
    return battleMapAdapter.rawProject(x, y, tileW, tileH);
  }

  function projectCell(x, y) {
    return battleMapAdapter.projectCell(x, y);
  }

  function screenToCell(screenX, screenY) {
    return battleMapAdapter.screenToCell(screenX, screenY);
  }

  function cellFromCanvasEvent(event) {
    return battleMapAdapter.cellFromCanvasEvent(event);
  }

  function isCellInGrid(cell) {
    return battleMapAdapter.isCellInGrid(cell);
  }

  function pathWaypoints(routeId = null) {
    return battleMapAdapter.pathWaypoints(routeId);
  }

  function allPathRoutes() {
    return battleMapAdapter.allPathRoutes();
  }

  function pathCells() {
    return battleMapAdapter.pathCells();
  }

  function distanceToPath(cell) {
    return battleMapAdapter.distanceToPath(cell);
  }

  function routeForSpawn(spawnIndex) {
    return battleMapAdapter.routeForSpawn(spawnIndex);
  }

  function enemyWaypoints(enemy) {
    return battleMapAdapter.enemyWaypoints(enemy);
  }

  function routePointAtT(route, progress) {
    return battleMapAdapter.routePointAtT(route, progress);
  }

  function routeSamplesBetween(route, startT, endT, count = 7) {
    return battleMapAdapter.routeSamplesBetween(route, startT, endT, count);
  }

  const battleInputContext = {
    getBattle: () => state.battle,
    cellFromCanvasEvent: (event) => cellFromCanvasEvent(event),
    deployToolAt: (tool, cell) => deployToolAt(tool, cell),
    toolReady: (tool) => toolReady(tool),
    toolUnavailableText: (tool) => toolUnavailableText(tool),
    setBattleToast: (text) => setBattleToast(text),
    updateBattleDom: () => updateBattleDom(),
  };

  const onBattleCanvasClick = (event) => handleBattleCanvasClick(battleInputContext, event);
  const onBattleCanvasPointerMove = (event) => handleBattleCanvasPointerMove(battleInputContext, event);
  const onBattleCanvasPointerLeave = () => handleBattleCanvasPointerLeave(battleInputContext);
  const beginToolDrag = (tool, event) => handleBeginToolDrag(battleInputContext, tool, event);
  const updateToolDrag = (event) => handleUpdateToolDrag(battleInputContext, event);
  const finishToolDrag = (event) => handleFinishToolDrag(battleInputContext, event);
  const cancelToolDrag = (event) => handleCancelToolDrag(battleInputContext, event);

  function deployToolAt(tool, cell) {
    if (tool === "basic") placeBasicDefense(cell);
    if (tool === "sample") {
      const projected = findBattleToolProjection("sample", battleToolProjection());
      if (projected && projected.objectId !== "sample_trap_7f3a") deployRuntimeTool("sample", cell);
      else placeSampleTrap(cell);
    }
    if (tool === "support") useSupportPulse(cell);
    if (!["basic", "sample", "support"].includes(tool)) deployRuntimeTool(tool, cell);
  }

  function toolUnavailableText(tool) {
    return toolUnavailableTextAction(findBattleToolProjection(tool, battleToolProjection()) || tool);
  }

  function canPreviewToolAt(tool, cell) {
    if (!isCellInGrid(cell) || !toolReady(tool)) return false;
    if (tool === "sample") {
      const projected = findBattleToolProjection("sample", battleToolProjection());
      if (projected && projected.objectId !== "sample_trap_7f3a") {
        return canPreviewRuntimeToolAt({ tool: projected, cell, canPlaceToolAt });
      }
      return canPlaceToolAt(tool, cell);
    }
    if (tool === "basic") return canPlaceToolAt(tool, cell);
    if (tool === "support") return true;
    return canPreviewRuntimeToolAt({
      tool: findBattleToolProjection(tool, battleToolProjection()),
      cell,
      canPlaceToolAt,
    });
  }

  function buildSlots() {
    return battleMapAdapter.buildSlots();
  }

  function mapResourceNodes() {
    return battleMapAdapter.mapResourceNodes();
  }

  function mapHazardZones() {
    return battleMapAdapter.mapHazardZones();
  }

  function mapDefenseAnchors() {
    return battleMapAdapter.mapDefenseAnchors();
  }

  function mapBlockedAreas() {
    return battleMapAdapter.mapBlockedAreas();
  }

  function slotAt(cell) {
    return battleMapAdapter.slotAt(cell);
  }

  function battleToolProjection(media = null) {
    return buildBattleToolProjection({
      battle: state.battle || {},
      battleConfig: battleConfig(),
      activatedRuntimeBundle: featureGateRegistry.activeBundleFor("battle"),
      media,
    });
  }

  function assetKindForTool(tool) {
    return assetKindForToolId(tool, battleToolProjection());
  }

  function canPlaceToolAt(tool, cell) {
    if (!isCellInGrid(cell)) return false;
    const slots = buildSlots();
    const occupied = isOccupied(cell);
    return canPlaceToolAtRule({
      tool,
      cell,
      grid: mapGrid(),
      occupied,
      slots,
      distanceToPathValue: !occupied && !slots.length ? distanceToPath(cell) : undefined,
      assetKind: slots.length ? assetKindForTool(tool) : undefined,
    });
  }

  function isOccupied(cell) {
    return battleMapAdapter.isOccupied(cell);
  }

  function placeBasicDefense(cell) {
    placeBasicDefenseAction({
      battle: state.battle,
      cell,
      tool: findBattleToolProjection("basic", battleToolProjection()),
      canPlaceToolAt,
      addEffect,
      setBattleToast,
    });
  }

  function placeSampleTrap(cell) {
    placeSampleTrapAction({
      battle: state.battle,
      cell,
      tool: findBattleToolProjection("sample", battleToolProjection()),
      canPlaceToolAt,
      addEffect,
      setBattleToast,
    });
  }

  function useSupportPulse(cell) {
    useSupportPulseAction({
      battle: state.battle,
      cell,
      tool: findBattleToolProjection("support", battleToolProjection()),
      addEffect,
      addFloating,
      setBattleToast,
    });
  }

  function deployRuntimeTool(toolId, cell) {
    deployRuntimeToolAction({
      battle: state.battle,
      cell,
      tool: findBattleToolProjection(toolId, battleToolProjection()),
      canPlaceToolAt,
      addEffect,
      addFloating,
      setBattleToast,
    });
  }

  function setBattleToast(text) {
    battleDomController.setBattleToast(text);
  }

  function showDialogue(name, line, portraitId) {
    battleDomController.showDialogue(name, line, portraitId);
  }

  function closeDialogue() {
    battleDomController.closeDialogue();
  }

  function handleBattleSampleDelivered() {
    void activateDeliveredSample();
  }

  async function activateDeliveredSample() {
    let displayName = "折光绊索";
    if (isApiMode() && state.research.jobPromise) {
      try {
        const job = await state.research.jobPromise;
        if (!job || job.status !== "completed") throw new Error("sample unavailable");
        const response = await apiPost(
          sessionApiPath(`/research/jobs/${encodeURIComponent(job.job_id)}/activate`),
          {},
          8000,
        );
        if (!response.activation_receipt || response.activation_receipt.status !== "activated") {
          throw new Error("sample activation blocked");
        }
        state.data.activatedRuntimeBundle =
          response.activated_runtime_bundle || state.data.activatedRuntimeBundle;
        const activatedIds = response.activation_receipt.runtime_effect.activated_object_ids || [];
        const activatedObjects = ((state.data.activatedRuntimeBundle || {}).capabilities || {}).battle_objects || [];
        const activatedObject = activatedObjects.find((item) => activatedIds.includes(item.object_id));
        if (activatedObject) {
          displayName = activatedObject.display_name || displayName;
          const uses = Number((activatedObject.lifecycle || {}).max_uses);
          if (state.battle && Number.isFinite(uses) && uses > 0) state.battle.sampleUses = uses;
        }
        battleObjectPreloadUrls().forEach((url) => getImage(url));
        updateBattleDom();
      } catch {
        setBattleToast("样品封装尚未稳定，先维持现有防线");
        return;
      }
    }
    setBattleToast(`样品完成：${displayName} x${state.battle ? state.battle.sampleUses : 2}`);
    if (!flowVisualSmokeMode()) {
      showDialogue(
        "临时工坊老师傅",
        `${displayName}封装完成。把它压在转角，影潮会被那道折光拖住。`,
        "npc_workshop_mentor_portrait",
      );
    }
  }

  function addEffect(type, x, y, color, duration, scale = 1) {
    addBattleEffect(state.battle, type, x, y, color, duration, scale);
  }

  function addFloating(x, y, text, color) {
    addBattleFloating(state.battle, x, y, text, color);
  }

  function waveLabel() {
    return buildBattleWaveLabel(state.battle);
  }

  function battleHudViewModel() {
    return buildBattleHudViewModel({
      battle: state.battle,
      objectives: mapObjectives(),
      sampleProgressText: sampleProgressMessage(),
      nextWaveLabel: nextWaveText(),
      npcAvatarUrl: npcPortraitUrl("npc_gray_lantern_keeper"),
      toolbarTools: battleToolbarViewModel(),
    });
  }

  function updateBattleDom() {
    battleDomController.updateBattleDom();
  }

  function sampleProgressMessage() {
    return buildSampleProgressMessage({
      battle: state.battle,
      battleConfig: battleConfig(),
    });
  }

  function nextWaveText() {
    return buildNextWaveText(state.battle);
  }

  function toolReady(tool) {
    return toolReadyRule(tool, state.battle, findBattleToolProjection(tool, battleToolProjection()));
  }

  function fallbackToolCooldownMs(tool) {
    return fallbackToolCooldownMsRule(tool);
  }

  function toolCooldownFill(tool) {
    const battle = state.battle;
    const projected = findBattleToolProjection(tool, battleToolProjection());
    return buildToolCooldownFill({
      battle,
      tool: {
        id: tool,
        cooldownMs: Number(projected && projected.cooldownMs) || fallbackToolCooldownMs(tool),
      },
    });
  }

  function battleToolbarViewModel() {
    const basicUrl = mediaUrl("defense_basic_lantern_barricade", "icon", true);
    const sampleUrl = sampleIconUrl();
    const npcUrl = mediaUrl("npc_gray_lantern_keeper_portrait", "icon", true);
    const tools = battleToolProjection({
      basic: basicUrl,
      sample: sampleUrl,
      support: npcUrl,
      asset_light_slow_tower_001: mediaUrl("asset_light_slow_tower_001", "icon"),
    });
    return buildBattleToolbarViewModel({
      battle: state.battle,
      tools,
      isToolReady: toolReady,
    });
  }

  function battleToolsMarkup(tools = battleToolbarViewModel()) {
    return tools
      .map(
        (tool) => `
          <button class="toolbar-card ${tool.isSelected ? "is-selected" : ""} ${tool.isDragging ? "is-dragging" : ""} ${tool.isLocked ? "is-locked" : ""}" data-action="select-tool" data-tool="${safeText(tool.id)}" draggable="false">
            <span class="tool-icon">${imageTag(tool.img, tool.name)}</span>
            <span class="tool-body">
              <span class="tool-name">${safeText(tool.name)}</span>
              <span class="tool-meta">${(tool.meta || []).map((item) => `<span>${safeText(item)}</span>`).join("")}</span>
              <span class="cooldown-bar"><i style="--fill:${tool.cooldownFill}"></i></span>
            </span>
          </button>
        `,
      )
      .join("");
  }

  function drawBattle() {
    const battle = state.battle;
    drawBattleFrame({
      battle,
      drawBackdrop,
      drawBuildableTerraces,
      drawSlotAccessTrails,
      drawPath,
      drawMapRuntimeStrongSemantics,
      drawDeployHints,
      drawWorldObjects,
      drawSpawnMarkers,
      drawEntities,
      drawEffects,
      drawDragGhost,
    });
  }

  function runtimeMapSeed() {
    const pkg = mapRuntimePackage();
    return hashString(`${pkg.package_id || ""}|${pkg.node_id || currentNodeId() || NODE_ID}`);
  }

  function hashString(value) {
    let hash = 2166136261;
    const text = String(value || "");
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function makeSeededRandom(seed) {
    let value = seed >>> 0;
    return () => {
      value += 0x6d2b79f5;
      let t = value;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function battleNodeVisualProfile() {
    const nodeId = String((mapRuntimePackage() || {}).node_id || currentNodeId() || NODE_ID);
    const profiles = {
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
    const fallback = profiles[nodeId] || profiles.gray_lantern_station;
    const pack = mapStylePack();
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

  function terrainFeatureSet() {
    const battle = state.battle;
    const grid = mapGrid();
    const pkg = mapRuntimePackage();
    const key = `${pkg.package_id || currentNodeId()}:${grid.width_cells}x${grid.height_cells}`;
    if (battle && battle.terrainFeatureSet && battle.terrainFeatureSet.key === key) {
      return battle.terrainFeatureSet;
    }

    const seed = runtimeMapSeed();
    const rng = makeSeededRandom(seed ^ hashString("procedural-battlefield"));
    const profile = battleNodeVisualProfile();
    const palette = profile.patchPalette;
    const bands = Array.from({ length: 8 }, (_, index) => ({
      y: -0.08 + index * 0.155 + (rng() - 0.5) * 0.03,
      height: 0.18 + rng() * 0.09,
      lean: (rng() - 0.5) * 0.16,
      alpha: 0.035 + rng() * 0.045,
      warm: rng() > 0.48,
    }));
    const patches = Array.from({ length: 13 }, () => ({
      x: rng(),
      y: rng(),
      rx: 0.12 + rng() * 0.22,
      ry: 0.06 + rng() * 0.14,
      rotation: (rng() - 0.5) * 0.9,
      color: palette[Math.floor(rng() * palette.length)],
      wobble: Array.from({ length: 9 }, () => 0.78 + rng() * 0.48),
    }));
    const specks = Array.from({ length: 260 }, () => ({
      x: rng(),
      y: rng(),
      size: 0.7 + rng() * 2.8,
      alpha: 0.05 + rng() * 0.13,
      warm: rng() > 0.46,
    }));
    const debris = [];
    let attempts = 0;
    while (debris.length < 88 && attempts < 260) {
      attempts += 1;
      const x = rng() * (grid.width_cells + 1.6) - 0.8;
      const y = rng() * (grid.height_cells + 1.6) - 0.8;
      const cell = { x: Math.round(x), y: Math.round(y) };
      if (!isCellInGrid(cell)) continue;
      if (distanceToPath(cell) < 1.15 || slotAt(cell) || objectiveAtCell(cell)) continue;
      debris.push({
        x,
        y,
        dx: (rng() - 0.5) * 0.62,
        dy: (rng() - 0.5) * 0.62,
        size: 0.55 + rng() * 1.4,
        rotation: rng() * Math.PI,
        kind: rng() < 0.52 ? "stone" : rng() < 0.82 ? "reed" : "scrap",
        shade: rng(),
      });
    }
    const darkPools = [];
    attempts = 0;
    while (darkPools.length < 9 && attempts < 180) {
      attempts += 1;
      const x = rng() * grid.width_cells;
      const y = rng() * grid.height_cells;
      const cell = { x: Math.round(x), y: Math.round(y) };
      if (!isCellInGrid(cell)) continue;
      if (distanceToPath(cell) < 1.05 || objectiveAtCell(cell)) continue;
      darkPools.push({
        x,
        y,
        rx: 0.34 + rng() * 0.52,
        ry: 0.18 + rng() * 0.28,
        rotation: (rng() - 0.5) * 0.7,
        alpha: 0.12 + rng() * 0.12,
      });
    }
    const landmarks = [];
    const landmarkKinds = ["collapsed_wall", "signal_scrap", "supply_cache", "lamp_relic"];
    attempts = 0;
    while (landmarks.length < 14 && attempts < 260) {
      attempts += 1;
      const x = Math.floor(rng() * grid.width_cells);
      const y = Math.floor(rng() * grid.height_cells);
      const cell = { x, y };
      if (!isCellInGrid(cell)) continue;
      if (distanceToPath(cell) < 1.2 || slotAt(cell) || objectiveAtCell(cell)) continue;
      landmarks.push({
        x: x + (rng() - 0.5) * 0.42,
        y: y + (rng() - 0.5) * 0.42,
        kind: landmarkKinds[Math.floor(rng() * landmarkKinds.length)],
        scale: 0.78 + rng() * 0.48,
        rotation: (rng() - 0.5) * 0.45,
        warm: rng() > 0.58,
      });
    }
    const wisps = Array.from({ length: 12 }, () => ({
      edge: Math.floor(rng() * 4),
      offset: rng(),
      sway: rng(),
      width: 38 + rng() * 88,
      alpha: 0.035 + rng() * 0.045,
    }));
    const scenicRidges = buildScenicRidges(rng, grid);
    const fieldEdgeProps = buildFieldEdgeProps(rng);
    const roadsideProps = buildRoadsideProps(rng, profile);
    const accessTrails = buildSlotAccessTrails();
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
      scenicRidges,
      fieldEdgeProps,
      wisps,
      roadsideProps,
      accessTrails,
    };
    if (battle) battle.terrainFeatureSet = features;
    return features;
  }

  function buildScenicRidges(rng, grid) {
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
        x: anchor.x + (rng() - 0.5) * 0.8,
        y: anchor.y + (rng() - 0.5) * 0.55,
        width: anchor.w * (0.86 + rng() * 0.22),
        height: anchor.h * (0.86 + rng() * 0.26),
        side: anchor.side,
        alpha: 0.18 + rng() * 0.16,
        warm: rng() > 0.56,
      });
    }
    return ridges;
  }

  function buildFieldEdgeProps(rng) {
    const props = [];
    const edgeCount = 8;
    for (let i = 0; i < edgeCount; i += 1) {
      const count = 4 + Math.floor(rng() * 3);
      for (let j = 0; j < count; j += 1) {
        if (rng() < 0.18) continue;
        props.push({
          edgeIndex: i,
          t: (j + 0.16 + rng() * 0.68) / count,
          angleJitter: (rng() - 0.5) * 0.5,
          scale: 0.58 + rng() * 0.92,
          kind: rng() < 0.42 ? "stone" : rng() < 0.76 ? "timber" : "reed",
          alpha: 0.18 + rng() * 0.18,
        });
      }
    }
    return props;
  }

  function buildRoadsideProps(rng, profile) {
    const props = [];
    for (const route of allPathRoutes()) {
      const waypoints = route.waypoints || [];
      for (let i = 0; i < waypoints.length - 1; i += 1) {
        const a = waypoints[i];
        const b = waypoints[i + 1];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.max(1, Math.hypot(dx, dy));
        const nx = -dy / len;
        const ny = dx / len;
        const count = Math.max(2, Math.floor(len * 1.35));
        for (let j = 0; j < count; j += 1) {
          if (rng() < 0.18) continue;
          const t = (j + 0.18 + rng() * 0.64) / count;
          const side = rng() < 0.5 ? -1 : 1;
          const kind = profile.roadside[Math.floor(rng() * profile.roadside.length)];
          props.push({
            routeId: route.route_id || "route",
            x: a.x + dx * t + nx * side * (0.58 + rng() * 0.42),
            y: a.y + dy * t + ny * side * (0.58 + rng() * 0.42),
            kind,
            scale: 0.68 + rng() * 0.52,
            rotation: (rng() - 0.5) * 0.72,
            warm: rng() > 0.45,
          });
        }
      }
    }
    return props;
  }

  function buildSlotAccessTrails() {
    const trails = [];
    for (const slot of buildSlots()) {
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

  function nearestPointOnRoutes(cell) {
    let best = null;
    for (const route of allPathRoutes()) {
      const points = route.waypoints || [];
      for (let i = 0; i < points.length - 1; i += 1) {
        const a = points[i];
        const b = points[i + 1];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const lenSq = dx * dx + dy * dy;
        if (!lenSq) continue;
        const t = clamp(((cell.x - a.x) * dx + (cell.y - a.y) * dy) / lenSq, 0, 1);
        const x = a.x + dx * t;
        const y = a.y + dy * t;
        const distance = Math.hypot(cell.x - x, cell.y - y);
        if (!best || distance < best.distance) best = { x, y, distance };
      }
    }
    return best;
  }

  function objectiveAtCell(cell) {
    const objectives = mapObjectives();
    const targets = [objectives.core_target, ...(objectives.optional_targets || [])].filter(Boolean);
    return targets.some(
      (target) => target.position && target.position.x === cell.x && target.position.y === cell.y,
    );
  }

  function drawBackdrop(ctx, m) {
    return battleTerrainRenderer.drawBackdrop(ctx, m);
  }

  function imageRenderable(image) {
    return battleTerrainRenderer.imageRenderable(image);
  }

  function drawComponentTextureEllipse(ctx, role, x, y, width, height, options = {}) {
    return battleTerrainRenderer.drawComponentTextureEllipse(ctx, role, x, y, width, height, options);
  }

  function drawPath(ctx) {
    battleRoadRenderer.drawPath(ctx);
  }

  function traceRoutePath(ctx, points) {
    battleRoadRenderer.traceRoutePath(ctx, points);
  }

  function drawSlotAccessTrails(ctx) {
    battleRoadRenderer.drawSlotAccessTrails(ctx);
  }

  function drawBuildableTerraces(ctx) {
    battleDeploymentRenderer.drawBuildableTerraces(ctx);
  }

  function drawDeployHints(ctx, options = {}) {
    battleDeploymentRenderer.drawDeployHints(ctx, options);
  }

  function suggestedSockets() {
    return battleDeploymentRenderer.suggestedSockets();
  }

  function drawMapRuntimeStrongSemantics(ctx) {
    battleSemanticRenderer.drawMapRuntimeStrongSemantics(ctx);
  }

  function drawWorldObjects(ctx, options = {}) {
    battleWorldRenderer.drawWorldObjects(ctx, options);
  }

  function drawSpawnMarkers(ctx) {
    battleWorldRenderer.drawSpawnMarkers(ctx);
  }

  function drawEntities(ctx) {
    battleEntityRenderer.drawEntities(ctx);
  }

  function drawTowerMuzzle(ctx, x, y, ratio) {
    battleEntityRenderer.drawTowerMuzzle(ctx, x, y, ratio);
  }

  function mapSpriteSize(base, minimum) {
    return battleEntityRenderer.mapSpriteSize(base, minimum);
  }

  function drawEffects(ctx) {
    battleEntityRenderer.drawEffects(ctx);
  }

  function drawDragGhost(ctx) {
    battleEntityRenderer.drawDragGhost(ctx);
  }

  function drawGroundGlow(ctx, x, y, color, alpha, radius) {
    battleEntityRenderer.drawGroundGlow(ctx, x, y, color, alpha, radius);
  }

  function drawSprite(ctx, spriteRef, x, y, size, flash = false) {
    battleEntityRenderer.drawSprite(ctx, spriteRef, x, y, size, flash);
  }

  async function finishBattle(result) {
    const battle = state.battle;
    if (!battle || battle.finishing) return;
    const finishedNodeId = currentNodeId();
    battle.finishing = true;
    battle.paused = true;
    battle.loopActive = false;
    state.battleOutcome = {
      result: result === "victory" ? "victory" : "defeat",
      protected_core_hp: Math.max(0, battle.coreHp),
      optional_target_state: battle.optionalHp < ((((mapObjectives().optional_targets || [])[0] || {}).durability) || 4) ? "damaged" : "intact",
      deployed_asset_ids: [...new Set(battle.deployedAssetIds)],
      leaked_enemy_count: battle.leaks,
      kills: battle.kills,
    };
    renderLoading("整理战报");
    let settlement = buildLocalSettlement(state.battleOutcome, finishedNodeId);
    if (isApiMode()) {
      try {
        const response = await apiPost(
          sessionApiPath(`/battles/${finishedNodeId}/results`),
          {
            result: state.battleOutcome.result,
            protected_core_hp: state.battleOutcome.protected_core_hp,
            optional_target_state: state.battleOutcome.optional_target_state,
            deployed_asset_ids: state.battleOutcome.deployed_asset_ids,
            leaked_enemy_count: state.battleOutcome.leaked_enemy_count,
            notes: "browser playable result",
          },
          5000,
        );
        settlement = response.settlement || settlement;
        state.data.activatedRuntimeBundle =
          response.activated_runtime_bundle || state.data.activatedRuntimeBundle || null;
      } catch {
        // Keep the locally calculated settlement.
      }
      try {
        await Promise.all([loadMap(), loadCampaignRoute()]);
      } catch {
        // Keep the last known map/route projection.
      }
      requestNextPrefetch();
      state.evidence = await fetchEvidence();
    } else {
      await advanceStaticCampaignAfterBattle(finishedNodeId, settlement);
    }
    state.settlement = settlement;
    saveProfile({ completedBattle: isApiMode() ? true : staticCampaignComplete() });
    setPlayerView("settlement");
    render();
  }

  async function advanceStaticCampaignAfterBattle(nodeId, settlement) {
    const progress = await advanceStaticCampaignProgress(nodeId);
    if (settlement && progress && progress.interlude) {
      settlement.interlude_summary = progress.interlude;
    }
  }

  function buildLocalSettlement(outcome, nodeId = currentNodeId()) {
    return settlementFeatureController.buildLocalSettlement(outcome, nodeId);
  }

  async function fetchEvidence() {
    try {
      if (state.research.jobPromise) await state.research.jobPromise;
      const response = await apiGet(sessionApiPath("/evidence"), 3600);
      return response;
    } catch {
      return null;
    }
  }

  function renderSettlement() {
    settlementFeatureController.renderSettlement();
  }

  function evidenceMarkup() {
    return settlementFeatureController.evidenceMarkup();
  }

  async function returnToMap() {
    if (isApiMode()) {
      try {
        await Promise.all([loadMap(), loadCampaignRoute()]);
      } catch {
        // Keep current map projection.
      }
    }
    state.selectedMapNodeId = currentNodeId();
    setPlayerView("map");
    render();
  }

  const appActionHandlers = {
    boot: () => boot(),
    continue: () => {
        setPlayerView(state.profile.worldCreated ? "map" : "world-config");
        render();
    },
    "new-archive": () => startNewArchive(),
    "reset-demo": () => resetDemo(),
    settings: () => {
        renderError(state.dataMode === "api" ? "当前使用中枢档案。重置演示可重新开始。" : "当前使用本机档案。");
    },
    "select-creativity": (target) => {
        state.selectedOptions.creativity_mode = target.dataset.value;
        saveProfile();
        renderWorldConfig();
    },
    "select-origin": (target) => {
        state.selectedOptions.player_origin = target.dataset.value;
        saveProfile();
        renderWorldConfig();
    },
    "use-recommended": () => {
        state.selectedOptions = { ...DEFAULT_WORLD_CONFIG.recommended_defaults };
        saveProfile();
        renderWorldConfig();
    },
    "begin-world": () => beginWorld(),
    "opening-next": () => {
        state.openingIndex += 1;
        if (state.openingIndex >= ((state.data.opening || {}).segments || []).length) {
          setPlayerView("map");
        }
        render();
    },
    "opening-skip": () => {
        setPlayerView("map");
        render();
    },
    "select-map-node": (target) => {
        state.selectedMapNodeId = target.dataset.nodeId;
        renderMap();
    },
    "enter-node": () => enterCurrentNode(),
    "refresh-map": () => loadMap().finally(renderMap),
    "map-zoom-in": () => zoomStrategicMapBy(1.25),
    "map-zoom-out": () => zoomStrategicMapBy(1 / 1.25),
    "map-camera-reset": () => resetStrategicMapCamera(),
    "proposal-refresh": () => refreshProposal(),
    "intent-preset": (target) => {
        state.intentText = target.dataset.intent || state.intentText;
        state.research.status = "idle";
        state.research.proposal = null;
        state.research.proposalIntent = "";
        renderWorkshop();
    },
    "confirm-prototype": () => confirmPrototype(),
    "toggle-pause": () => battleDomController.togglePause(),
    "cycle-speed": () => battleDomController.cycleSpeed(),
    "select-tool": (target) => battleDomController.selectTool(target.dataset.tool),
    "close-dialogue": () => closeDialogue(),
    "back-to-map": () => battleDomController.announceMapLocked(),
    "return-map": () => returnToMap(),
    "restart-battle": () => {
        state.battle = null;
        setPlayerView("battle");
        render();
    },
  };

  const rootEventRouter = createRootEventRouter({
    root: ROOT,
    windowRef: window,
    actionHandlers: appActionHandlers,
    isActionBlocked: (action) =>
      state.view === "battle" &&
      Boolean(state.battle && state.battle.dialogueOpen) &&
      action !== "close-dialogue",
    getSuppressMapClick: () => Boolean(state.suppressMapClick),
    setSuppressMapClick: (value) => {
      state.suppressMapClick = value;
    },
    canBeginToolDrag: (event) => state.view === "battle" && event.button === 0,
    beginToolDrag: (tool, event) => beginToolDrag(tool, event),
    updateToolDrag: (event) => updateToolDrag(event),
    finishToolDrag: (event) => finishToolDrag(event),
    cancelToolDrag: (event) => cancelToolDrag(event),
    beginStrategicMapDrag: (event) => beginStrategicMapDrag(event),
    updateStrategicMapDrag: (event) => updateStrategicMapDrag(event),
    finishStrategicMapDrag: (event) => finishStrategicMapDrag(event),
    handleStrategicMapWheel: (event) => handleStrategicMapWheel(event),
    updateIntent: (value) => {
      state.intentText = value;
      if (
        state.research.status === "proposed" &&
        state.research.proposalIntent &&
        state.research.proposalIntent !== value.trim()
      ) {
        state.research.status = "stale";
        state.research.proposal = null;
        state.research.proposalIntent = "";
        const review = ROOT.querySelector(".workshop-review");
        if (review) review.classList.add("is-stale");
        const confirm = ROOT.querySelector("[data-action='confirm-prototype']");
        if (confirm) confirm.disabled = true;
        const refresh = ROOT.querySelector("[data-action='proposal-refresh']");
        if (refresh) {
          refresh.disabled = false;
          refresh.textContent = "重新推演方案";
          refresh.classList.add("primary-button");
        }
      }
    },
  });
  rootEventRouter.install();

  boot();
})();
