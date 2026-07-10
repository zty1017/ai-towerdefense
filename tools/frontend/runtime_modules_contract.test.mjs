import assert from "node:assert/strict";
import test from "node:test";

import { createAppFlowOrchestrator } from "../../frontend/runtime/app-flow-orchestrator.js";
import {
  assetKindForToolId,
  buildBattleToolProjection,
  findBattleToolProjection,
} from "../../frontend/runtime/runtime-projection-adapter.js";
import {
  canPreviewRuntimeToolAt,
  deployRuntimeTool,
  placeBasicDefense,
  toolUnavailableText,
  useSupportPulse,
} from "../../frontend/runtime/battle-actions.js";
import {
  buildBattleHudViewModel,
  buildBattleToolbarViewModel,
  toolCooldownFill,
} from "../../frontend/runtime/battle-hud-view-model.js";
import {
  allPathRoutesFromRuntime,
  colorFromStylePack,
  mapGridFromRuntime,
  mapObjectivesFromRuntime,
  pathWaypointsFromRuntime,
  rgbaFromStylePack,
  routeRoadWidthCellsFromPlan,
  routeShoulderWidthScaleFromPlan,
  runtimeSemanticList,
  slotFootprintScaleFromPlan,
} from "../../frontend/runtime/map-runtime-accessors.js";
import { toolReady } from "../../frontend/runtime/battle-rules.js";
import { createFrontendDataRuntime } from "../../frontend/runtime/frontend-data-runtime.js";
import { createFeatureGateRegistry } from "../../frontend/runtime/feature-gates.js";
import { createNarrativeFeatureProjection } from "../../frontend/runtime/narrative-feature-projection.js";
import { createFrontendMediaCatalog } from "../../frontend/runtime/frontend-media-catalog.js";
import { createOnboardingFeatureController } from "../../frontend/runtime/onboarding-feature-controller.js";
import { createRootEventRouter } from "../../frontend/runtime/root-event-router.js";
import { createSettlementFeatureController } from "../../frontend/runtime/settlement-feature-controller.js";
import { createWorkshopFeatureController } from "../../frontend/runtime/workshop-feature-controller.js";
import {
  createStrategicMapController,
  fitStrategicMapCamera,
  normalizeStrategicMapCamera,
  STRATEGIC_MAP_MAX_ZOOM,
} from "../../frontend/runtime/strategic-map-controller.js";
import { createStrategicMapFeatureController } from "../../frontend/runtime/strategic-map-feature-controller.js";
import { createStrategicMapProjection } from "../../frontend/runtime/strategic-map-projection.js";
import {
  createBattleOrchestrator,
  runBattleUpdate,
} from "../../frontend/runtime/battle-orchestrator.js";
import { createBattleDeploymentRenderer } from "../../frontend/runtime/battle-deployment-renderer.js";
import { createBattleDomController } from "../../frontend/runtime/battle-dom-controller.js";
import { createBattleMapAdapter } from "../../frontend/runtime/battle-map-adapter.js";
import { createBattleEntityRenderer } from "../../frontend/runtime/battle-entity-renderer.js";
import { createBattleRoadRenderer } from "../../frontend/runtime/battle-road-renderer.js";
import { createBattleSemanticRenderer } from "../../frontend/runtime/battle-semantic-renderer.js";
import { createBattleTerrainRenderer } from "../../frontend/runtime/battle-terrain-renderer.js";
import { createBattleWorldRenderer } from "../../frontend/runtime/battle-world-renderer.js";

function recordingCanvasContext() {
  const calls = [];
  const gradient = { addColorStop: (...args) => calls.push(["addColorStop", ...args]) };
  const target = { calls };
  return new Proxy(target, {
    get(object, property) {
      if (property in object) return object[property];
      if (property === "createLinearGradient" || property === "createRadialGradient") {
        return (...args) => {
          calls.push([property, ...args]);
          return gradient;
        };
      }
      return (...args) => calls.push([property, ...args]);
    },
    set(object, property, value) {
      object[property] = value;
      calls.push(["set", property, value]);
      return true;
    },
  });
}

function runtimeBundle(extraObjects = []) {
  return {
    capabilities: {
      battle_objects: [
        {
          object_id: "basic_lantern_tower_001",
          display_name: "基础灯栏",
          asset_kind: "tower_blueprint",
          behavior_abi: {
            cost: { resource: "materials", amount: 7 },
            cooldown: { milliseconds: 1234 },
            effect_blocks: [{ kind: "damage" }],
            ui_surfaces: ["battle_hotbar"],
          },
        },
        {
          object_id: "guardian_support_001",
          display_name: "守灯支援",
          asset_kind: "support_item",
          behavior_abi: {
            cost: { resource: "materials", amount: 11 },
            cooldown: { milliseconds: 4321 },
            effect_blocks: [{ kind: "aura" }],
            ui_surfaces: ["battle_hotbar"],
          },
        },
        ...extraObjects,
      ],
    },
  };
}

test("runtime projection consumes battle_hotbar ABI cost and cooldown", () => {
  const projection = buildBattleToolProjection({
    battle: { basicUses: 2, sampleDelivered: false, sampleUses: 0, supportUses: 1 },
    activatedRuntimeBundle: runtimeBundle([
      {
        object_id: "ember_watch_tower_001",
        display_name: "余烬望塔",
        asset_kind: "tower_blueprint",
        media_refs: {
          icon: { url: "/assets/activated/ember-icon.png" },
          sprite: { image: "/assets/activated/ember-sprite.png" },
        },
        behavior_abi: {
          placement: { mode: "build_slot" },
          cost: { resource: "materials", amount: 13 },
          cooldown: { milliseconds: 1500 },
          targeting: { range_cells: 3 },
          effect_blocks: [{ kind: "damage", amount: 16 }],
          ui_surfaces: ["battle_hotbar"],
        },
      },
      {
        object_id: "echo_talisman_001",
        display_name: "回光符",
        asset_kind: "field_device",
        behavior_abi: {
          cost: { resource: "light", amount: 3 },
          cooldown: { seconds: 2 },
          effect_blocks: [{ kind: "reveal" }],
          ui_surfaces: ["battle_hotbar"],
        },
      },
      {
        object_id: "unsafe_tool",
        tool_id: "bad\" onclick=\"x",
        display_name: "不安全标识测试",
        asset_kind: "support_item",
        behavior_abi: {
          placement: { mode: "free_point" },
          cost: { resource: "materials", amount: -5 },
          cooldown: { milliseconds: 100 },
          effect_blocks: [{ kind: "reveal" }],
          ui_surfaces: ["battle_hotbar"],
        },
      },
    ]),
    media: { basic: "/basic.png", support: "/support.png", echo_talisman_001: "/echo.png" },
  });

  const basic = findBattleToolProjection("basic", projection);
  assert.equal(basic.cooldownMs, 1234);
  assert.deepEqual(basic.cost, { resource: "materials", amount: 7 });
  assert.deepEqual(basic.meta, ["材料 7", "剩余 2"]);

  const support = findBattleToolProjection("support", projection);
  assert.equal(support.cooldownMs, 4321);
  assert.equal(support.meta[0], "材料 11");

  const tower = findBattleToolProjection("ember_watch_tower_001", projection);
  assert.equal(tower.assetKind, "tower_blueprint");
  assert.equal(tower.cooldownMs, 1500);
  assert.equal(tower.runtimeOnly, true);
  assert.equal(tower.img, "/assets/activated/ember-icon.png");
  assert.equal(tower.mediaRefs.sprite.image, "/assets/activated/ember-sprite.png");

  const dynamic = findBattleToolProjection("echo_talisman_001", projection);
  assert.equal(dynamic.name, "回光符");
  assert.equal(dynamic.cooldownMs, 2000);
  assert.equal(dynamic.cost.resource, "light");
  assert.equal(dynamic.runtimeOnly, true);
  assert.equal(assetKindForToolId("echo_talisman_001", projection), "field_device");

  const unsafe = projection.find((tool) => tool.objectId === "unsafe_tool");
  assert.equal(unsafe.id.includes('"'), false);
  assert.equal(unsafe.meta[0], "材料 0");
});

test("frontend data runtime owns static node routing and asset resolution", async () => {
  const state = {
    apiBase: "",
    dataMode: "static",
    sessionId: "",
    profile: { staticCampaignStageIndex: 0 },
    selectedNodeId: "gray_lantern_station",
    selectedMapNodeId: "gray_lantern_station",
    data: {
      battleConfig: { display_name: "旧信号塔" },
      runWorldState: { progress: { phase: "signal_pressure" } },
    },
  };
  const runtime = createFrontendDataRuntime({
    state,
    location: {
      search: "?static=1&flowVisualSmoke=1&nodeId=old_signal_tower",
      protocol: "http:",
      hostname: "127.0.0.1",
      origin: "http://127.0.0.1:5174",
    },
  });

  assert.equal(runtime.forceStaticDataMode(), true);
  assert.equal(runtime.staticNodeId(), "old_signal_tower");
  assert.deepEqual(runtime.apiCandidates(), []);
  const route = await runtime.loadCampaignRoute();
  assert.equal(route.current.node_id, "old_signal_tower");
  assert.equal(route.current.playable, true);
  assert.equal(state.selectedNodeId, "old_signal_tower");
  assert.equal(
    runtime.resolveAssetUrl("/assets/layered_maps/old_signal_tower/composited/map.svg"),
    "/game_data/media/layered_maps/old_signal_tower/composited/map.svg",
  );
});

test("frontend data runtime probes explicit API candidates through injected fetch", async () => {
  const calls = [];
  const state = {
    apiBase: "",
    dataMode: "loading",
    sessionId: "",
    profile: {},
    selectedNodeId: "gray_lantern_station",
    selectedMapNodeId: "gray_lantern_station",
    data: {},
  };
  const runtime = createFrontendDataRuntime({
    state,
    location: {
      search: "?apiBase=https%3A%2F%2Fapi.example.test%2F",
      protocol: "https:",
      hostname: "game.example.test",
      origin: "https://game.example.test",
    },
    fetchJsonImpl: async (url) => {
      calls.push(url);
      if (url === "https://api.example.test/api/health") return { status: "ok" };
      throw new Error("unavailable");
    },
  });

  assert.deepEqual(runtime.apiCandidates(), [
    "https://api.example.test",
    "https://game.example.test",
  ]);
  assert.equal(await runtime.detectApiBase(), "https://api.example.test");
  assert.deepEqual(calls, ["https://api.example.test/api/health"]);
});

test("frontend data runtime refreshes activated feature snapshots through the API adapter", async () => {
  const calls = [];
  const state = {
    apiBase: "https://api.example.test",
    dataMode: "api",
    sessionId: "session-a",
    profile: {},
    selectedNodeId: "node_a",
    selectedMapNodeId: "node_a",
    data: {},
  };
  const runtime = createFrontendDataRuntime({
    state,
    location: { search: "", protocol: "https:", hostname: "game.example.test" },
    fetchJsonImpl: async (url) => {
      calls.push(url);
      return {
        payload: {
          activated_runtime_bundle: {
            bundle_id: "activated_bundle_a",
            runtime_selection: { current_node_id: "node_a" },
          },
        },
      };
    },
  });

  const bundle = await runtime.loadFeatureRuntime("node_a");
  assert.equal(bundle.bundle_id, "activated_bundle_a");
  assert.equal(state.data.activatedRuntimeBundle, bundle);
  assert.equal(
    calls[0],
    "https://api.example.test/api/sessions/session-a/runtime/feature-snapshots?node_id=node_a",
  );
});

test("frontend data runtime advances static campaign and refreshes route atomically", async () => {
  const fetched = [];
  const state = {
    apiBase: "",
    dataMode: "static",
    sessionId: "",
    profile: { staticCampaignStageIndex: 0 },
    selectedNodeId: "gray_lantern_station",
    selectedMapNodeId: "gray_lantern_station",
    data: {
      battleConfig: { display_name: "灰灯驿站" },
      runWorldState: { progress: { phase: "opening_pressure" } },
    },
  };
  const runtime = createFrontendDataRuntime({
    state,
    location: {
      search: "?static=1",
      protocol: "http:",
      hostname: "127.0.0.1",
      origin: "http://127.0.0.1:5174",
    },
    saveProfile: (patch = {}) => {
      state.profile = { ...state.profile, ...patch };
    },
    fetchJsonImpl: async (url) => {
      fetched.push(url);
      return { progress: { phase: "northern_road" } };
    },
  });

  await runtime.loadCampaignRoute();
  const progress = await runtime.advanceStaticCampaignProgress("gray_lantern_station");
  assert.equal(progress.nextIndex, 1);
  assert.equal(progress.nextStep.node_id, "lamp_wick_store");
  assert.equal(state.profile.staticCampaignStageIndex, 1);
  assert.equal(state.data.campaignRouter.current.node_id, "lamp_wick_store");
  assert.equal(state.selectedMapNodeId, "lamp_wick_store");
  assert.match(fetched[0], /demo_after_stage_03_northern_road/);
});

test("battle update orchestration preserves simulation order and outcome boundary", () => {
  const order = [];
  const battle = { loopActive: true };
  const result = runBattleUpdate({
    battle,
    dt: 32,
    advanceBattleStep: ({ dt }) => {
      order.push(`advance:${dt}`);
      return { sampleDelivered: true };
    },
    onSampleDelivered: () => order.push("sample"),
    spawnEnemies: () => order.push("spawn"),
    updateEnemies: () => order.push("enemies"),
    updateDefenses: () => order.push("defenses"),
    updateTraps: () => order.push("traps"),
    updateEffects: () => order.push("effects"),
    resolveBattleOutcome: () => {
      order.push("outcome");
      return "victory";
    },
    finishBattle: (outcome) => order.push(`finish:${outcome}`),
  });

  assert.deepEqual(order, [
    "advance:32",
    "sample",
    "spawn",
    "enemies",
    "defenses",
    "traps",
    "effects",
    "outcome",
    "finish:victory",
  ]);
  assert.deepEqual(result, { updated: true, outcome: "victory", sampleDelivered: true });
});

test("frontend media catalog resolves compiled media, atlas frames, map layers, and cached images", () => {
  const data = {
    mediaManifest: {
      items: [{ asset_id: "compiled_tower", media_role: "tower_sprite", url: "/compiled/tower.png" }],
    },
    mediaAtlasManifest: {
      items: [{
        asset_id: "animated_tower",
        media_role: "tower_sprite",
        playback: { fps: 4, loop: true },
        spritesheet: { url: "/compiled/tower-sheet.png" },
        frames: [
          { x: 0, y: 0, width: 64, height: 96, url: "/compiled/frame-0.png" },
          { x: 64, y: 0, width: 64, height: 96, url: "/compiled/frame-1.png" },
        ],
      }],
    },
    runtimeMediaManifest: {
      items: [{ asset_id: "runtime_tower", media_role: "defense_sprite", url: "/runtime/tower.png" }],
    },
    mapComponentManifest: {
      items: [
        { node_id: "node_a", component_role: "road_band", url: "/components/node-a-road.png" },
        { node_id: "node_b", component_role: "road_band", url: "/components/node-b-road.png" },
        { component_role: "road_band", url: "/components/shared-road.png" },
      ],
    },
    strategicMapMarkerManifest: {
      atlas: { url: "/markers/atlas.png", width: 128 },
      items: [
        { media_role: "strategic_node_marker", node_kind: "battle_hotspot", state_hint: "active", frame: "hotspot" },
        { media_role: "strategic_node_marker", node_kind: "generic", frame: "generic" },
      ],
    },
    layeredMapVisualPackage: {
      layers: [{
        role: "composited",
        url: "/layered/node-a.svg",
        player_default: true,
        quality: {
          gate_status: "passed",
          alignment_status: "passed",
          player_visible_quality: "passed",
        },
      }],
    },
  };
  const createdImages = [];
  const catalog = createFrontendMediaCatalog({
    getData: () => data,
    getBattle: () => ({ elapsedMs: 260 }),
    getMapRuntimePackage: () => ({
      node_id: "node_a",
      visual_layers: [{
        role: "battle_control_sketch",
        url: "/maps/control.png",
        authority: "published_visual_layer",
        player_visible_quality: "passed",
      }],
    }),
    getCurrentNodeId: () => "node_a",
    resolveAssetUrl: (url) => `/repo${url}`,
    createImage: () => {
      const image = {};
      createdImages.push(image);
      return image;
    },
  });

  assert.equal(catalog.assetUrl("https://cdn.example/tower.png"), "https://cdn.example/tower.png");
  assert.deepEqual(catalog.mediaSpriteRef("animated_tower", "tower_sprite"), {
    url: "/repo/compiled/tower-sheet.png",
    source: { x: 64, y: 0, width: 64, height: 96 },
  });
  assert.deepEqual(
    catalog.battleObjectSpriteRef({ object_id: "compiled_tower", asset_kind: "tower_blueprint" }),
    { url: "/repo/compiled/tower.png", source: null },
  );
  assert.deepEqual(
    catalog.battleObjectSpriteRef({ object_id: "runtime_tower", asset_kind: "tower_blueprint" }),
    { url: "/repo/runtime/tower.png", source: null },
  );
  const activatedObject = {
    object_id: "activated_tower",
    asset_kind: "tower_blueprint",
    media_refs: {
      icon: { url: "/assets/activated/icon.png" },
      sprite: { image: "/assets/activated/sprite.png" },
    },
  };
  assert.deepEqual(catalog.battleObjectSpriteRef(activatedObject), {
    url: "/repo/assets/activated/sprite.png",
    source: null,
  });
  assert.deepEqual(catalog.battleObjectPreloadUrls([activatedObject]), [
    "/repo/assets/activated/sprite.png",
    "/repo/assets/activated/icon.png",
  ]);
  assert.deepEqual(
    catalog.mapComponentItems("road_band").map((item) => item.url),
    ["/components/node-a-road.png", "/components/shared-road.png"],
  );
  assert.equal(catalog.mapVisualUrl("battle_control_sketch", { playerOnly: true }), "/repo/maps/control.png");
  assert.equal(catalog.layeredMapVisualUrl(), "/repo/layered/node-a.svg");
  assert.equal(catalog.strategicMarkerAtlas().url, "/repo/markers/atlas.png");
  assert.equal(catalog.strategicMarkerItem("battle_hotspot", "active").frame, "hotspot");
  assert.equal(catalog.strategicMarkerItem("unknown", "locked").frame, "generic");
  const firstImage = catalog.getImage("/compiled/tower.png");
  assert.equal(catalog.getImage("/compiled/tower.png"), firstImage);
  assert.equal(firstImage.src, "/repo/compiled/tower.png");
  assert.equal(createdImages.length, 1);
});

test("battle DOM controller owns canvas lifecycle, HUD projection, and dialogue pause", () => {
  const classNames = new Set();
  const element = () => ({ innerHTML: "", textContent: "" });
  const elements = {
    battleStats: element(),
    battleTasks: element(),
    battleInfo: element(),
    battleTools: element(),
    battleToast: element(),
    dialogueLayer: element(),
    pauseButton: element(),
    speedButton: element(),
  };
  const context = recordingCanvasContext();
  const canvasListeners = new Map();
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => context,
    getBoundingClientRect: () => ({ width: 640, height: 360 }),
    addEventListener: (name, callback) => canvasListeners.set(name, callback),
  };
  elements.battleCanvas = canvas;
  const shell = {
    classList: {
      add: (name) => classNames.add(name),
      remove: (name) => classNames.delete(name),
    },
  };
  const windowListeners = new Map();
  const documentRef = {
    getElementById: (id) => elements[id] || null,
    querySelector: (selector) => selector === ".battle-shell" ? shell : null,
  };
  const windowRef = {
    devicePixelRatio: 2,
    addEventListener: (name, callback) => windowListeners.set(name, callback),
    removeEventListener: (name) => windowListeners.delete(name),
  };
  const battle = { elapsedMs: 400, paused: false, speed: 1 };
  const calls = [];
  const controller = createBattleDomController({
    getBattle: () => battle,
    ensureBattle: () => battle,
    documentRef,
    windowRef,
    onCanvasClick: () => {},
    onCanvasPointerMove: () => {},
    onCanvasPointerLeave: () => {},
    computeMetrics: (width, height) => ({ width, height }),
    installSmokeProbe: () => calls.push("smoke"),
    preloadImages: () => calls.push("preload"),
    shouldShowInitialDialogue: () => true,
    getInitialDialogue: () => ({ name: "守灯人", line: "守住路口。", portraitId: "keeper" }),
    resolvePortraitUrl: () => "/keeper.png",
    buildHudViewModel: () => ({
      stats: [{ label: "材料", value: 9 }],
      tasksTitle: "本场目标",
      taskItems: [{ title: "守住核心", text: "不要漏敌。" }],
      info: {
        avatarUrl: "/keeper.png",
        avatarAlt: "守灯人",
        title: "战术面板",
        items: [{ title: "下一波", text: "前锋" }],
      },
      toolbarTools: [{ id: "basic" }],
      toastText: "就绪",
      pauseText: "暂停",
      speedText: "1x",
    }),
    renderToolbar: () => "<button>基础灯栏</button>",
    imageTag: (url, alt) => `<img src="${url}" alt="${alt}">`,
    safeText: (value) => String(value),
    startLoop: () => calls.push("start"),
    stopLoop: () => calls.push("stop"),
  });

  assert.equal(controller.setupBattle(), true);
  assert.deepEqual(calls, ["smoke", "preload", "start"]);
  assert.equal(canvas.width, 1280);
  assert.equal(canvas.height, 720);
  assert.deepEqual(battle.metrics, { width: 640, height: 360 });
  assert.ok(canvasListeners.has("click"));
  assert.ok(canvasListeners.has("pointermove"));
  assert.ok(windowListeners.has("resize"));
  assert.equal(battle.dialogueOpen, true);
  assert.equal(battle.paused, true);
  assert.ok(classNames.has("is-dialogue-open"));
  assert.ok(elements.dialogueLayer.innerHTML.includes("守住路口"));
  controller.closeDialogue();
  assert.equal(battle.paused, false);
  assert.ok(elements.battleStats.innerHTML.includes("材料"));
  assert.ok(elements.battleTools.innerHTML.includes("基础灯栏"));
  controller.setBattleToast("已部署");
  assert.equal(battle.toast, "已部署");
  controller.cycleSpeed();
  assert.equal(battle.speed, 2);
  controller.stopBattleLoop();
  assert.ok(calls.includes("stop"));
  assert.equal(windowListeners.has("resize"), false);
});

test("battle orchestrator owns frame timing, HUD throttling, and cancellation", () => {
  const frames = [];
  const cancelled = [];
  const observedDt = [];
  let drawCount = 0;
  let domCount = 0;
  const battle = {
    loopActive: false,
    paused: false,
    speed: 2,
    elapsedMs: 0,
    lastFrameAt: 0,
    lastDomAt: -999,
  };
  const orchestrator = createBattleOrchestrator({
    getBattle: () => battle,
    requestFrame: (callback) => {
      frames.push(callback);
      return frames.length;
    },
    cancelFrame: (frameId) => cancelled.push(frameId),
    advanceBattleStep: ({ battle: current, dt }) => {
      observedDt.push(dt);
      current.elapsedMs += dt;
      return { sampleDelivered: false };
    },
    spawnEnemies: () => {},
    updateEnemies: () => {},
    updateDefenses: () => {},
    updateTraps: () => {},
    updateEffects: () => {},
    resolveBattleOutcome: () => null,
    finishBattle: () => {},
    drawBattle: () => { drawCount += 1; },
    updateBattleDom: () => { domCount += 1; },
  });

  assert.equal(orchestrator.start(), true);
  assert.equal(battle.loopActive, true);
  frames.shift()(100);
  frames.shift()(220);
  assert.deepEqual(observedDt, [0, 160]);
  assert.equal(drawCount, 2);
  assert.equal(domCount, 1);
  orchestrator.stop();
  assert.equal(battle.loopActive, false);
  assert.deepEqual(cancelled, [1]);
});

test("battle terrain renderer keeps reviewed backdrop and procedural fallback paths", () => {
  const context = recordingCanvasContext();
  let backdrop = null;
  const renderer = createBattleTerrainRenderer({
    getBattle: () => ({ elapsedMs: 0, metrics: { width: 320, height: 180, tileW: 32, tileH: 20, scale: 1 } }),
    getLayeredBackdropImage: () => backdrop,
    terrainFeatureSet: () => ({
      profile: { soil: ["#101010", "#202020", "#303030", "#404040"] },
      scenicRidges: [],
      bands: [],
      fieldEdgeProps: [],
      patches: [],
      darkPools: [],
      specks: [],
      debris: [],
      wisps: [],
    }),
    mapGrid: () => ({ width_cells: 4, height_cells: 3 }),
    runtimeMapSeed: () => 7,
    projectCell: (x, y) => ({ x: x * 20 + 80, y: y * 12 + 50 }),
    mapComponentImage: () => null,
    hashString: () => 11,
    makeSeededRandom: () => () => 0.5,
  });
  const metrics = {
    width: 320,
    height: 180,
    baseWidth: 1280,
    baseHeight: 720,
    imageOffsetX: 0,
    imageOffsetY: 0,
    imageWidth: 320,
    imageHeight: 180,
    tileW: 32,
    tileH: 20,
    scale: 1,
    safeArea: { left: 0, right: 0, top: 0, bottom: 0 },
  };

  assert.equal(renderer.drawBackdrop(context, metrics), false);
  assert.ok(context.calls.some(([name]) => name === "fillRect"));
  backdrop = { complete: true, naturalWidth: 1280, naturalHeight: 720 };
  assert.equal(renderer.drawBackdrop(context, metrics), true);
  assert.ok(context.calls.some(([name]) => name === "drawImage"));
});

test("battle road renderer consumes structured routes and smooths route turns", () => {
  const context = recordingCanvasContext();
  const componentRoles = [];
  const renderer = createBattleRoadRenderer({
    getBattle: () => ({ elapsedMs: 300, metrics: { width: 600, height: 360, tileW: 40, tileH: 24, scale: 1 } }),
    getVisualProfile: () => ({ road: { base: "#654321", crown: "#987654" } }),
    getRoutes: () => [{ route_id: "main", waypoints: [{ x: 0, y: 0 }, { x: 3, y: 2 }, { x: 6, y: 2 }] }],
    projectCell: (x, y) => ({ x: x * 40 + 40, y: y * 24 + 40 }),
    routeRoadWidthCells: () => 1,
    routeShoulderWidthScale: () => 1,
    runtimeMapSeed: () => 19,
    hashString: () => 23,
    makeSeededRandom: () => () => 0.5,
    drawComponentTextureEllipse: (_ctx, role) => { componentRoles.push(role); },
    terrainFeatureSet: () => ({ roadsideProps: [], accessTrails: [] }),
  });

  renderer.drawPath(context);
  assert.ok(context.calls.some(([name]) => name === "quadraticCurveTo"));
  assert.ok(context.calls.filter(([name]) => name === "stroke").length >= 6);
  assert.ok(componentRoles.includes("road_band"));
});

test("battle entity renderer draws runtime sprites, effects, and drag preview", () => {
  const context = recordingCanvasContext();
  const mediaRequests = [];
  const battle = {
    elapsedMs: 500,
    metrics: { scale: 1 },
    enemies: [{
      x: 2,
      y: 1,
      type: "shadow_tide_runner",
      slowUntil: 0,
      hitFlashUntil: 0,
      animSeed: 0.2,
      moveDx: 0.2,
      moveDy: 0.1,
      hp: 2,
      maxHp: 3,
    }],
    effects: [{ type: "ring", x: 1, y: 1, age: 100, duration: 500, scale: 1, color: "#9edcff" }],
    draggingTool: "basic",
    dragPointer: { x: 120, y: 90 },
    hoverCell: { x: 1, y: 1 },
    canvas: { getBoundingClientRect: () => ({ left: 20, top: 10, width: 400, height: 240 }) },
  };
  const renderer = createBattleEntityRenderer({
    getBattle: () => battle,
    projectCell: (x, y) => ({ x: x * 30 + 50, y: y * 20 + 50 }),
    mediaSpriteRef: (assetId, role) => {
      mediaRequests.push([assetId, role]);
      return { url: `/${assetId}.png`, source: null };
    },
    getImage: () => ({ complete: true, naturalWidth: 64, naturalHeight: 96 }),
  });

  renderer.drawEntities(context);
  renderer.drawEffects(context);
  renderer.drawDragGhost(context);
  assert.ok(context.calls.some(([name]) => name === "drawImage"));
  assert.ok(context.calls.some(([name]) => name === "ellipse"));
  assert.ok(mediaRequests.some(([assetId]) => assetId === "enemy_shadow_tide_runner"));
  assert.ok(mediaRequests.some(([assetId]) => assetId === "defense_basic_lantern_barricade"));
});

test("battle sprite flash follows transparent sprite pixels instead of painting a rectangle", () => {
  const context = recordingCanvasContext();
  const renderer = createBattleEntityRenderer({
    getBattle: () => ({ metrics: { scale: 1 } }),
    projectCell: (x, y) => ({ x, y }),
    mediaSpriteRef: () => null,
    getImage: () => ({ complete: true, naturalWidth: 64, naturalHeight: 96 }),
  });

  renderer.drawSprite(context, { url: "/tower.png", source: null }, 80, 90, 60, true);
  assert.equal(context.calls.filter(([name]) => name === "drawImage").length, 2);
  assert.equal(context.calls.filter(([name]) => name === "fillRect").length, 0);
});

test("battle deployment renderer previews a compiled tool with its reviewed sprite", () => {
  const context = recordingCanvasContext();
  const spriteCalls = [];
  const battle = {
    metrics: { tileW: 80, tileH: 42 },
    draggingTool: "asset_light_slow_tower_001",
    hoverCell: { x: 2, y: 3 },
  };
  const renderer = createBattleDeploymentRenderer({
    getBattle: () => battle,
    getSlots: () => [{ slot_id: "slot_a", position: { x: 2, y: 3 } }],
    isCellInGrid: () => true,
    projectCell: (x, y) => ({ x: x * 20, y: y * 12 }),
    makeSeededRandom: () => () => 0.5,
    runtimeMapSeed: () => 7,
    hashString: () => 11,
    slotFootprintScale: () => 1,
    getVisualProfile: () => ({ platform: {} }),
    drawComponentTextureEllipse: () => {},
    canPreviewToolAt: () => true,
    drawSprite: (_ctx, spriteRef) => spriteCalls.push(spriteRef),
    drawGroundGlow: () => {},
    mapSpriteSize: () => 62,
    resolveToolSpriteRef: (toolId) => ({ url: `/compiled/${toolId}.png`, source: null }),
  });

  renderer.drawBuildableTerraces(context);
  renderer.drawDeployHints(context, { layeredBackdrop: true });
  assert.deepEqual(spriteCalls, [{ url: "/compiled/asset_light_slow_tower_001.png", source: null }]);
  assert.equal(renderer.suggestedSockets()[0].slot_id, "slot_a");
});

test("battle semantic renderer consumes route-bound hazards and structured world semantics", () => {
  const context = recordingCanvasContext();
  const roles = [];
  let collapsedWalls = 0;
  const route = {
    route_id: "main_route",
    waypoints: [{ x: 0, y: 0 }, { x: 4, y: 2 }],
  };
  const renderer = createBattleSemanticRenderer({
    getBattle: () => ({ metrics: { tileW: 80, tileH: 42, scale: 1 } }),
    getResourceNodes: () => [{ node_id: "wick", position: { x: 2, y: 2 } }],
    getHazardZones: () => [{ zone_id: "fog", anchor_route_id: "main_route", path_t_range: { start: 0.2, end: 0.7 } }],
    getDefenseAnchors: () => [{ anchor_id: "gate", position: { x: 1, y: 1 }, influence_radius_cells: 2 }],
    getBlockedAreas: () => [{ area_id: "ruin", cells: [{ x: 3, y: 3 }] }],
    getVisualProfile: () => ({ objective: {}, road: {} }),
    getRoutes: () => [route],
    projectCell: (x, y) => ({ x: x * 20, y: y * 12 }),
    routeSamplesBetween: (selectedRoute, start, end) => {
      assert.equal(selectedRoute, route);
      assert.equal(start, 0.2);
      assert.equal(end, 0.7);
      return [{ x: 1, y: 0.5 }, { x: 3, y: 1.5 }];
    },
    routeRoadWidthCells: () => 1,
    traceRoutePath: (ctx, points) => {
      ctx.moveTo(points[0].x, points[0].y);
      ctx.lineTo(points[1].x, points[1].y);
    },
    drawGroundGlow: () => {},
    drawComponentTextureEllipse: (_ctx, role) => roles.push(role),
    drawCollapsedWall: () => { collapsedWalls += 1; },
    hashString: () => 5,
    isCellInGrid: () => true,
  });

  renderer.drawMapRuntimeStrongSemantics(context);
  assert.ok(roles.includes("hazard_marker"));
  assert.ok(roles.includes("resource_marker"));
  assert.ok(roles.includes("blocking_prop"));
  assert.equal(collapsedWalls, 1);
});

test("battle world renderer resolves each compiled defense through runtime media identity", () => {
  const context = recordingCanvasContext();
  const resolvedObjects = [];
  const spriteCalls = [];
  const dynamicSprite = { url: "/compiled/asset_light_slow_tower_001.png", source: null };
  const battle = {
    elapsedMs: 900,
    metrics: { tileW: 80, tileH: 42, scale: 1, width: 800, height: 500 },
    defenses: [{
      x: 2,
      y: 3,
      objectId: "asset_light_slow_tower_001",
      runtimeToolId: "asset_light_slow_tower_001",
      assetKind: "tower_blueprint",
      attackColor: "#77ddee",
      shotAt: 800,
    }],
    traps: [],
    mapPackage: { spawn_points: [] },
  };
  const renderer = createBattleWorldRenderer({
    getBattle: () => battle,
    getObjectives: () => ({ core_target: { position: { x: 0, y: 0 } } }),
    getVisualProfile: () => ({ objective: {}, spawn: {} }),
    terrainFeatureSet: () => ({ landmarks: [] }),
    projectCell: (x, y) => ({ x: x * 20, y: y * 12 }),
    drawComponentTextureEllipse: () => {},
    drawGroundGlow: () => {},
    drawSprite: (_ctx, spriteRef) => spriteCalls.push(spriteRef),
    drawTowerMuzzle: () => {},
    mapSpriteSize: () => 66,
    mediaSpriteRef: (assetId) => ({ url: `/fallback/${assetId}.png`, source: null }),
    resolveBattleObjectSpriteRef: (object) => {
      resolvedObjects.push(object.objectId);
      return dynamicSprite;
    },
    hashString: () => 3,
  });

  renderer.drawWorldObjects(context, { layeredBackdrop: true });
  assert.deepEqual(resolvedObjects, ["asset_light_slow_tower_001"]);
  assert.deepEqual(spriteCalls, [dynamicSprite]);
});

test("strategic map camera clamps zoom and keeps visible key nodes in frame", () => {
  const clamped = normalizeStrategicMapCamera({ zoom: 99, centerX: -100, centerY: 9999 });
  assert.equal(clamped.zoom, STRATEGIC_MAP_MAX_ZOOM);
  assert.equal(clamped.x, 0);
  assert.equal(clamped.y + clamped.height, 720);

  const map = {
    nodes: [
      { stable_internal_id: "city", kind: "main_city", position: { x: 220, y: 480 } },
      { stable_internal_id: "battle", kind: "battle_hotspot", position: { x: 1030, y: 250 } },
      { stable_internal_id: "hidden", kind: "resource_storage", position: { x: 1270, y: 710 } },
      { stable_internal_id: "decor", kind: "story", position: { x: 10, y: 10 } },
    ],
  };
  const camera = fitStrategicMapCamera(map, (node) => node.stable_internal_id !== "hidden");
  assert.ok(camera.x <= 220 && camera.x + camera.width >= 1030);
  assert.ok(camera.y <= 250 && camera.y + camera.height >= 480);
  assert.ok(camera.zoom >= 1 && camera.zoom <= 1.32);
});

test("strategic map controller updates DOM and suppresses click after drag", () => {
  const attributes = {};
  const classNames = new Set();
  const mapEl = {
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 500 }),
    classList: {
      add: (name) => classNames.add(name),
      remove: (name) => classNames.delete(name),
    },
    setPointerCapture: () => {},
    releasePointerCapture: () => {},
  };
  const svg = { setAttribute: (name, value) => { attributes[name] = value; } };
  const readout = { textContent: "" };
  const zoomOut = { disabled: false };
  const zoomIn = { disabled: false };
  const root = {
    querySelector(selector) {
      if (selector === ".strategic-map") return mapEl;
      if (selector === "[data-map-camera-svg]") return svg;
      if (selector === "[data-map-camera-readout]") return readout;
      if (selector === "[data-action='map-zoom-out']") return zoomOut;
      if (selector === "[data-action='map-zoom-in']") return zoomIn;
      return null;
    },
  };
  const state = {
    view: "map",
    mapCamera: { zoom: 1, centerX: 640, centerY: 360 },
    mapCameraMode: "auto",
    mapDrag: null,
    suppressMapClick: false,
  };
  const controller = createStrategicMapController({
    state,
    root,
    getMapData: () => ({
      nodes: [
        { kind: "main_city", position: { x: 260, y: 470 } },
        { kind: "battle_hotspot", position: { x: 980, y: 260 } },
      ],
    }),
  });
  const target = {
    closest(selector) {
      if (selector === ".strategic-map") return mapEl;
      return null;
    },
  };
  const beginEvent = {
    target,
    button: 0,
    pointerId: 7,
    clientX: 500,
    clientY: 250,
    preventDefault() {},
  };
  controller.beginStrategicMapDrag(beginEvent);
  assert.ok(state.mapDrag);
  assert.equal(classNames.has("is-dragging"), true);
  const centerBefore = state.mapDrag.camera.centerX;
  controller.updateStrategicMapDrag({
    pointerId: 7,
    clientX: 380,
    clientY: 250,
    preventDefault() {},
  });
  assert.equal(state.mapCameraMode, "manual");
  assert.ok(state.mapCamera.centerX > centerBefore);
  assert.ok(attributes.viewBox);
  assert.match(readout.textContent, /%$/);
  controller.finishStrategicMapDrag({ pointerId: 7 });
  assert.equal(state.mapDrag, null);
  assert.equal(state.suppressMapClick, true);
  assert.equal(classNames.has("is-dragging"), false);
});

test("runtime projection keeps new asset kinds out of default slots unless explicitly bound", () => {
  const projection = buildBattleToolProjection({
    battle: { basicUses: 2, sampleDelivered: false, sampleUses: 0, supportUses: 1 },
    activatedRuntimeBundle: {
      capabilities: {
        battle_objects: [
          {
            object_id: "ember_watch_tower_001",
            display_name: "余烬望塔",
            asset_kind: "tower_blueprint",
            behavior_abi: {
              placement: { mode: "build_slot" },
              cost: { resource: "materials", amount: 13 },
              effect_blocks: [{ kind: "damage", amount: 16 }],
              ui_surfaces: ["battle_hotbar"],
            },
          },
        ],
      },
    },
  });

  assert.equal(findBattleToolProjection("basic", projection).objectId, "basic_lantern_tower_001");
  assert.equal(findBattleToolProjection("basic", projection).name, "基础灯栏");
  assert.equal(findBattleToolProjection("ember_watch_tower_001", projection).runtimeOnly, true);
  assert.equal(projection.length, 4);
});

test("runtime projection supports explicit default binding and collision-safe dynamic ids", () => {
  const projection = buildBattleToolProjection({
    battle: { basicUses: 2, sampleDelivered: false, sampleUses: 0, supportUses: 1 },
    activatedRuntimeBundle: {
      capabilities: {
        battle_objects: [
          {
            object_id: "reinforced_lantern_001",
            tool_id: "basic",
            display_name: "加固灯栏",
            asset_kind: "tower_blueprint",
            behavior_abi: {
              effect_blocks: [{ kind: "damage" }],
              ui_surfaces: ["battle_hotbar"],
            },
          },
          {
            object_id: "incompatible_basic_support",
            tool_id: "basic",
            display_name: "错误类型覆盖测试",
            asset_kind: "support_item",
            behavior_abi: {
              effect_blocks: [{ kind: "aura" }],
              ui_surfaces: ["battle_hotbar"],
            },
          },
          {
            object_id: "storm_tower_alpha",
            tool_id: "storm/tower",
            asset_kind: "tower_blueprint",
            behavior_abi: {
              effect_blocks: [{ kind: "damage" }],
              ui_surfaces: ["battle_hotbar"],
            },
          },
          {
            object_id: "storm_tower_beta",
            tool_id: "storm?tower",
            asset_kind: "tower_blueprint",
            behavior_abi: {
              effect_blocks: [{ kind: "damage" }],
              ui_surfaces: ["battle_hotbar"],
            },
          },
        ],
      },
    },
  });

  assert.equal(findBattleToolProjection("basic", projection).objectId, "reinforced_lantern_001");
  assert.equal(findBattleToolProjection("basic", projection).name, "加固灯栏");
  assert.equal(findBattleToolProjection("basic_2", projection).objectId, "incompatible_basic_support");
  assert.equal(findBattleToolProjection("storm_tower", projection).objectId, "storm_tower_alpha");
  assert.equal(findBattleToolProjection("storm_tower_2", projection).objectId, "storm_tower_beta");
});

test("runtime tools deploy through behavior ABI whitelist", () => {
  const battle = {
    resources: 40,
    power: 8,
    cooldowns: {},
    defenses: [],
    traps: [],
    effects: [],
    enemies: [{ x: 5, y: 5, hp: 4, slowUntil: 0 }],
    deployedAssetIds: [],
    elapsedMs: 300,
  };
  const tower = {
    id: "ember_watch_tower_001",
    name: "余烬望塔",
    assetKind: "tower_blueprint",
    objectId: "ember_watch_tower_001",
    cost: { resource: "materials", amount: 13 },
    cooldownMs: 1500,
    mediaRefs: { sprite: { image: "/assets/activated/ember.png" } },
    behaviorAbi: {
      placement: { mode: "build_slot" },
      targeting: { range_cells: 3 },
      effect_blocks: [{ kind: "damage", amount: 16 }],
    },
  };
  const support = {
    id: "echo_bell_001",
    name: "回声铃",
    assetKind: "support_item",
    objectId: "echo_bell_001",
    cost: { resource: "light", amount: 3 },
    cooldownMs: 2500,
    behaviorAbi: {
      placement: { mode: "free_point" },
      targeting: { radius_cells: 2 },
      effect_blocks: [{ kind: "damage", amount: 8 }],
    },
  };

  assert.equal(
    canPreviewRuntimeToolAt({
      tool: tower,
      cell: { x: 2, y: 2 },
      canPlaceToolAt: () => true,
    }),
    true,
  );
  assert.equal(
    deployRuntimeTool({
      battle,
      cell: { x: 2, y: 2 },
      tool: tower,
      canPlaceToolAt: () => true,
      addEffect: (...args) => battle.effects.push({ args }),
      setBattleToast: () => {},
    }),
    true,
  );
  assert.equal(battle.resources, 27);
  assert.equal(battle.cooldowns.ember_watch_tower_001, 1500);
  assert.equal(battle.defenses[0].name, "余烬望塔");
  assert.equal(battle.defenses[0].damage, 2);
  assert.equal(battle.defenses[0].range, 3);
  assert.deepEqual(battle.defenses[0].mediaRefs, tower.mediaRefs);

  assert.equal(
    deployRuntimeTool({
      battle,
      cell: { x: 5, y: 5 },
      tool: support,
      canPlaceToolAt: () => false,
      addEffect: (...args) => battle.effects.push({ args }),
      addFloating: (...args) => battle.effects.push({ args }),
      setBattleToast: () => {},
    }),
    true,
  );
  assert.equal(battle.power, 5);
  assert.equal(battle.cooldowns.echo_bell_001, 2500);
  assert.equal(battle.enemies[0].hp, 3);
});

test("runtime deployment rejects locked tools and clamps unsafe ABI numbers", () => {
  const lockedBattle = {
    resources: 20,
    power: 5,
    cooldowns: {},
    defenses: [],
    traps: [],
    effects: [],
    enemies: [],
    deployedAssetIds: [],
    elapsedMs: 0,
  };
  const lockedTool = {
    id: "locked_tower",
    name: "未完成塔",
    assetKind: "tower_blueprint",
    objectId: "locked_tower",
    locked: true,
    cost: { resource: "materials", amount: 5 },
    cooldownMs: 1000,
    behaviorAbi: { placement: { mode: "build_slot" }, effect_blocks: [{ kind: "damage", amount: 8 }] },
  };
  assert.equal(
    deployRuntimeTool({
      battle: lockedBattle,
      cell: { x: 1, y: 1 },
      tool: lockedTool,
      canPlaceToolAt: () => true,
      setBattleToast: () => {},
    }),
    false,
  );
  assert.equal(lockedBattle.defenses.length, 0);

  const unsafeBattle = {
    resources: 10,
    power: 3,
    cooldowns: {},
    defenses: [],
    traps: [],
    effects: [],
    enemies: [{ x: 0, y: 0, hp: 5, slowUntil: 0 }],
    deployedAssetIds: [],
    elapsedMs: 0,
  };
  assert.equal(
    deployRuntimeTool({
      battle: unsafeBattle,
      cell: { x: 0, y: 0 },
      tool: {
        id: "unsafe_support",
        name: "异常支援",
        assetKind: "support_item",
        objectId: "unsafe_support",
        cost: { resource: "materials", amount: -5 },
        cooldownMs: -100,
        behaviorAbi: {
          placement: { mode: "free_point" },
          targeting: { radius_cells: 999 },
          effect_blocks: [{ kind: "damage", amount: 999 }],
        },
      },
      addEffect: () => {},
      addFloating: () => {},
      setBattleToast: () => {},
    }),
    true,
  );
  assert.equal(unsafeBattle.resources, 10);
  assert.equal(unsafeBattle.cooldowns.unsafe_support, 0);
  assert.equal(unsafeBattle.enemies[0].hp, 0);
});

test("battle rules and actions consume projected metadata", () => {
  const tool = {
    id: "basic",
    cost: { resource: "materials", amount: 7 },
    cooldownMs: 1234,
  };
  const battle = {
    basicUses: 1,
    resources: 10,
    cooldowns: { basic: 0 },
    defenses: [],
    deployedAssetIds: [],
    elapsedMs: 100,
    config: { basic_defense: { duration_ms: 1000 } },
  };
  const effects = [];
  const toasts = [];

  assert.equal(toolReady("basic", battle, tool), true);
  assert.equal(
    placeBasicDefense({
      battle,
      cell: { x: 2, y: 3 },
      tool,
      canPlaceToolAt: () => true,
      addEffect: (...args) => effects.push(args),
      setBattleToast: (text) => toasts.push(text),
    }),
    true,
  );
  assert.equal(battle.resources, 3);
  assert.equal(battle.cooldowns.basic, 1234);
  assert.equal(battle.basicUses, 0);
  assert.equal(battle.defenses[0].key, "2,3");
  assert.equal(effects.length, 1);
  assert.equal(toasts.at(-1), "基础灯栏已立起");
});

test("support action uses ABI cost and cooldown", () => {
  const battle = {
    supportUses: 1,
    resources: 12,
    cooldowns: { support: 0 },
    enemies: [{ x: 1, y: 1, hp: 3, slowUntil: 0 }],
    elapsedMs: 200,
  };
  const effects = [];
  const floating = [];
  const result = useSupportPulse({
    battle,
    cell: { x: 1, y: 1 },
    tool: { cost: { amount: 11 }, cooldownMs: 4321 },
    addEffect: (...args) => effects.push(args),
    addFloating: (...args) => floating.push(args),
    setBattleToast: () => {},
  });
  assert.equal(result, true);
  assert.equal(battle.resources, 1);
  assert.equal(battle.cooldowns.support, 4321);
  assert.equal(battle.enemies[0].hp, 2);
  assert.equal(effects.length, 1);
  assert.equal(floating.length, 1);
  assert.equal(toolUnavailableText("sample"), "样品尚未送达");
});

test("HUD view model remains pure projection of battle state", () => {
  const battle = {
    enemies: [{ waveIndex: 2 }],
    spawned: 2,
    config: { waves: [{}, {}], victory_condition: "守住核心" },
    coreHp: 8,
    optionalHp: 3,
    power: 4,
    resources: 30,
    leaks: 0,
    sampleDelivered: true,
    selectedTool: "basic",
    draggingTool: null,
    cooldowns: { basic: 250 },
    paused: false,
    speed: 2,
    toast: "已部署",
    toastUntil: 0,
    elapsedMs: 100,
  };
  const toolbarTools = buildBattleToolbarViewModel({
    battle,
    tools: [{ id: "basic", cooldownMs: 1000, meta: [], locked: false }],
    isToolReady: () => true,
  });
  assert.equal(toolCooldownFill({ battle, tool: toolbarTools[0] }), "75%");
  assert.equal(toolbarTools[0].isSelected, true);
  const hud = buildBattleHudViewModel({
    battle,
    objectives: { core_target: { durability: 10 }, optional_targets: [{ durability: 4 }] },
    sampleProgressText: "封装中",
    nextWaveLabel: "第二波",
    npcAvatarUrl: "/npc.png",
    toolbarTools,
  });
  assert.equal(hud.stats[0].value, "2/2");
  assert.equal(hud.taskItems[2].text, "折光绊索已送达。");
  assert.equal(hud.toolbarTools.length, 1);
});

test("map runtime accessors normalize package-first data and render plan geometry", () => {
  const mapPackage = {
    grid: { width_cells: 20, height_cells: 12 },
    objectives: { core_target: { target_id: "core", durability: 9 } },
    path_routes: [{ route_id: "main", waypoints: [{ x: 1, y: 2 }, { x: 3, y: 4 }] }],
    resource_nodes: [{ node_id: "r1" }],
  };
  const battleConfig = {
    grid: { width_cells: 1, height_cells: 1 },
    paths: [{ stable_internal_id: "fallback", waypoints: [{ x: 0, y: 0 }] }],
  };
  const plan = {
    layers: [
      {
        kind: "road_band",
        operations: [
          {
            semantic_ref: { kind: "path_route", id: "main" },
            geometry: { width_cells: 1.2 },
          },
        ],
      },
      {
        kind: "road_edge",
        operations: [
          {
            semantic_ref: { kind: "path_route", id: "main" },
            geometry: { shoulder_width_cells: 0.3 },
          },
        ],
      },
      {
        kind: "build_slot_platform",
        operations: [
          {
            semantic_ref: { kind: "build_slot", id: "slot_a" },
            geometry: { footprint: { width_cells: 1.2, height_cells: 0.8 } },
          },
        ],
      },
    ],
  };
  assert.deepEqual(mapGridFromRuntime({ mapPackage, battleConfig }), {
    width_cells: 20,
    height_cells: 12,
  });
  assert.equal(mapObjectivesFromRuntime({ mapPackage, battleConfig }).core_target.target_id, "core");
  assert.equal(pathWaypointsFromRuntime({ mapPackage, battleConfig, routeId: "main" }).length, 2);
  assert.equal(allPathRoutesFromRuntime({ mapPackage, battleConfig })[0].route_id, "main");
  assert.equal(runtimeSemanticList(mapPackage, "resource_nodes").length, 1);
  assert.equal(routeRoadWidthCellsFromPlan(plan, { route_id: "main" }), 0.95);
  assert.equal(routeShoulderWidthScaleFromPlan(plan, { route_id: "main" }), 1.2);
  assert.equal(slotFootprintScaleFromPlan(plan, { slot_id: "slot_a" }, "width"), 1.2);
  assert.equal(colorFromStylePack({ palette: { accent: "#aabbcc" } }, "accent", "#fff"), "#aabbcc");
  assert.equal(
    rgbaFromStylePack({ palette: { accent: "#aabbcc" } }, "accent", 0.5, "fallback"),
    "rgba(170,187,204,0.5)",
  );
});

test("battle map adapter owns runtime package projection and canvas hit testing", () => {
  const mapPackage = {
    grid: { width_cells: 10, height_cells: 8 },
    objectives: {
      core_target: { target_id: "core", position: { x: 8, y: 6 }, durability: 10 },
      optional_targets: [{ target_id: "relay", position: { x: 6, y: 2 }, durability: 4 }],
    },
    path_routes: [
      { route_id: "north", waypoints: [{ x: 0, y: 1 }, { x: 4, y: 1 }, { x: 8, y: 6 }] },
      { route_id: "south", waypoints: [{ x: 0, y: 6 }, { x: 4, y: 5 }, { x: 8, y: 6 }] },
    ],
    spawn_points: [
      { spawn_id: "south_spawn", route_id: "south", position: { x: 0, y: 6 } },
      { spawn_id: "north_spawn", route_id: "north", position: { x: 0, y: 1 } },
    ],
    build_slots: [
      { slot_id: "slot_a", position: { x: 3, y: 3 }, allowed_asset_kinds: ["tower_blueprint"] },
    ],
    resource_nodes: [{ node_id: "ore_a", position: { x: 2, y: 5 } }],
    hazard_zones: [{ zone_id: "mist_a", anchor_route_id: "north" }],
    defense_anchors: [{ anchor_id: "anchor_a", position: { x: 7, y: 5 } }],
    blocked_areas: [{ area_id: "wall_a", cells: [{ x: 5, y: 4 }] }],
  };
  const battle = {
    defenses: [{ key: "3,3" }],
    traps: [],
    canvas: {
      getBoundingClientRect: () => ({ left: 10, top: 20, right: 1450, bottom: 920 }),
    },
    metrics: null,
  };
  const adapter = createBattleMapAdapter({
    getBattle: () => battle,
    getMapPackage: () => mapPackage,
    getBattleConfig: () => ({ grid: { width_cells: 1, height_cells: 1 } }),
  });

  assert.deepEqual(adapter.mapGrid(), { width_cells: 10, height_cells: 8 });
  assert.equal(adapter.mapObjectives().core_target.target_id, "core");
  assert.equal(adapter.allPathRoutes().length, 2);
  assert.equal(adapter.routeForSpawn(0).route_id, "south");
  assert.equal(adapter.buildSlots()[0].slot_id, "slot_a");
  assert.equal(adapter.slotAt({ x: 3, y: 3 }).slot_id, "slot_a");
  assert.equal(adapter.isOccupied({ x: 3, y: 3 }), true);
  assert.equal(adapter.mapResourceNodes()[0].node_id, "ore_a");
  assert.equal(adapter.mapHazardZones()[0].zone_id, "mist_a");
  assert.equal(adapter.mapDefenseAnchors()[0].anchor_id, "anchor_a");
  assert.equal(adapter.mapBlockedAreas()[0].area_id, "wall_a");

  battle.metrics = adapter.computeBattleMetrics(1440, 900);
  const projected = adapter.projectCell(4, 5);
  const roundTrip = adapter.screenToCell(projected.x, projected.y);
  assert.equal(roundTrip.x, 4);
  assert.equal(roundTrip.y, 5);
  assert.deepEqual(
    adapter.cellFromCanvasEvent({ clientX: projected.x + 10, clientY: projected.y + 20 }),
    { x: 4, y: 5 },
  );
  assert.equal(adapter.cellFromCanvasEvent({ clientX: 5, clientY: 5 }), null);
});

test("page feature controllers project injected runtime state without browser globals", () => {
  const state = {
    sessionId: "session-a",
    profile: {},
    dataMode: "static",
    selectedOptions: { creativity_mode: "stable", player_origin: "scout" },
    openingIndex: 0,
    intentText: "把辉晶做成减速灯塔",
    research: { status: "proposed" },
    data: {
      opening: { segments: [{ kind: "black_screen_text", lines: ["长夜未尽"] }] },
      materials: [{ material_id: "glow_crystal", quantity: 2 }],
    },
    battleOutcome: { result: "victory", protected_core_hp: 8, leaked_enemy_count: 1 },
    settlement: null,
    evidence: null,
  };
  const safeText = (value) => String(value ?? "");
  const imageTag = (url, alt) => `<img src="${url}" alt="${alt}">`;
  const root = {};
  const navigations = [];
  const onboarding = createOnboardingFeatureController({
    root,
    getState: () => state,
    getWorldConfig: () => ({
      worldbook_display_name: "测试世界",
      creativity_mode: { options: [{ id: "stable", display_name: "稳健", summary: "受控" }] },
      player_origin: { options: [{ id: "scout", display_name: "斥候", summary: "先行" }] },
    }),
    defaultWorldConfig: {},
    screenHeader: (title) => `<header>${title}</header>`,
    safeText,
    navigate: (view) => navigations.push(view),
    renderApp: () => {},
  });
  onboarding.renderProfile();
  assert.match(root.innerHTML, /继续当前体验/);
  onboarding.renderWorldConfig();
  assert.match(root.innerHTML, /测试世界/);
  assert.match(root.innerHTML, /option-button is-selected/);
  onboarding.renderOpening();
  assert.match(root.innerHTML, /长夜未尽/);
  assert.deepEqual(navigations, []);

  const workshopRoot = {};
  const workshop = createWorkshopFeatureController({
    root: workshopRoot,
    getState: () => state,
    getBriefing: () => ({
      summary: "守住旧塔",
      threat: { enemy_traits: "高速", approach_direction: "北路" },
      protection_targets: [{ display_name: "旧塔", summary: "不能失守" }],
      available_materials: state.data.materials,
    }),
    getBattleConfig: () => ({ sample_asset: { display_name: "回光棱镜" } }),
    getCurrentNodeId: () => "old_signal_tower",
    getCurrentNodeDisplayName: () => "旧信号塔",
    screenHeader: (title) => `<header>${title}</header>`,
    safeText,
    imageTag,
    npcPortraitUrl: () => "/npc.png",
    sampleIconUrl: () => "/sample.png",
    materialName: () => "辉晶",
    getSurfaceContributions: () => [
      {
        kind: "proposal_hint",
        payload: { title: "编译后的回光棱镜", summary: "让旧塔回光形成短时迟滞。" },
      },
      {
        kind: "participant_notice",
        payload: { display_name: "巡灯使", summary: "可校准回光角度。" },
      },
    ],
  });
  assert.equal(workshop.currentProposal().name, "编译后的回光棱镜");
  workshop.renderWorkshop();
  assert.match(workshopRoot.innerHTML, /把辉晶做成减速灯塔/);
  assert.match(workshopRoot.innerHTML, /旧信号塔应急改造间/);
  assert.match(workshopRoot.innerHTML, /巡灯使/);

  const settlementRoot = {};
  const settlement = createSettlementFeatureController({
    root: settlementRoot,
    getState: () => state,
    getCurrentNodeId: () => "old_signal_tower",
    displayNameForNodeId: () => "旧信号塔",
    screenHeader: (title) => `<header>${title}</header>`,
    safeText,
    imageTag,
    npcPortraitUrl: () => "/npc.png",
    getSurfaceContributions: () => [
      {
        kind: "settlement_note",
        slot: "result_summary",
        payload: { summary: "编译结算确认旧塔稳定。" },
      },
      {
        kind: "settlement_note",
        slot: "world_delta",
        payload: { summary: "北路分潮线显现。" },
      },
    ],
  });
  assert.match(settlement.buildLocalSettlement(state.battleOutcome).battle_summary, /旧信号塔/);
  settlement.renderSettlement();
  assert.match(settlementRoot.innerHTML, /节点守住/);
  assert.match(settlementRoot.innerHTML, /核心耐久/);
  assert.match(settlementRoot.innerHTML, /编译结算确认旧塔稳定/);
  assert.match(settlementRoot.innerHTML, /北路分潮线显现/);
});

test("narrative feature projection accepts only node-targeted beats for battle intro", () => {
  const projection = createNarrativeFeatureProjection({
    getSurfaceContributions: () => [
      {
        contributionId: "generic_history",
        kind: "narrative_beat",
        targetNodeId: "",
        payload: { speaker_name: "长夜回响", text: "旧日记录不应打断当前战斗。" },
      },
      {
        contributionId: "compiled_intro",
        kind: "narrative_beat",
        targetNodeId: "node_a",
        payload: {
          speaker_name: "巡灯使",
          portrait_asset_id: "npc_patrol_portrait",
          text: "北路影潮已经转向。",
        },
      },
    ],
  });
  const fallback = { name: "守灯人", line: "守住这里。", portraitId: "keeper" };
  assert.deepEqual(projection.battleIntro("node_a", fallback), {
    name: "巡灯使",
    line: "北路影潮已经转向。",
    portraitId: "npc_patrol_portrait",
    contributionId: "compiled_intro",
  });
  assert.deepEqual(projection.battleIntro("node_b", fallback), fallback);
});

test("root event router installs one delegated lifecycle and dispatches injected commands", () => {
  function eventTarget() {
    const listeners = new Map();
    return {
      listeners,
      addEventListener(type, handler) {
        const values = listeners.get(type) || [];
        values.push(handler);
        listeners.set(type, values);
      },
      removeEventListener(type, handler) {
        listeners.set(type, (listeners.get(type) || []).filter((value) => value !== handler));
      },
    };
  }
  const root = eventTarget();
  const windowRef = eventTarget();
  const calls = [];
  const actionTarget = {
    dataset: { action: "select-tool", tool: "dynamic_tower" },
    closest: (selector) => (selector === "[data-action]" ? actionTarget : null),
  };
  const toolbarTarget = {
    dataset: { tool: "dynamic_tower" },
    closest: (selector) => (selector === ".toolbar-card[data-tool]" ? toolbarTarget : null),
  };
  const router = createRootEventRouter({
    root,
    windowRef,
    actionHandlers: { "select-tool": (target) => calls.push(["action", target.dataset.tool]) },
    beginToolDrag: (tool) => calls.push(["drag", tool]),
    updateToolDrag: () => {},
    finishToolDrag: () => {},
    cancelToolDrag: () => {},
    beginStrategicMapDrag: () => calls.push(["map-drag"]),
    updateStrategicMapDrag: () => {},
    finishStrategicMapDrag: () => {},
    handleStrategicMapWheel: () => true,
    updateIntent: (value) => calls.push(["intent", value]),
    canBeginToolDrag: (event) => event.button === 0,
  });

  router.install();
  router.install();
  assert.equal(root.listeners.get("click").length, 1);
  assert.equal(windowRef.listeners.get("pointermove").length, 2);
  root.listeners.get("click")[0]({ target: actionTarget, preventDefault() {}, stopPropagation() {} });
  root.listeners.get("pointerdown")[0]({ target: toolbarTarget, button: 0 });
  root.listeners.get("input")[0]({ target: { dataset: { field: "intent" }, value: "新构想" } });
  assert.deepEqual(calls, [["action", "dynamic_tower"], ["drag", "dynamic_tower"], ["intent", "新构想"]]);
  router.uninstall();
  assert.equal(root.listeners.get("click").length, 0);
  assert.equal(windowRef.listeners.get("pointermove").length, 0);
});

test("feature gate registry admits only active runtime-safe declarative contributions", () => {
  let bundle = {
    frontend_role: "consume_only",
    status: "active",
    activation_receipt: { status: "activated", runtime_safe_scan: "passed" },
    runtime_selection: { activation_applied: true },
    quarantine: { status_values: ["quarantined", "rolled_back"] },
    feature_gates: { strategic_surface: { enabled: true } },
    feature_snapshots: {
      strategic_map: {
        schema_version: "frontend_feature_snapshot.v0.1",
        feature_id: "strategic_map",
        surface: "strategic_map",
        status: "active",
        required_gates: ["strategic_surface"],
        contributions: [
          {
            schema_version: "frontend_surface_contribution.v0.1",
            contribution_id: "compiled_objective_a",
            feature_id: "strategic_map",
            surface: "strategic_map",
            kind: "objective_card",
            slot: "objective_overlay",
            visibility: "player_visible",
            priority: 20,
            target_node_id: "node_a",
            payload: {
              title: "北路预警",
              summary: "守住当前节点。",
              node_id: "node_a",
              html: "<script>ignored()</script>",
            },
          },
          {
            schema_version: "frontend_surface_contribution.v0.1",
            contribution_id: "unsafe_component",
            feature_id: "strategic_map",
            surface: "strategic_map",
            kind: "custom_component",
            slot: "objective_overlay",
            visibility: "player_visible",
            payload: { title: "不得进入" },
          },
        ],
      },
      battle: {
        schema_version: "frontend_feature_snapshot.v0.1",
        feature_id: "battle",
        surface: "battle_canvas",
        status: "active",
      },
    },
    capabilities: { battle_objects: [{ object_id: "tower_a" }] },
  };
  const registry = createFeatureGateRegistry({ getBundle: () => bundle });
  assert.equal(registry.evaluateBundle().active, true);
  assert.equal(registry.featureEnabled("strategic_map"), true);
  assert.equal(registry.capabilityList("battle_objects", "battle")[0].object_id, "tower_a");
  const contributions = registry.surfaceContributions("strategic_map", {
    surface: "strategic_map",
    nodeId: "node_a",
  });
  assert.equal(contributions.length, 1);
  assert.equal(contributions[0].payload.title, "北路预警");
  assert.equal("html" in contributions[0].payload, false);

  bundle.feature_snapshots.strategic_map.contributions.push({
    schema_version: "frontend_surface_contribution.v0.1",
    contribution_id: "wrong_parent",
    feature_id: "workshop",
    surface: "strategic_map",
    kind: "objective_card",
    slot: "objective_overlay",
    visibility: "player_visible",
    payload: { title: "越界", summary: "不得进入" },
  });
  assert.equal(registry.surfaceContributions("strategic_map").length, 1);

  bundle.feature_snapshots.strategic_map.schema_version = "frontend_feature_snapshot.v9";
  assert.equal(registry.featureEnabled("strategic_map"), false);
  bundle.feature_snapshots.strategic_map.schema_version = "frontend_feature_snapshot.v0.1";

  bundle = { ...bundle, status: "quarantined" };
  assert.equal(registry.evaluateBundle().active, false);
  assert.deepEqual(registry.capabilityList("battle_objects", "battle"), []);
  assert.deepEqual(registry.surfaceContributions("strategic_map"), []);
});

test("strategic map projection merges compiled contributions with world and map state", () => {
  const contributions = [
    {
      contributionId: "objective_compiled",
      kind: "objective_card",
      payload: { title: "编译目标", summary: "保护新生节点" },
    },
    {
      contributionId: "npc_compiled",
      kind: "node_participant",
      payload: { npc_id: "npc_dynamic", display_name: "巡灯使", summary: "可提供路径校准" },
    },
  ];
  const map = {
    display_name: "动态态势图",
    nodes: [
      { stable_internal_id: "node_a", display_name: "节点甲", state: "contested", position: { x: 100, y: 100 } },
      { stable_internal_id: "node_hidden", display_name: "隐藏节点", state: "unknown", position: { x: 300, y: 200 } },
    ],
    floating_events: [{ stable_internal_id: "fallback", display_name: "默认目标", summary: "默认" }],
  };
  const projection = createStrategicMapProjection({
    getMapData: () => map,
    getRunWorldState: () => ({
      map_nodes: [{ node_id: "node_hidden", visibility: "hidden" }],
      tasks: [{ task_id: "task_world", status: "active", title: "世界任务", summary: "推进世界线" }],
      npcs: [{ npc_id: "npc_world", display_name: "灯路斥候", location_node_id: "node_a", gameplay_roles: ["scout"] }],
    }),
    getProfile: () => ({}),
    getSelectedNodeId: () => "node_a",
    getCurrentNodeId: () => "node_a",
    fallbackNodeId: "node_a",
    getSurfaceContributions: () => contributions,
  });
  assert.equal(projection.selectedMapNode().stable_internal_id, "node_a");
  assert.equal(projection.mapNodeVisible(map.nodes[1]), false);
  assert.deepEqual(projection.objectiveCards(map).map((item) => item.title), ["编译目标", "世界任务"]);
  assert.deepEqual(projection.participantCards("node_a").map((item) => item.title), ["巡灯使", "灯路斥候"]);

  const root = {};
  const feature = createStrategicMapFeatureController({
    root,
    projection,
    camera: {
      active: () => ({ centerX: 640, centerY: 360, zoom: 1 }),
      set: (value) => value,
      viewBox: () => "0 0 1280 720",
      mode: () => "auto",
      minZoom: 0.5,
      maxZoom: 2,
    },
    runtime: {
      currentNodeId: () => "node_a",
      isCurrentNode: (nodeId) => nodeId === "node_a",
      nodePlayable: () => true,
      routeCurrent: () => ({ node_id: "node_a" }),
      routeNext: () => null,
    },
    presentation: {
      routePath: () => "M 0 0 L 1 1",
      darkRegionMarkup: () => "",
      threatEdgeMarkup: () => "",
      markerPreloadUrls: () => [],
      getImage: () => null,
      assetUrl: (url) => url,
      safeText: (value) => String(value ?? ""),
      nodeColor: () => "#fff",
      nodeMarkerMarkup: () => "<circle />",
      nodeLabel: (node) => `<text>${node.display_name}</text>`,
      screenHeader: (title) => `<header>${title}</header>`,
    },
  });
  feature.renderMap();
  assert.match(root.innerHTML, /动态态势图/);
  assert.match(root.innerHTML, /编译目标/);
  assert.match(root.innerHTML, /巡灯使/);
  assert.doesNotMatch(root.innerHTML, /隐藏节点/);
});

test("app flow orchestrator limits compiled navigation to registered player surfaces", () => {
  let view = "profile";
  const calls = [];
  const flow = createAppFlowOrchestrator({
    getView: () => view,
    setView: (next) => {
      view = next;
    },
    stopCurrentActivity: () => calls.push("stop"),
    renderers: {
      profile: () => calls.push("profile"),
      map: () => calls.push("map"),
      workshop: () => calls.push("workshop"),
    },
  });
  assert.equal(flow.viewForSurface("strategic_map"), "map");
  assert.equal(flow.viewForSurface("arbitrary_script_surface"), null);
  assert.equal(flow.navigateToSurface("strategic_map"), "map");
  assert.equal(view, "map");
  assert.deepEqual(calls, ["stop", "map"]);
  assert.equal(flow.navigate("unknown-player-page"), "profile");
  assert.equal(view, "profile");
  assert.deepEqual(calls, ["stop", "map", "stop", "profile"]);
});
