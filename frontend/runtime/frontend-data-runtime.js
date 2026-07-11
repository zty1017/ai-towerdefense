import { fetchJson, queryFlag, queryParam, unwrapPayload } from "./api-client.js";
import {
  DEFAULT_WORLD_CONFIG,
  NODE_ID,
  STATIC_CAMPAIGN_STATE_PATHS,
  STATIC_CAMPAIGN_STEPS,
  STATIC_NODE_PATHS,
  STATIC_PATHS,
} from "./content-registry.js";
import { resolveStaticAssetUrl } from "./media-resolver.js";

function defaultLocation() {
  return (globalThis.window && globalThis.window.location) || globalThis.location || { search: "" };
}

export function createFrontendDataRuntime({
  state,
  saveProfile = () => {},
  location = defaultLocation(),
  fetchJsonImpl = fetchJson,
  resolveStaticAssetUrlImpl = resolveStaticAssetUrl,
} = {}) {
  if (!state || typeof state !== "object") {
    throw new TypeError("createFrontendDataRuntime requires mutable state");
  }

  function apiUrl(path) {
    return `${state.apiBase}${path}`;
  }

  async function apiGet(path, timeoutMs = 3600) {
    return unwrapPayload(await fetchJsonImpl(apiUrl(path), {}, timeoutMs));
  }

  async function apiPost(path, body = {}, timeoutMs = 9000) {
    return unwrapPayload(
      await fetchJsonImpl(
        apiUrl(path),
        {
          method: "POST",
          body: JSON.stringify(body),
        },
        timeoutMs,
      ),
    );
  }

  function isApiMode() {
    return state.dataMode === "api";
  }

  function sessionApiPath(path = "") {
    return `/api/sessions/${encodeURIComponent(state.sessionId)}${path}`;
  }

  async function fetchOptionalJson(url, fallback = null, timeoutMs = 3600) {
    try {
      return await fetchJsonImpl(url, {}, timeoutMs);
    } catch {
      return fallback;
    }
  }

  function assertNodeBound(expectedNodeId, values) {
    const mismatches = values
      .map(([label, value]) => [label, value && typeof value === "object" ? value.node_id : null])
      .filter(([, nodeId]) => nodeId && nodeId !== expectedNodeId);
    if (mismatches.length) {
      const detail = mismatches.map(([label, nodeId]) => `${label}:${nodeId}`).join(", ");
      throw new Error(`节点运行数据错配，期望 ${expectedNodeId}，收到 ${detail}`);
    }
  }

  function forceStaticDataMode() {
    return queryFlag("static", location) || queryFlag("staticMode", location);
  }

  function battleVisualSmokeMode() {
    return queryFlag("battleVisualSmoke", location);
  }

  function battleDialogueSmokeMode() {
    return queryFlag("battleDialogueSmoke", location);
  }

  function battleVisualHoldMode() {
    return battleVisualSmokeMode() && queryFlag("battleVisualHold", location);
  }

  function flowVisualSmokeMode() {
    return queryFlag("flowVisualSmoke", location) || battleVisualSmokeMode();
  }

  function staticCampaignStageIndex() {
    const raw = Number((state.profile || {}).staticCampaignStageIndex ?? 0);
    if (!Number.isFinite(raw)) return 0;
    return Math.max(0, Math.min(STATIC_CAMPAIGN_STEPS.length, Math.floor(raw)));
  }

  function staticCampaignComplete() {
    return staticCampaignStageIndex() >= STATIC_CAMPAIGN_STEPS.length;
  }

  function staticCampaignCurrentStep() {
    return STATIC_CAMPAIGN_STEPS[staticCampaignStageIndex()] || null;
  }

  function staticCampaignStepForNode(nodeId) {
    return STATIC_CAMPAIGN_STEPS.find((step) => step.node_id === nodeId) || null;
  }

  function staticCampaignStepIndexForNode(nodeId) {
    return STATIC_CAMPAIGN_STEPS.findIndex((step) => step.node_id === nodeId);
  }

  function staticCampaignStatePath() {
    return (
      STATIC_CAMPAIGN_STATE_PATHS[staticCampaignStageIndex()] ||
      STATIC_CAMPAIGN_STATE_PATHS[STATIC_CAMPAIGN_STATE_PATHS.length - 1]
    );
  }

  function requestedStaticNodeId() {
    const requested = queryParam("nodeId", location) || queryParam("node", location);
    return Object.prototype.hasOwnProperty.call(STATIC_NODE_PATHS, requested) ? requested : "";
  }

  function staticNodeId() {
    const requested = requestedStaticNodeId();
    if (flowVisualSmokeMode() && requested) return requested;
    const step = staticCampaignCurrentStep();
    if (step && step.node_id) return step.node_id;
    return state.selectedNodeId && Object.prototype.hasOwnProperty.call(STATIC_NODE_PATHS, state.selectedNodeId)
      ? state.selectedNodeId
      : NODE_ID;
  }

  function staticNodePathsFor(nodeId) {
    return STATIC_NODE_PATHS[nodeId] || STATIC_NODE_PATHS[NODE_ID];
  }

  function staticNodePaths() {
    return staticNodePathsFor(staticNodeId());
  }

  function staticPathFor(key) {
    return staticNodePaths()[key] || STATIC_PATHS[key];
  }

  function staticOptionalPathFor(key) {
    return staticNodePaths()[key] || STATIC_PATHS[key] || "";
  }

  function fetchStaticJson(key, timeoutMs = 3600) {
    return fetchJsonImpl(staticPathFor(key), {}, timeoutMs);
  }

  function fetchOptionalStaticJson(key, fallback = null, timeoutMs = 3600) {
    const path = staticOptionalPathFor(key);
    if (!path) return Promise.resolve(fallback);
    return fetchOptionalJson(path, fallback, timeoutMs);
  }

  function apiCandidates() {
    if (forceStaticDataMode()) return [];
    const explicit = queryParam("apiBase", location) || queryParam("api", location);
    const candidates = [];
    if (explicit) candidates.push(explicit);
    if (String(location.protocol || "").startsWith("http") && location.origin) {
      candidates.push(location.origin);
    }
    if (["localhost", "127.0.0.1"].includes(location.hostname)) {
      candidates.push("http://127.0.0.1:8000");
      candidates.push("http://localhost:8000");
    }
    return [...new Set(candidates.map((item) => item.replace(/\/+$/, "")))];
  }

  async function detectApiBase() {
    for (const candidate of apiCandidates()) {
      try {
        const health = await fetchJsonImpl(`${candidate}/api/health`, {}, 1200);
        if (health && health.status === "ok") return candidate;
      } catch {
        // Continue through candidates before selecting the static adapter.
      }
    }
    return "";
  }

  async function ensureSession() {
    if (state.sessionId) {
      try {
        await apiGet(sessionApiPath(), 1800);
        return;
      } catch {
        state.sessionId = "";
      }
    }
    const response = await fetchJsonImpl(
      apiUrl("/api/sessions"),
      {
        method: "POST",
        body: JSON.stringify({ display_name: "本地档案" }),
      },
      3200,
    );
    state.sessionId = response.session_id;
    saveProfile();
  }

  function routeData() {
    return state.data.campaignRouter || null;
  }

  function routeCurrent() {
    const route = routeData();
    return (route && route.current) || null;
  }

  function routeNext() {
    const route = routeData();
    return (route && route.next) || null;
  }

  function currentNodeId() {
    return (routeCurrent() || {}).node_id || state.selectedNodeId || NODE_ID;
  }

  function currentNodeDisplayName() {
    return (
      (routeCurrent() || {}).display_name ||
      (state.data.battleConfig || {}).display_name ||
      "灰灯驿站"
    );
  }

  function displayNameForNodeId(nodeId) {
    const node = ((state.data.map || {}).nodes || []).find(
      (item) => item.stable_internal_id === nodeId,
    );
    return (
      (node && node.display_name) ||
      (staticNodePathsFor(nodeId) || {}).displayName ||
      nodeId ||
      "节点"
    );
  }

  function routeNodeFor(nodeId) {
    const route = routeData();
    const nodes = route && Array.isArray(route.route) ? route.route : [];
    return nodes.find((node) => node.node_id === nodeId) || null;
  }

  function nodePlayable(nodeId) {
    const routeNode = routeNodeFor(nodeId);
    if (!routeNode) return nodeId === currentNodeId() && Boolean(routeCurrent());
    return routeNode.playable === true;
  }

  function isCurrentNode(nodeId) {
    const current = routeCurrent();
    return Boolean(current && current.node_id === nodeId);
  }

  function buildBriefingFallback(nodeId) {
    const nodes = ((state.data.map || {}).nodes || []);
    const node = nodes.find((item) => item.stable_internal_id === nodeId) || {};
    const pack = state.data.pack || {};
    return {
      node_id: nodeId,
      display_name: node.display_name || (routeNodeFor(nodeId) || {}).display_name || "危机节点",
      summary: node.summary || "前线节点需要临时处理。",
      threat: {
        enemy_traits: "影潮压力正在升高。",
        approach_direction: "由暗区边缘向节点逼近。",
      },
      protection_targets: [
        {
          display_name: node.display_name || "节点核心",
          summary: node.summary || "守住节点设施，避免防线被撕开。",
        },
      ],
      available_materials: pack.materials || [],
      facility_state: { summary: "现场工坊可进行应急试作。" },
      constraints: { sample_delivery: "样品可在战斗中途送达。" },
    };
  }

  const adapters = {
    api: {
      async loadInitialData() {
        await ensureSession();
        const [
          worldCatalog,
          packResponse,
          openingResponse,
          mapVisualManifest,
          mapComponentManifest,
          strategicMapMarkerManifest,
          layeredMapVisualPackage,
        ] = await Promise.all([
          apiGet("/api/world-catalog", 3600),
          apiGet(sessionApiPath("/frontend-mock-pack"), 7000),
          apiGet(sessionApiPath("/opening"), 3600),
          fetchOptionalJson(
            `${state.apiBase}/assets/map_visual_reference/map_visual_reference_manifest.v0.1.json`,
          ),
          fetchOptionalJson(
            `${state.apiBase}/assets/map_components/map_component_media_manifest.v0.1.json`,
          ),
          fetchOptionalJson(
            `${state.apiBase}/assets/strategic_map_markers/strategic_map_marker_media_manifest.v0.1.json`,
          ),
          fetchOptionalJson(
            `${state.apiBase}/assets/layered_maps/${encodeURIComponent(NODE_ID)}/layered_map_visual_package.v0.1.json`,
          ),
        ]);
        Object.assign(state.data, {
          worldCatalog,
          pack: packResponse.pack,
          mediaManifest: packResponse.media_manifest,
          mediaAtlasManifest: packResponse.media_atlas_manifest,
          runtimeKit: packResponse.runtime_art_kit,
          runtimeMediaManifest: packResponse.runtime_art_media_manifest,
          runtimeArtAtlasManifest: packResponse.runtime_art_atlas_manifest,
          activatedRuntimeBundle: packResponse.activated_runtime_bundle || null,
          mapVisualManifest,
          mapComponentManifest,
          strategicMapMarkerManifest,
          layeredMapVisualPackage,
          opening: openingResponse.opening,
          worldConfig:
            ((worldCatalog.worlds || []).find(
              (item) => item.world_id === state.selectedWorldId,
            ) || {}).world_config || DEFAULT_WORLD_CONFIG,
        });
        await Promise.all([loadMap(), loadCampaignRoute()]);
        await loadNodeRuntime(currentNodeId());
      },
      async loadMap() {
        const response = await apiGet(sessionApiPath("/map"), 3600);
        Object.assign(state.data, {
          map: response.map,
          runWorldState: response.run_world_state,
          activatedRuntimeBundle:
            response.activated_runtime_bundle || state.data.activatedRuntimeBundle || null,
          layeredMapVisualPackage:
            response.layered_map_visual_package || state.data.layeredMapVisualPackage || null,
        });
        return state.data.map;
      },
      async loadCampaignRoute() {
        try {
          const response = await apiGet(sessionApiPath("/campaign-router"), 3200);
          state.data.campaignRouter = response.campaign_router || null;
          const nodeId = ((state.data.campaignRouter || {}).current || {}).node_id;
          if (nodeId) {
            state.selectedNodeId = nodeId;
            state.selectedMapNodeId = nodeId;
          }
        } catch {
          state.data.campaignRouter = null;
          state.selectedNodeId = state.selectedNodeId || NODE_ID;
        }
        return state.data.campaignRouter;
      },
      async loadBriefing(nodeId = currentNodeId()) {
        let response;
        try {
          response = await apiGet(sessionApiPath(`/nodes/${nodeId}/briefing`), 3600);
        } catch {
          response = {
            briefing: buildBriefingFallback(nodeId),
            materials: (state.data.pack || {}).materials || [],
            npcs: (state.data.pack || {}).npcs || [],
            suggested_input: "我想做一个能稳住当前节点防线的临时装置。",
          };
        }
        assertNodeBound(nodeId, [
          ["briefing_response", response],
          ["briefing", response.briefing],
        ]);
        Object.assign(state.data, {
          briefing: response.briefing,
          materials: response.materials,
          npcs: response.npcs,
          suggestedInput: response.suggested_input,
          activatedRuntimeBundle:
            response.activated_runtime_bundle || state.data.activatedRuntimeBundle || null,
          loadedBriefingNodeId: nodeId,
        });
        return state.data.briefing;
      },
      async loadBattleConfig(nodeId = currentNodeId()) {
        const response = await apiGet(sessionApiPath(`/battles/${nodeId}/config`), 5000);
        let mapRuntimePackage = response.map_runtime_package || null;
        let mapRenderPlanBundle = response.map_render_plan_bundle || null;
        if (!mapRuntimePackage) {
          try {
            const mapResponse = await apiGet(
              sessionApiPath(`/battles/${nodeId}/map-runtime-package`),
              3600,
            );
            assertNodeBound(nodeId, [["map_runtime_response", mapResponse]]);
            mapRuntimePackage = mapResponse.map_runtime_package;
          } catch {
            mapRuntimePackage = null;
          }
        }
        if (!mapRenderPlanBundle) {
          try {
            const mapPlanResponse = await apiGet(
              sessionApiPath(`/battles/${nodeId}/map-render-plan`),
              3600,
            );
            assertNodeBound(nodeId, [["map_render_plan_response", mapPlanResponse]]);
            mapRenderPlanBundle = mapPlanResponse.map_render_plan_bundle;
          } catch {
            mapRenderPlanBundle = null;
          }
        }
        const layeredMapVisualPackage =
          response.layered_map_visual_package ||
          (await fetchOptionalJson(
            `${state.apiBase}/assets/layered_maps/${encodeURIComponent(nodeId)}/layered_map_visual_package.v0.1.json`,
            null,
          ));
        assertNodeBound(nodeId, [
          ["battle_response", response],
          ["battle_config", response.battle_config],
          ["map_runtime_package", mapRuntimePackage],
          ["map_render_plan_bundle", mapRenderPlanBundle],
          ["layered_map_visual_package", layeredMapVisualPackage],
        ]);
        Object.assign(state.data, {
          battleConfig: response.battle_config,
          mapRuntimePackage,
          mapRenderPlanBundle,
          layeredMapVisualPackage,
          toolbarAssets: response.toolbar_assets,
          sampleDeliveryAsset: response.sample_delivery_asset,
          mediaManifest: response.media_manifest,
          mediaAtlasManifest: response.media_atlas_manifest || state.data.mediaAtlasManifest,
          runtimeKit: response.runtime_art_kit,
          runtimeMediaManifest: response.runtime_art_media_manifest,
          runtimeArtAtlasManifest:
            response.runtime_art_atlas_manifest || state.data.runtimeArtAtlasManifest,
          activatedRuntimeBundle:
            response.activated_runtime_bundle || state.data.activatedRuntimeBundle || null,
          loadedBattleNodeId: nodeId,
        });
        return state.data.battleConfig;
      },
      async loadFeatureRuntime(nodeId = currentNodeId()) {
        const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
        const response = await apiGet(
          sessionApiPath(`/runtime/feature-snapshots${query}`),
          3600,
        );
        state.data.activatedRuntimeBundle =
          response.activated_runtime_bundle || state.data.activatedRuntimeBundle || null;
        return state.data.activatedRuntimeBundle;
      },
      resolveAssetUrl(url) {
        return `${state.apiBase}${url}`;
      },
    },
    static: {
      async loadInitialData() {
        const nodeId = staticNodeId();
        const nodePaths = staticNodePaths();
        const [
          pack,
          runtimeKit,
          mediaManifest,
          mediaAtlasManifest,
          runtimeMediaManifest,
          runtimeArtAtlasManifest,
          activatedRuntimeBundle,
          mapVisualManifest,
          mapComponentManifest,
          strategicMapMarkerManifest,
          layeredMapVisualPackage,
          opening,
          worldConfig,
          runWorldState,
          map,
          briefing,
          battleConfig,
          mapRuntimePackage,
          mapStylePack,
          mapRenderPlan,
          mapSemanticVisualConsistencyReport,
        ] = await Promise.all([
          fetchStaticJson("pack"),
          fetchStaticJson("runtimeKit"),
          fetchStaticJson("mediaManifest"),
          fetchStaticJson("mediaAtlasManifest"),
          fetchStaticJson("runtimeMediaManifest"),
          fetchStaticJson("runtimeArtAtlasManifest"),
          fetchOptionalStaticJson("activatedRuntimeBundle"),
          fetchOptionalStaticJson("mapVisualManifest"),
          fetchOptionalStaticJson("mapComponentManifest"),
          fetchOptionalStaticJson("strategicMapMarkerManifest"),
          fetchOptionalStaticJson("layeredMapVisualPackage"),
          fetchStaticJson("opening"),
          fetchOptionalStaticJson("worldConfig", DEFAULT_WORLD_CONFIG),
          fetchJsonImpl(staticCampaignStatePath(), {}, 3600),
          fetchStaticJson("map"),
          fetchStaticJson("briefing"),
          fetchStaticJson("battleConfig"),
          fetchOptionalStaticJson("mapRuntimePackage"),
          fetchOptionalStaticJson("mapStylePack"),
          fetchOptionalStaticJson("mapRenderPlan"),
          fetchOptionalStaticJson("mapSemanticVisualConsistencyReport"),
        ]);
        const mapRenderPlanBundle =
          mapRenderPlan && mapStylePack && mapSemanticVisualConsistencyReport
            ? {
                node_id: nodeId,
                refs: {
                  map_style_pack: STATIC_PATHS.mapStylePack,
                  procedural_map_render_plan:
                    nodePaths.mapRenderPlan || STATIC_PATHS.mapRenderPlan,
                  semantic_visual_consistency_report:
                    nodePaths.mapSemanticVisualConsistencyReport ||
                    STATIC_PATHS.mapSemanticVisualConsistencyReport,
                },
                map_style_pack: mapStylePack,
                procedural_map_render_plan: mapRenderPlan,
                semantic_visual_consistency_report: mapSemanticVisualConsistencyReport,
              }
            : null;
        state.data = {
          worldCatalog: {
            schema_version: "world_catalog.v0.1",
            default_world_id: "long_night_lanterns",
            worlds: [
              {
                world_id: "long_night_lanterns",
                display_name: worldConfig.worldbook_display_name || "长夜灯火",
                tagline: "长夜未尽，第一处危机已经点亮。",
                visual_style_name: worldConfig.visual_style_display_name,
                status: "ready",
                source: "reviewed_mvp_template",
                entry_node_id: NODE_ID,
                preview_url: "/assets/layered_maps/gray_lantern_station/composited/gray_lantern_station.layered_map.svg",
                theme_tags: ["东方古风", "暗夜", "灯火", "驿站"],
                world_config: worldConfig,
              },
            ],
          },
          pack,
          runtimeKit,
          mediaManifest,
          mediaAtlasManifest,
          runtimeMediaManifest,
          runtimeArtAtlasManifest,
          activatedRuntimeBundle,
          mapVisualManifest,
          mapComponentManifest,
          strategicMapMarkerManifest,
          layeredMapVisualPackage,
          opening,
          worldConfig,
          runWorldState,
          map,
          briefing,
          battleConfig,
          mapRuntimePackage,
          mapRenderPlanBundle,
        };
        await this.loadCampaignRoute();
      },
      async loadMap() {
        return state.data.map;
      },
      async loadCampaignRoute() {
        const nodeId = staticNodeId();
        const nodePaths = staticNodePaths();
        const displayName =
          (state.data.battleConfig || {}).display_name || nodePaths.displayName || "灰灯驿站";
        const requestedIndex = staticCampaignStepIndexForNode(requestedStaticNodeId());
        const currentIndex =
          flowVisualSmokeMode() && requestedStaticNodeId() && requestedIndex >= 0
            ? requestedIndex
            : staticCampaignStageIndex();
        const currentStep = STATIC_CAMPAIGN_STEPS[currentIndex] || null;
        const complete = !flowVisualSmokeMode() && staticCampaignComplete();
        const route = STATIC_CAMPAIGN_STEPS.map((step, index) => {
          const paths = staticNodePathsFor(step.node_id);
          return {
            ...step,
            playable: index === currentIndex && !complete,
            asset_handle: {
              status: "ready",
              map_runtime_package_ref: paths.mapRuntimePackage,
              battle_config_ref: paths.battleConfig,
              layered_map_visual_package_ref: paths.layeredMapVisualPackage,
            },
          };
        });
        const current = currentStep
          ? { ...route[currentIndex], display_name: displayName || currentStep.display_name }
          : null;
        state.data.campaignRouter = {
          schema_version: "campaign_router.v0.1",
          router_mode: "static_mvp_three_battle_route",
          current,
          next: route[currentIndex + 1] || null,
          lookahead: route.slice(currentIndex + 1, currentIndex + 3),
          route,
          run_progress: {
            stage_index: currentIndex,
            complete,
            phase: ((state.data.runWorldState || {}).progress || {}).phase || null,
          },
        };
        state.selectedNodeId = current ? current.node_id : nodeId;
        state.selectedMapNodeId = current ? current.node_id : state.selectedMapNodeId || NODE_ID;
        return state.data.campaignRouter;
      },
      async loadBriefing(nodeId = currentNodeId()) {
        const nodePaths = staticNodePathsFor(nodeId);
        const briefing = nodePaths.briefing
          ? await fetchJsonImpl(nodePaths.briefing, {}, 3600)
          : buildBriefingFallback(nodeId);
        Object.assign(state.data, {
          briefing,
          materials: briefing.available_materials || (state.data.pack || {}).materials || [],
          suggestedInput:
            nodePaths.suggestedInput || "我想做一个能稳住当前节点防线的临时装置。",
          loadedBriefingNodeId: nodeId,
        });
        return state.data.briefing;
      },
      async loadBattleConfig(nodeId = currentNodeId()) {
        const nodePaths = staticNodePathsFor(nodeId);
        const [
          battleConfig,
          mapRuntimePackage,
          mapStylePack,
          mapRenderPlan,
          mapSemanticVisualConsistencyReport,
          layeredMapVisualPackage,
        ] = await Promise.all([
          fetchJsonImpl(nodePaths.battleConfig || STATIC_PATHS.battleConfig, {}, 3600),
          fetchOptionalJson(nodePaths.mapRuntimePackage || STATIC_PATHS.mapRuntimePackage),
          fetchOptionalJson(nodePaths.mapStylePack || STATIC_PATHS.mapStylePack),
          fetchOptionalJson(nodePaths.mapRenderPlan || STATIC_PATHS.mapRenderPlan),
          fetchOptionalJson(
            nodePaths.mapSemanticVisualConsistencyReport ||
              STATIC_PATHS.mapSemanticVisualConsistencyReport,
          ),
          fetchOptionalJson(nodePaths.layeredMapVisualPackage || ""),
        ]);
        const mapRenderPlanBundle =
          mapRenderPlan && mapStylePack && mapSemanticVisualConsistencyReport
            ? {
                node_id: nodeId,
                refs: {
                  map_style_pack: nodePaths.mapStylePack || STATIC_PATHS.mapStylePack,
                  procedural_map_render_plan:
                    nodePaths.mapRenderPlan || STATIC_PATHS.mapRenderPlan,
                  semantic_visual_consistency_report:
                    nodePaths.mapSemanticVisualConsistencyReport ||
                    STATIC_PATHS.mapSemanticVisualConsistencyReport,
                },
                map_style_pack: mapStylePack,
                procedural_map_render_plan: mapRenderPlan,
                semantic_visual_consistency_report: mapSemanticVisualConsistencyReport,
              }
            : null;
        assertNodeBound(nodeId, [
          ["battle_config", battleConfig],
          ["map_runtime_package", mapRuntimePackage],
          ["map_render_plan_bundle", mapRenderPlanBundle],
          ["layered_map_visual_package", layeredMapVisualPackage],
        ]);
        Object.assign(state.data, {
          battleConfig,
          mapRuntimePackage,
          mapRenderPlanBundle,
          layeredMapVisualPackage,
          loadedBattleNodeId: nodeId,
        });
        return state.data.battleConfig;
      },
      async loadFeatureRuntime() {
        return state.data.activatedRuntimeBundle || null;
      },
      resolveAssetUrl(url) {
        return resolveStaticAssetUrlImpl(url);
      },
    },
  };

  function dataAdapter() {
    return adapters[state.dataMode] || adapters.static;
  }

  function loadData() {
    return dataAdapter().loadInitialData();
  }

  function loadMap() {
    return dataAdapter().loadMap();
  }

  async function loadRunWorldState(path) {
    state.data.runWorldState = await fetchJsonImpl(path, {}, 3600);
    return state.data.runWorldState;
  }

  async function advanceStaticCampaignProgress(nodeId) {
    const index = staticCampaignStepIndexForNode(nodeId);
    if (index < 0) return null;
    const nextIndex = Math.min(index + 1, STATIC_CAMPAIGN_STEPS.length);
    const currentStep = STATIC_CAMPAIGN_STEPS[index] || null;
    const nextStatePath =
      (currentStep && currentStep.next_state) ||
      STATIC_CAMPAIGN_STATE_PATHS[nextIndex] ||
      STATIC_CAMPAIGN_STATE_PATHS[STATIC_CAMPAIGN_STATE_PATHS.length - 1];
    try {
      await loadRunWorldState(nextStatePath);
    } catch {
      // Route progress remains valid when the optional lookahead state is unavailable.
    }
    saveProfile({
      staticCampaignStageIndex: nextIndex,
      completedBattle: nextIndex >= STATIC_CAMPAIGN_STEPS.length,
    });
    await loadCampaignRoute();
    const nextStep = STATIC_CAMPAIGN_STEPS[nextIndex] || null;
    state.selectedMapNodeId = nextStep ? nextStep.node_id : nodeId;
    return {
      index,
      nextIndex,
      nextStep,
      interlude: currentStep ? currentStep.interlude : "",
    };
  }

  function loadBriefing(nodeId) {
    return dataAdapter().loadBriefing(nodeId);
  }

  function loadBattleConfig(nodeId) {
    return dataAdapter().loadBattleConfig(nodeId);
  }

  async function loadNodeRuntime(nodeId = currentNodeId()) {
    const expectedNodeId = nodeId || currentNodeId();
    const previousData = { ...state.data };
    const results = await Promise.allSettled([
      dataAdapter().loadBriefing(expectedNodeId),
      dataAdapter().loadBattleConfig(expectedNodeId),
    ]);
    const failed = results.find((result) => result.status === "rejected");
    const routeChanged = currentNodeId() !== expectedNodeId;
    if (failed || routeChanged) {
      for (const key of Object.keys(state.data)) delete state.data[key];
      Object.assign(state.data, previousData);
      if (failed) throw failed.reason;
      throw new Error(`节点在装载期间发生变化：${expectedNodeId}`);
    }
    if (
      state.data.loadedBriefingNodeId !== expectedNodeId ||
      state.data.loadedBattleNodeId !== expectedNodeId
    ) {
      for (const key of Object.keys(state.data)) delete state.data[key];
      Object.assign(state.data, previousData);
      throw new Error(`节点运行数据未完整装载：${expectedNodeId}`);
    }
    state.data.loadedNodeId = expectedNodeId;
    return {
      nodeId: expectedNodeId,
      briefing: state.data.briefing,
      battleConfig: state.data.battleConfig,
      mapRuntimePackage: state.data.mapRuntimePackage,
      mapRenderPlanBundle: state.data.mapRenderPlanBundle,
      layeredMapVisualPackage: state.data.layeredMapVisualPackage,
    };
  }

  function loadCampaignRoute() {
    return dataAdapter().loadCampaignRoute();
  }

  function loadFeatureRuntime(nodeId) {
    return dataAdapter().loadFeatureRuntime(nodeId);
  }

  function resolveAssetUrl(url) {
    return dataAdapter().resolveAssetUrl(url);
  }

  return {
    advanceStaticCampaignProgress,
    apiCandidates,
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
    forceStaticDataMode,
    isApiMode,
    isCurrentNode,
    loadBattleConfig,
    loadBriefing,
    loadCampaignRoute,
    loadData,
    loadFeatureRuntime,
    loadMap,
    loadNodeRuntime,
    nodePlayable,
    requestedStaticNodeId,
    resolveAssetUrl,
    routeCurrent,
    routeData,
    routeNext,
    routeNodeFor,
    sessionApiPath,
    staticCampaignComplete,
    staticCampaignCurrentStep,
    staticCampaignStageIndex,
    staticCampaignStatePath,
    staticCampaignStepForNode,
    staticCampaignStepIndexForNode,
    staticNodeId,
    staticNodePathsFor,
  };
}
