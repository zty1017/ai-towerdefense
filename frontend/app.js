(() => {
  "use strict";

  const ROOT = document.getElementById("app");
  const NODE_ID = "gray_lantern_station";
  const STORE_KEY = "ai_compiled_td_frontend_profile_v1";

  const STATIC_PATHS = {
    pack: "/examples/frontend_mock/frontend_mock_pack.v0.1.json",
    runtimeKit: "/examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json",
    mediaManifest: "/game_data/media/frontend_mock/frontend_media_manifest.v0.1.json",
    mediaAtlasManifest: "/game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json",
    runtimeMediaManifest:
      "/game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
    runtimeArtAtlasManifest:
      "/game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
    mapVisualManifest:
      "/game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json",
    opening: "/content/worldbooks/long_night_lanterns/opening.json",
    worldConfig: "/content/worldbooks/long_night_lanterns/world_instance_config.json",
    map: "/game_data/demo/initial_map.json",
    briefing: "/game_data/demo/first_crisis_node.json",
    battleConfig: "/game_data/demo/first_battle_config.json",
    mapRuntimePackage:
      "/examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json",
  };

  const STATIC_ASSET_PREFIXES = [
    [
      /^\/assets\/frontend_runtime_mock\/processed\//,
      "/game_data/media/frontend_runtime_mock/processed/",
    ],
    [
      /^\/assets\/frontend_runtime_mock\/generated\//,
      "/game_data/media/frontend_runtime_mock/generated/",
    ],
    [
      /^\/assets\/frontend_runtime_mock\/atlas_frames\//,
      "/game_data/media/frontend_runtime_mock/atlas_frames/",
    ],
    [
      /^\/assets\/frontend_runtime_mock\/atlas_sheets\//,
      "/game_data/media/frontend_runtime_mock/atlas_sheets/",
    ],
    [/^\/assets\/frontend_mock\/processed\//, "/game_data/media/frontend_mock/processed/"],
    [/^\/assets\/frontend_mock\/generated\//, "/game_data/media/frontend_mock/generated/"],
    [/^\/assets\/frontend_mock\/atlas_frames\//, "/game_data/media/frontend_mock/atlas_frames/"],
    [/^\/assets\/frontend_mock\/atlas_sheets\//, "/game_data/media/frontend_mock/atlas_sheets/"],
    [/^\/assets\/map_visual_reference\//, "/game_data/media/map_visual_reference/"],
  ];

  const DEFAULT_WORLD_CONFIG = {
    worldbook_template_id: "long_night_lanterns",
    worldbook_display_name: "长夜灯火",
    visual_style_id: "lantern_wasteland_pseudo3d",
    visual_style_display_name: "灯塬遗景·伪三维",
    creativity_mode: {
      selected: "stable",
      options: [
        {
          id: "stable",
          display_name: "稳健",
          summary: "倾向使用已验证的灯塬工艺，方案更稳定但变化较少。",
        },
        {
          id: "experimental",
          display_name: "实验性",
          summary: "允许尝试非常规改写与稀疏配比，可能产出意外样品。",
        },
      ],
    },
    player_origin: {
      selected: "lampwright_apprentice",
      options: [
        {
          id: "lampwright_apprentice",
          display_name: "守灯技师",
          summary: "熟悉灯塔结构与灯火工艺，善于在余灯中枢附近进行临时改造。",
        },
        {
          id: "flow_engineer",
          display_name: "流亡工程师",
          summary: "曾维护远方补给线，对导线与输送装置更有心得。",
        },
        {
          id: "signal_dispatcher",
          display_name: "见习调度员",
          summary: "负责观测影潮边缘与驿站信标，擅长判断敌潮动向。",
        },
      ],
    },
    recommended_defaults: {
      creativity_mode: "stable",
      player_origin: "lampwright_apprentice",
      visual_style_id: "lantern_wasteland_pseudo3d",
    },
  };

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
      visual_style_id: "lantern_wasteland_pseudo3d",
    },
    data: {},
    campaignPrefetch: null,
    profile: {},
    openingIndex: 0,
    intentText: "我想做一个能拖慢影潮的临时装置。",
    research: {
      status: "idle",
      proposal: null,
      job: null,
      jobPromise: null,
    },
    battle: null,
    battleOutcome: null,
    settlement: null,
    evidence: null,
    images: new Map(),
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

  async function fetchJson(url, options = {}, timeoutMs = 2400) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...(options.headers || {}),
        },
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } finally {
      window.clearTimeout(timer);
    }
  }

  function unwrapPayload(response) {
    return response && response.payload ? response.payload : response;
  }

  function apiUrl(path) {
    return `${state.apiBase}${path}`;
  }

  async function apiGet(path, timeoutMs = 3600) {
    return unwrapPayload(await fetchJson(apiUrl(path), {}, timeoutMs));
  }

  async function apiPost(path, body = {}, timeoutMs = 9000) {
    return unwrapPayload(
      await fetchJson(
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
      return await fetchJson(url, {}, timeoutMs);
    } catch {
      return fallback;
    }
  }

  function fetchStaticJson(key, timeoutMs = 3600) {
    return fetchJson(STATIC_PATHS[key], {}, timeoutMs);
  }

  function fetchOptionalStaticJson(key, fallback = null, timeoutMs = 3600) {
    return fetchOptionalJson(STATIC_PATHS[key], fallback, timeoutMs);
  }

  function queryFlag(name) {
    const params = new URLSearchParams(window.location.search);
    if (!params.has(name)) return false;
    const value = String(params.get(name) || "1").toLowerCase();
    return !["0", "false", "no", "off"].includes(value);
  }

  function forceStaticDataMode() {
    return queryFlag("static") || queryFlag("staticMode");
  }

  function battleVisualSmokeMode() {
    return queryFlag("battleVisualSmoke");
  }

  function apiCandidates() {
    if (forceStaticDataMode()) return [];
    const params = new URLSearchParams(window.location.search);
    const explicit = params.get("apiBase") || params.get("api");
    const candidates = [];
    if (explicit) candidates.push(explicit);
    if (window.location.protocol.startsWith("http")) candidates.push(window.location.origin);
    if (["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      candidates.push("http://127.0.0.1:8000");
      candidates.push("http://localhost:8000");
    }
    return [...new Set(candidates.map((item) => item.replace(/\/+$/, "")))];
  }

  async function detectApiBase() {
    for (const candidate of apiCandidates()) {
      try {
        const health = await fetchJson(`${candidate}/api/health`, {}, 1200);
        if (health && health.status === "ok") return candidate;
      } catch {
        // Try the next candidate, then fall back to static JSON.
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
    const response = await fetchJson(
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

  const DATA_ADAPTERS = {
    api: {
      async loadInitialData() {
        await ensureSession();
        const [packResponse, openingResponse, mapVisualManifest] = await Promise.all([
          apiGet(sessionApiPath("/frontend-mock-pack"), 7000),
          apiGet(sessionApiPath("/opening"), 3600),
          fetchOptionalJson(
            `${state.apiBase}/assets/map_visual_reference/map_visual_reference_manifest.v0.1.json`,
            null,
            3600,
          ),
        ]);
        Object.assign(state.data, {
          pack: packResponse.pack,
          mediaManifest: packResponse.media_manifest,
          mediaAtlasManifest: packResponse.media_atlas_manifest,
          runtimeKit: packResponse.runtime_art_kit,
          runtimeMediaManifest: packResponse.runtime_art_media_manifest,
          runtimeArtAtlasManifest: packResponse.runtime_art_atlas_manifest,
          mapVisualManifest,
          opening: openingResponse.opening,
          worldConfig: DEFAULT_WORLD_CONFIG,
        });
        await Promise.all([loadMap(), loadCampaignRoute()]);
        await Promise.all([loadBriefing(), loadBattleConfig()]);
      },
      async loadMap() {
        const response = await apiGet(sessionApiPath("/map"), 3600);
        Object.assign(state.data, {
          map: response.map,
          runWorldState: response.run_world_state,
        });
        return state.data.map;
      },
      async loadCampaignRoute() {
        try {
          const response = await apiGet(sessionApiPath("/campaign-router"), 3200);
          state.data.campaignRouter = response.campaign_router || null;
          const nodeId = (state.data.campaignRouter && state.data.campaignRouter.current || {}).node_id;
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
      async loadBriefing() {
        const nodeId = currentNodeId();
        let response = null;
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
        Object.assign(state.data, {
          briefing: response.briefing,
          materials: response.materials,
          npcs: response.npcs,
          suggestedInput: response.suggested_input,
        });
        return state.data.briefing;
      },
      async loadBattleConfig() {
        const nodeId = currentNodeId();
        const response = await apiGet(sessionApiPath(`/battles/${nodeId}/config`), 5000);
        Object.assign(state.data, {
          battleConfig: response.battle_config,
          mapRuntimePackage: response.map_runtime_package || null,
          toolbarAssets: response.toolbar_assets,
          sampleDeliveryAsset: response.sample_delivery_asset,
          mediaManifest: response.media_manifest,
          mediaAtlasManifest: response.media_atlas_manifest || state.data.mediaAtlasManifest,
          runtimeKit: response.runtime_art_kit,
          runtimeMediaManifest: response.runtime_art_media_manifest,
          runtimeArtAtlasManifest:
            response.runtime_art_atlas_manifest || state.data.runtimeArtAtlasManifest,
        });
        if (!state.data.mapRuntimePackage) {
          try {
            const mapResponse = await apiGet(
              sessionApiPath(`/battles/${nodeId}/map-runtime-package`),
              3600,
            );
            state.data.mapRuntimePackage = mapResponse.map_runtime_package;
          } catch {
            state.data.mapRuntimePackage = null;
          }
        }
        return state.data.battleConfig;
      },
      resolveAssetUrl(url) {
        return `${state.apiBase}${url}`;
      },
    },
    static: {
      async loadInitialData() {
        const [
          pack,
          runtimeKit,
          mediaManifest,
          mediaAtlasManifest,
          runtimeMediaManifest,
          runtimeArtAtlasManifest,
          mapVisualManifest,
          opening,
          worldConfig,
          map,
          briefing,
          battleConfig,
          mapRuntimePackage,
        ] = await Promise.all([
          fetchStaticJson("pack"),
          fetchStaticJson("runtimeKit"),
          fetchStaticJson("mediaManifest"),
          fetchStaticJson("mediaAtlasManifest"),
          fetchStaticJson("runtimeMediaManifest"),
          fetchStaticJson("runtimeArtAtlasManifest"),
          fetchOptionalStaticJson("mapVisualManifest"),
          fetchStaticJson("opening"),
          fetchOptionalStaticJson("worldConfig", DEFAULT_WORLD_CONFIG),
          fetchStaticJson("map"),
          fetchStaticJson("briefing"),
          fetchStaticJson("battleConfig"),
          fetchOptionalStaticJson("mapRuntimePackage"),
        ]);
        state.data = {
          pack,
          runtimeKit,
          mediaManifest,
          mediaAtlasManifest,
          runtimeMediaManifest,
          runtimeArtAtlasManifest,
          mapVisualManifest,
          opening,
          worldConfig,
          map,
          briefing,
          battleConfig,
          mapRuntimePackage,
        };
        await this.loadCampaignRoute();
      },
      async loadMap() {
        return state.data.map;
      },
      async loadCampaignRoute() {
        state.data.campaignRouter = {
          schema_version: "campaign_router.v0.1",
          router_mode: "static_fallback_route",
          current: {
            node_id: NODE_ID,
            display_name: "灰灯驿站",
            playable: true,
            asset_handle: {
              status: "ready",
              map_runtime_package_ref: STATIC_PATHS.mapRuntimePackage,
              battle_config_ref: STATIC_PATHS.battleConfig,
            },
          },
          next: null,
          lookahead: [],
          route: [],
        };
        state.selectedNodeId = NODE_ID;
        state.selectedMapNodeId = NODE_ID;
        return state.data.campaignRouter;
      },
      async loadBriefing() {
        return state.data.briefing;
      },
      async loadBattleConfig() {
        return state.data.battleConfig;
      },
      resolveAssetUrl(url) {
        return resolveStaticAssetUrl(url);
      },
    },
  };

  function dataAdapter() {
    return DATA_ADAPTERS[state.dataMode] || DATA_ADAPTERS.static;
  }

  async function loadData() {
    return dataAdapter().loadInitialData();
  }

  async function loadMap() {
    return dataAdapter().loadMap();
  }

  async function loadBriefing() {
    return dataAdapter().loadBriefing();
  }

  async function loadBattleConfig() {
    return dataAdapter().loadBattleConfig();
  }

  async function loadCampaignRoute() {
    return dataAdapter().loadCampaignRoute();
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
      (battleConfig() || {}).display_name ||
      "灰灯驿站"
    );
  }

  function routeNodeFor(nodeId) {
    const route = routeData();
    const nodes = route && Array.isArray(route.route) ? route.route : [];
    return nodes.find((node) => node.node_id === nodeId) || null;
  }

  function nodePlayable(nodeId) {
    const routeNode = routeNodeFor(nodeId);
    if (!routeNode) return nodeId === NODE_ID;
    return routeNode.playable === true;
  }

  function isCurrentNode(nodeId) {
    return nodeId === currentNodeId();
  }

  function buildBriefingFallback(nodeId) {
    const nodes = mapData().nodes || [];
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
      if (battleVisualSmokeMode()) {
        saveProfile({ worldCreated: true, completedBattle: false });
        state.battle = null;
        state.view = "battle";
        render();
        return;
      }
      state.view = "profile";
      render();
    } catch (error) {
      if (isApiMode()) {
        try {
          state.dataMode = "static";
          state.apiBase = "";
          await loadData();
          saveProfile();
          state.view = "profile";
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
    return state.data.battleConfig || {};
  }

  function mapRuntimePackage() {
    return state.data.mapRuntimePackage || {};
  }

  function mapGrid() {
    return mapRuntimePackage().grid || battleConfig().grid || { width_cells: 16, height_cells: 9 };
  }

  function mapObjectives() {
    const fromPackage = mapRuntimePackage().objectives || {};
    const config = battleConfig();
    if (fromPackage.core_target) return fromPackage;
    return {
      core_target: normalizeTarget(config.core_target, "target_node_core"),
      optional_targets: (config.optional_targets || []).map((target, index) =>
        normalizeTarget(target, `optional_target_${index + 1}`),
      ),
    };
  }

  function normalizeTarget(target, fallbackId) {
    const data = target || {};
    return {
      target_id: data.target_id || data.stable_internal_id || fallbackId,
      display_name: data.display_name || "防守目标",
      position: data.position || { x: 0, y: 0 },
      durability: data.durability || 1,
    };
  }

  function manifestItems(manifest) {
    return Array.isArray(manifest && manifest.items) ? manifest.items : [];
  }

  function resolveStaticAssetUrl(url) {
    return STATIC_ASSET_PREFIXES.reduce(
      (resolved, [pattern, replacement]) => resolved.replace(pattern, replacement),
      url,
    );
  }

  function assetUrl(url) {
    if (!url) return "";
    if (/^https?:\/\//.test(url)) return url;
    return dataAdapter().resolveAssetUrl(url);
  }

  function mediaItem(assetId, role, runtime = false) {
    const manifest = runtime ? state.data.runtimeMediaManifest : state.data.mediaManifest;
    return manifestItems(manifest).find(
      (item) =>
        (item.asset_id === assetId || item.source_game_id === assetId) &&
        item.media_role === role,
    );
  }

  function mediaUrl(assetId, role, runtime = false) {
    const frameUrl = atlasFrameUrl(assetId, role, runtime);
    if (frameUrl) return frameUrl;
    const item = mediaItem(assetId, role, runtime);
    return item ? assetUrl(item.url) : "";
  }

  function atlasItems(runtime = false) {
    const manifest = runtime ? state.data.runtimeArtAtlasManifest : state.data.mediaAtlasManifest;
    return Array.isArray(manifest && manifest.items) ? manifest.items : [];
  }

  function atlasItem(assetId, role, runtime = false) {
    return atlasItems(runtime).find(
      (entry) =>
        entry &&
        (entry.asset_id === assetId || entry.source_game_id === assetId) &&
        entry.media_role === role &&
        Array.isArray(entry.frames) &&
        entry.frames.length,
    );
  }

  function atlasClockMs() {
    if (state.battle && Number.isFinite(state.battle.elapsedMs)) return state.battle.elapsedMs;
    return typeof performance !== "undefined" ? performance.now() : Date.now();
  }

  function atlasFrameIndex(item) {
    const frames = Array.isArray(item && item.frames) ? item.frames : [];
    if (frames.length <= 1) return 0;
    const playback = item.playback || {};
    const fps = Number(playback.fps) > 0 ? Number(playback.fps) : 6;
    const frameDuration = 1000 / fps;
    const rawIndex = Math.floor(atlasClockMs() / frameDuration);
    if (playback.loop === false) return Math.min(frames.length - 1, rawIndex);
    return rawIndex % frames.length;
  }

  function atlasFrameUrl(assetId, role, runtime = false) {
    const item = atlasItem(assetId, role, runtime);
    const frames = Array.isArray(item && item.frames) ? item.frames : [];
    const frame = frames[atlasFrameIndex(item)];
    return frame && frame.url ? assetUrl(frame.url) : "";
  }

  function atlasFrameRef(assetId, role, runtime = false) {
    const item = atlasItem(assetId, role, runtime);
    const frames = Array.isArray(item && item.frames) ? item.frames : [];
    const frame = frames[atlasFrameIndex(item)];
    if (!frame) return null;
    const sheet = item && item.spritesheet;
    if (sheet && sheet.url) {
      return {
        url: assetUrl(sheet.url),
        source: {
          x: Number(frame.x) || 0,
          y: Number(frame.y) || 0,
          width: Math.max(1, Number(frame.width) || 1),
          height: Math.max(1, Number(frame.height) || 1),
        },
      };
    }
    if (frame.url) return { url: assetUrl(frame.url), source: null };
    return null;
  }

  function atlasFrameUrls(assetId, role, runtime = false) {
    const item = atlasItem(assetId, role, runtime);
    const frames = Array.isArray(item && item.frames) ? item.frames : [];
    const urls = [];
    const sheet = item && item.spritesheet;
    if (sheet && sheet.url) urls.push(assetUrl(sheet.url));
    for (const frame of frames) {
      if (frame && frame.url) urls.push(assetUrl(frame.url));
    }
    return [...new Set(urls.filter(Boolean))];
  }

  function mediaSpriteRef(assetId, role, runtime = false) {
    const frameRef = atlasFrameRef(assetId, role, runtime);
    if (frameRef) return frameRef;
    const url = mediaUrl(assetId, role, runtime);
    return url ? { url, source: null } : null;
  }

  function mediaPreloadUrls(assetId, role, runtime = false) {
    const urls = atlasFrameUrls(assetId, role, runtime);
    if (urls.length) return urls;
    const url = mediaUrl(assetId, role, runtime);
    return url ? [url] : [];
  }

  function playerReadyMapLayer(entry) {
    if (!entry) return false;
    return (
      entry.authority === "published_visual_layer" &&
      entry.player_visible_quality === "passed"
    );
  }

  function mapVisualUrl(role, options = {}) {
    const playerOnly = Boolean(options.playerOnly);
    const packageLayer = (mapRuntimePackage().visual_layers || []).find(
      (entry) => entry.role === role && (!playerOnly || playerReadyMapLayer(entry)),
    );
    if (packageLayer && packageLayer.url) return assetUrl(packageLayer.url);
    const item = manifestItems(state.data.mapVisualManifest).find(
      (entry) => entry.role === role && (!playerOnly || playerReadyMapLayer(entry)),
    );
    return item ? assetUrl(item.url) : "";
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
    const resolved = assetUrl(url);
    if (!resolved) return null;
    if (state.images.has(resolved)) return state.images.get(resolved);
    const img = new Image();
    img.decoding = "async";
    img.src = resolved;
    state.images.set(resolved, img);
    return img;
  }

  function render() {
    stopBattleLoop();
    switch (state.view) {
      case "profile":
        renderProfile();
        break;
      case "world-config":
        renderWorldConfig();
        break;
      case "opening":
        renderOpening();
        break;
      case "map":
        renderMap();
        break;
      case "workshop":
        renderWorkshop();
        break;
      case "battle":
        renderBattle();
        break;
      case "settlement":
        renderSettlement();
        break;
      default:
        renderProfile();
    }
  }

  function renderProfile() {
    const hasSession = Boolean(state.sessionId || state.profile.sessionId);
    ROOT.innerHTML = `
      <main class="screen">
        <section class="hero-layout">
          <div>
            <div class="eyebrow">本地档案</div>
            <h1 class="screen-title">余灯中枢</h1>
            <p class="screen-subtitle">
              长夜未尽，灰灯驿站发来急报。档案只保存在本机，进入后会为本次体验建立独立进度。
            </p>
            <div class="profile-menu" style="margin-top:24px">
              <button class="menu-button primary-button" data-action="continue">
                <span><strong>${hasSession ? "继续当前体验" : "开始新档案"}</strong><span>从开局配置进入第一场危机</span></span>
                <b>›</b>
              </button>
              <button class="menu-button" data-action="new-archive">
                <span><strong>开始新档案</strong><span>清空本机演示进度</span></span>
                <b>↻</b>
              </button>
              <button class="menu-button ghost-button" data-action="reset-demo">
                <span><strong>重置演示</strong><span>保留入口，重新生成本次进度</span></span>
                <b>⌁</b>
              </button>
              <button class="menu-button ghost-button" data-action="settings">
                <span><strong>设置</strong><span>${state.dataMode === "api" ? "中枢档案已连通" : "使用本机档案"}</span></span>
                <b>⚙</b>
              </button>
            </div>
          </div>
          <div class="profile-visual" aria-label="余灯中枢远景"></div>
        </section>
      </main>
    `;
  }

  function renderWorldConfig() {
    const config = worldConfig();
    const creativity = config.creativity_mode || DEFAULT_WORLD_CONFIG.creativity_mode;
    const origin = config.player_origin || DEFAULT_WORLD_CONFIG.player_origin;
    ROOT.innerHTML = `
      <main class="screen">
        ${screenHeader("建立本局档案", "选择本局世界书、画风、创造性与开局身份。", "开局建档")}
        <section class="config-grid">
          <aside class="panel">
            <h2 class="panel-title">世界书</h2>
            <p class="panel-text">${safeText(config.worldbook_display_name || "长夜灯火")}</p>
            <div class="tag-row">
              <span class="tag">灯火</span>
              <span class="tag">影潮</span>
              <span class="tag">前哨</span>
            </div>
            <p class="panel-text">长夜没有结束，余灯中枢仍在燃烧。第一处危机已经点亮。</p>
          </aside>
          <div class="world-preview" aria-label="画风预览">
            <span class="signal"></span>
            <span class="signal"></span>
            <div class="horizon"></div>
            <div style="position:absolute;left:18px;bottom:18px;right:18px">
              <div class="eyebrow">画风</div>
              <h2 class="panel-title">${safeText(config.visual_style_display_name || "灯塬遗景·伪三维")}</h2>
              <p class="panel-text">斜视角战场、暗色地形、暖金灯火与冷色迟滞场。</p>
            </div>
          </div>
          <aside class="panel">
            <h2 class="panel-title">创造性</h2>
            <div class="option-stack">
              ${(creativity.options || [])
                .map(
                  (option) => `
                    <button class="option-button ${state.selectedOptions.creativity_mode === option.id ? "is-selected" : ""}" data-action="select-creativity" data-value="${safeText(option.id)}">
                      <strong>${safeText(option.display_name)}</strong>
                      <span>${safeText(option.summary)}</span>
                    </button>
                  `,
                )
                .join("")}
            </div>
            <h2 class="panel-title" style="margin-top:18px">开局身份</h2>
            <div class="option-stack">
              ${(origin.options || [])
                .map(
                  (option) => `
                    <button class="option-button ${state.selectedOptions.player_origin === option.id ? "is-selected" : ""}" data-action="select-origin" data-value="${safeText(option.id)}">
                      <strong>${safeText(option.display_name)}</strong>
                      <span>${safeText(option.summary)}</span>
                    </button>
                  `,
                )
                .join("")}
            </div>
            <div class="screen-actions" style="margin-top:18px">
              <button class="primary-button" data-action="begin-world">点亮档案</button>
              <button class="ghost-button" data-action="use-recommended">使用推荐配置</button>
            </div>
          </aside>
        </section>
      </main>
    `;
  }

  function openingSegment() {
    const opening = state.data.opening || {};
    const segments = opening.segments || [];
    return segments[state.openingIndex] || segments[0] || null;
  }

  function renderOpening() {
    const segment = openingSegment();
    if (!segment) {
      state.view = "map";
      render();
      return;
    }
    const lines = Array.isArray(segment.lines) ? segment.lines : [];
    const isBlack = segment.kind === "black_screen_text";
    ROOT.innerHTML = `
      <main class="opening-screen">
        <section class="opening-frame">
          ${
            isBlack
              ? `<div class="opening-lines">${lines.map((line) => `<div>${safeText(line)}</div>`).join("")}</div>`
              : `<div class="opening-card"><p class="opening-narration">${safeText(segment.narration || "")}</p></div>`
          }
          <div class="opening-controls">
            <button class="ghost-button" data-action="opening-skip">跳过</button>
            <button class="primary-button" data-action="opening-next">继续</button>
          </div>
        </section>
      </main>
    `;
  }

  function mapNodeColor(kind, stateName) {
    if (stateName === "secured") return "#8fcf83";
    if (kind === "battle_hotspot") return "#ff756a";
    if (kind === "main_city") return "#f0bd58";
    if (kind === "research_facility") return "#64d2c8";
    if (kind === "resource_storage") return "#9fd48a";
    return "#d8c58a";
  }

  function nodeState(node) {
    const runNodes = (state.data.runWorldState || {}).map_nodes || [];
    const runNode = runNodes.find((item) => item.node_id === node.stable_internal_id);
    if (runNode && runNode.status) return runNode.status;
    if (state.profile.completedBattle && node.stable_internal_id === NODE_ID) return "secured";
    return node.state;
  }

  function selectedMapNode() {
    const nodes = mapData().nodes || [];
    return (
      nodes.find((node) => node.stable_internal_id === state.selectedMapNodeId) ||
      nodes.find((node) => node.stable_internal_id === currentNodeId()) ||
      nodes.find((node) => node.stable_internal_id === NODE_ID) ||
      nodes[0]
    );
  }

  function renderMap() {
    const map = mapData();
    const nodes = map.nodes || [];
    const selected = selectedMapNode();
    const byId = new Map(nodes.map((node) => [node.stable_internal_id, node]));
    const lines = (map.supply_lines || [])
      .map((line) => {
        const from = byId.get(line.from_node_id);
        const to = byId.get(line.to_node_id);
        if (!from || !to) return "";
        return `<line x1="${from.position.x}" y1="${from.position.y}" x2="${to.position.x}" y2="${to.position.y}" stroke="rgba(240,189,88,.48)" stroke-width="8" stroke-linecap="round" stroke-dasharray="12 12" />`;
      })
      .join("");
    const dark = (map.dark_regions || [])
      .map((region) => {
        const points = (region.polygon || []).map((p) => `${p.x},${p.y}`).join(" ");
        return `<polygon points="${points}" fill="rgba(5,7,9,.72)" stroke="rgba(143,124,255,.24)" stroke-width="2" />`;
      })
      .join("");
    const threats = (map.threat_edges || [])
      .map(
        (edge) => `
          <g>
            <circle cx="${edge.position.x}" cy="${edge.position.y}" r="74" fill="none" stroke="rgba(143,124,255,.78)" stroke-width="4" stroke-dasharray="18 10">
              <animate attributeName="r" values="58;88;58" dur="2.2s" repeatCount="indefinite" />
            </circle>
            <path d="M ${edge.position.x - 70} ${edge.position.y + 45} Q ${edge.position.x} ${edge.position.y - 40} ${edge.position.x + 78} ${edge.position.y + 10}" fill="none" stroke="rgba(255,102,102,.7)" stroke-width="5" />
          </g>
        `,
      )
      .join("");
    const terrain = `
      <defs>
        <linearGradient id="mapGround" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#20291f" />
          <stop offset=".52" stop-color="#141917" />
          <stop offset="1" stop-color="#18121b" />
        </linearGradient>
        <radialGradient id="cityGlow" cx="34%" cy="52%" r="30%">
          <stop offset="0" stop-color="rgba(255,218,132,.42)" />
          <stop offset=".42" stop-color="rgba(240,189,88,.12)" />
          <stop offset="1" stop-color="rgba(240,189,88,0)" />
        </radialGradient>
        <pattern id="terrainLines" width="46" height="46" patternUnits="userSpaceOnUse" patternTransform="rotate(-18)">
          <path d="M 0 18 L 46 18" stroke="rgba(255,237,184,.055)" stroke-width="2" />
        </pattern>
      </defs>
      <rect x="0" y="0" width="1280" height="720" fill="url(#mapGround)" />
      <path d="M 20 556 C 218 480 360 534 548 458 S 902 306 1260 370 L 1260 720 L 20 720 Z" fill="rgba(122,108,72,.24)" />
      <path d="M 0 186 C 210 132 352 168 522 126 S 828 60 1280 98 L 1280 0 L 0 0 Z" fill="rgba(52,69,55,.28)" />
      <rect x="0" y="0" width="1280" height="720" fill="url(#terrainLines)" opacity=".82" />
      <ellipse cx="430" cy="390" rx="310" ry="230" fill="url(#cityGlow)" />
    `;
    const nodeMarkup = nodes
      .map((node) => {
        const color = mapNodeColor(node.kind, nodeState(node));
        const radius = node.kind === "main_city" ? 30 : node.kind === "battle_hotspot" ? 24 : 20;
        const pulse =
          node.stable_internal_id === currentNodeId()
            ? `<circle cx="${node.position.x}" cy="${node.position.y}" r="${radius + 12}" fill="none" stroke="${color}" stroke-width="3" opacity=".6"><animate attributeName="r" values="${radius + 8};${radius + 26};${radius + 8}" dur="1.4s" repeatCount="indefinite" /></circle>`
            : "";
        return `
          <g class="map-node" data-action="select-map-node" data-node-id="${safeText(node.stable_internal_id)}">
            ${pulse}
            <circle cx="${node.position.x}" cy="${node.position.y}" r="${radius}" fill="${color}" fill-opacity=".82" stroke="rgba(255,245,220,.82)" stroke-width="3" />
            <text x="${node.position.x + radius + 10}" y="${node.position.y + 7}">${safeText(node.display_name)}</text>
          </g>
        `;
      })
      .join("");
    ROOT.innerHTML = `
      <main class="screen">
        ${screenHeader(map.display_name || "余灯中枢态势图", map.summary || "", "战略态势")}
        <section class="map-layout">
          <aside class="panel">
            <h2 class="panel-title">当前目标</h2>
            <div class="event-list">
              ${(map.floating_events || [])
                .map(
                  (event) => `
                    <div class="event-item">
                      <strong>${safeText(event.display_name)}</strong>
                      <span>${safeText(event.summary)}</span>
                    </div>
                  `,
                )
                .join("")}
            </div>
          </aside>
          <div class="strategic-map" aria-label="${safeText(map.display_name || "态势图")}">
            <svg viewBox="0 0 1280 720" role="img">
              ${terrain}
              ${dark}
              ${lines}
              ${threats}
              ${nodeMarkup}
            </svg>
          </div>
          <aside class="panel">
            <h2 class="panel-title">${safeText(selected ? selected.display_name : "节点")}</h2>
            <p class="panel-text">${safeText(selected ? selected.summary : "")}</p>
            <div class="tag-row">
              <span class="tag">${safeText(selected ? selected.kind : "node")}</span>
              <span class="tag">${safeText(selected ? nodeState(selected) : "")}</span>
            </div>
            <div class="screen-actions">
              <button class="primary-button" data-action="enter-node" ${selected && isCurrentNode(selected.stable_internal_id) && nodePlayable(selected.stable_internal_id) ? "" : "disabled"}>进入当前节点</button>
              <button class="ghost-button" data-action="refresh-map">刷新态势</button>
            </div>
            ${
              routeNext()
                ? `<div class="event-list" style="margin-top:12px">
                    <div class="event-item"><strong>下一处</strong><span>${safeText(routeNext().display_name || "前方节点")}</span></div>
                  </div>`
                : ""
            }
          </aside>
        </section>
      </main>
    `;
  }

  function materialName(id) {
    const names = {
      lamp_shard: "灯芯碎片",
      conductor_filament: "导线丝",
      lamp_oil: "灯油",
      iron_scrap: "铁料",
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
    const sampleId = sample ? sample.stable_internal_id : "asset_mirror_lure_trap_001";
    return mediaUrl(sampleId, "icon", false) || mediaUrl(sampleId, "ui_card", false);
  }

  function currentProposal() {
    const config = battleConfig();
    const sample = config.sample_asset || {};
    return {
      name: sample.display_name || "折光绊索",
      summary: "灯光编织的临时绊线，可让经过的影潮短暂迟滞。",
      effect: sample.effect_summary || "范围内敌人短暂减速。",
      material: "灯芯碎片 x2 / 导线丝 x1",
      constraint: "一次性装置，需要部署在路径转角附近。",
      risk: "稳定性偏低，强雾中效果可能衰减。",
      npc: "守灯人认为它能争取第一波后的喘息。",
    };
  }

  function renderWorkshop() {
    const briefing = briefingData();
    const proposal = currentProposal();
    const materials = briefing.available_materials || state.data.materials || [];
    const targets = briefing.protection_targets || [];
    const threat = briefing.threat || {};
    const npcUrl = npcPortraitUrl("npc_workshop_mentor");
    const sampleUrl = sampleIconUrl();
    const nodeName = currentNodeDisplayName();
    ROOT.innerHTML = `
      <main class="screen">
        ${screenHeader(`${nodeName}应急改造间`, briefing.summary || "影潮正在接近。", "现场试作")}
        <section class="workshop-grid">
          <aside class="panel">
            <h2 class="panel-title">当前危机</h2>
            <div class="brief-list">
              <div class="brief-item"><strong>敌潮</strong><span>${safeText(threat.enemy_traits || "高速、低耐久。")}</span></div>
              <div class="brief-item"><strong>方向</strong><span>${safeText(threat.approach_direction || "东南方向。")}</span></div>
              ${targets
                .map(
                  (target) => `
                    <div class="brief-item">
                      <strong>${safeText(target.display_name)}</strong>
                      <span>${safeText(target.summary)}</span>
                    </div>
                  `,
                )
                .join("")}
            </div>
          </aside>
          <section class="panel">
            <h2 class="panel-title">构想</h2>
            <textarea class="workshop-input" data-field="intent">${safeText(state.intentText)}</textarea>
            <div class="screen-actions" style="margin-top:12px">
              <button class="ghost-button" data-action="proposal-refresh">校准方案</button>
              <button class="primary-button" data-action="confirm-prototype" ${state.research.status === "confirming" ? "disabled" : ""}>确认试作</button>
            </div>
            <article class="proposal-card">
              <div class="proposal-art">${imageTag(sampleUrl, proposal.name)}</div>
              <div class="proposal-body">
                <h3>${safeText(proposal.name)}</h3>
                <p class="panel-text">${safeText(proposal.summary)}</p>
                <div class="tag-row">
                  <span class="tag">减速：中</span>
                  <span class="tag">持续：短</span>
                  <span class="tag">稳定性：偏低</span>
                  <span class="tag">次数：2</span>
                </div>
                <div class="event-list">
                  <div class="event-item"><strong>预期作用</strong><span>${safeText(proposal.effect)}</span></div>
                  <div class="event-item"><strong>建议投入</strong><span>${safeText(proposal.material)}</span></div>
                  <div class="event-item"><strong>已知约束</strong><span>${safeText(proposal.constraint)}</span></div>
                  <div class="event-item"><strong>不确定性</strong><span>${safeText(proposal.risk)}</span></div>
                  <div class="event-item"><strong>NPC 初判</strong><span>${safeText(proposal.npc)}</span></div>
                </div>
              </div>
            </article>
          </section>
          <aside class="panel">
            <div class="side-avatar">${imageTag(npcUrl, "临时工坊老师傅")}</div>
            <h2 class="panel-title">参与者与条件</h2>
            <div class="material-grid">
              ${materials
                .map(
                  (item) => `
                    <div class="meter-row">
                      <span>${safeText(materialName(item.material_id || item.resource_id))}</span>
                      <b>${safeText(item.quantity ?? item.amount ?? 0)}</b>
                    </div>
                  `,
                )
                .join("")}
            </div>
            <div class="event-list" style="margin-top:12px">
              <div class="event-item"><strong>设施</strong><span>${safeText((briefing.facility_state || {}).summary || "临时工坊可用。")}</span></div>
              <div class="event-item"><strong>限制</strong><span>${safeText((briefing.constraints || {}).sample_delivery || "样品在战斗中途送达。")}</span></div>
            </div>
          </aside>
        </section>
      </main>
    `;
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
    saveProfile({ worldCreated: true, completedBattle: false });
    state.openingIndex = 0;
    state.view = "opening";
    render();
  }

  async function startNewArchive() {
    localStorage.removeItem(STORE_KEY);
    state.sessionId = "";
    state.profile = {};
    state.selectedOptions = {
      creativity_mode: "stable",
      player_origin: "lampwright_apprentice",
      visual_style_id: "lantern_wasteland_pseudo3d",
    };
    state.research = { status: "idle", proposal: null, job: null, jobPromise: null };
    state.battle = null;
    state.settlement = null;
    if (isApiMode()) {
      await ensureSession();
    }
    state.view = "world-config";
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
    saveProfile({ worldCreated: false, completedBattle: false });
    state.research = { status: "idle", proposal: null, job: null, jobPromise: null };
    state.battle = null;
    state.settlement = null;
    state.view = "profile";
    render();
  }

  async function refreshProposal() {
    state.research.status = "proposed";
    renderWorkshop();
    await sleep(260);
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
    requestNextPrefetch();
    state.view = "workshop";
    render();
  }

  async function confirmPrototype() {
    state.research.status = "confirming";
    renderWorkshop();
    const intent = state.intentText.trim() || "我想做一个能拖慢影潮的临时装置。";
    if (isApiMode()) {
      try {
        const proposal = await apiPost(
          sessionApiPath("/research/proposals"),
          { intent_text: intent, node_id: currentNodeId() },
          4200,
        );
        state.research.proposal = proposal;
        state.research.jobPromise = apiPost(
          sessionApiPath(
            `/research/proposals/${encodeURIComponent(proposal.proposal_id)}/confirm`,
          ),
          {},
          20000,
        )
          .then((job) => {
            state.research.job = job;
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
    state.view = "battle";
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
            <div id="dialogueLayer"></div>
          </section>
          <aside class="battle-side battle-right" id="battleInfo"></aside>
          <div class="battle-tools" id="battleTools"></div>
        </section>
      </main>
    `;
    setupBattle();
  }

  function setupBattle() {
    const canvas = document.getElementById("battleCanvas");
    const ctx = canvas.getContext("2d");
    state.battle = state.battle || createBattleState();
    Object.assign(state.battle, {
      canvas,
      ctx,
      dom: {
        stats: document.getElementById("battleStats"),
        tasks: document.getElementById("battleTasks"),
        info: document.getElementById("battleInfo"),
        tools: document.getElementById("battleTools"),
        toast: document.getElementById("battleToast"),
        dialogue: document.getElementById("dialogueLayer"),
        pause: document.getElementById("pauseButton"),
        speed: document.getElementById("speedButton"),
      },
      loopActive: true,
      lastFrameAt: 0,
      lastDomAt: -999,
    });
    canvas.addEventListener("click", onBattleCanvasClick);
    canvas.addEventListener("pointermove", onBattleCanvasPointerMove);
    canvas.addEventListener("pointerleave", onBattleCanvasPointerLeave);
    window.addEventListener("resize", resizeBattleCanvas);
    resizeBattleCanvas();
    preloadBattleImages();
    if (!battleVisualSmokeMode()) {
      showDialogue(
        "灰灯驿站守灯人",
        "第一波很快就会撞进来。样品还在封装，先用基础灯栏争取时间。",
        "npc_gray_lantern_keeper_portrait",
      );
    }
    requestAnimationFrame(battleFrame);
  }

  function stopBattleLoop() {
    if (state.battle) {
      state.battle.loopActive = false;
    }
    window.removeEventListener("resize", resizeBattleCanvas);
  }

  function createBattleState() {
    const config = battleConfig();
    const objectives = mapObjectives();
    const sample = config.sample_asset || {};
    return {
      config,
      mapPackage: mapRuntimePackage(),
      elapsedMs: 0,
      speed: 1,
      paused: false,
      enemies: [],
      defenses: [],
      traps: [],
      effects: [],
      resources: 115,
      power: 8,
      coreHp: (objectives.core_target || {}).durability || 10,
      optionalHp: ((objectives.optional_targets || [])[0] || {}).durability || 4,
      leaks: 0,
      kills: 0,
      selectedTool: "basic",
      draggingTool: null,
      dragPointer: null,
      hoverCell: null,
      basicUses: (config.basic_defense || {}).uses_per_battle || 3,
      sampleUses: 0,
      supportUses: 1,
      sampleDelivered: false,
      sampleDeliveryMs: sample.delivery_delay_ms || 30000,
      cooldowns: {
        basic: 0,
        sample: 0,
        support: 0,
      },
      spawned: 0,
      spawnSchedule: buildSpawnSchedule(config),
      finishing: false,
      deployedAssetIds: [],
      selectedObject: null,
      toast: "样品封装中",
      dialogueOpen: false,
      metrics: null,
    };
  }

  function buildSpawnSchedule(config) {
    let t = 0;
    const schedule = [];
    for (const wave of config.waves || []) {
      t += wave.delay_before_wave_ms || 0;
      for (let i = 0; i < wave.count; i += 1) {
        schedule.push({ at: t + i * (wave.spawn_interval_ms || 1000), wave });
      }
      t += (wave.count || 0) * (wave.spawn_interval_ms || 1000);
    }
    return schedule;
  }

  function preloadBattleImages() {
    [
      ...mediaPreloadUrls("enemy_shadow_tide_runner", "unit_sprite", true),
      ...mediaPreloadUrls("enemy_shadow_tide_shade", "unit_sprite", true),
      ...mediaPreloadUrls("enemy_shadow_tide_cluster", "unit_sprite", true),
      ...mediaPreloadUrls("objective_station_core", "objective_sprite", true),
      ...mediaPreloadUrls("objective_signal_beacon", "objective_sprite", true),
      ...mediaPreloadUrls("defense_basic_lantern_barricade", "defense_sprite", true),
      sampleIconUrl(),
      ...debugBattleMapVisualUrls(),
      npcPortraitUrl("npc_gray_lantern_keeper"),
      npcPortraitUrl("npc_workshop_mentor"),
    ].forEach((url) => getImage(url));
  }

  function resizeBattleCanvas() {
    if (!state.battle || !state.battle.canvas) return;
    const canvas = state.battle.canvas;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    const ctx = state.battle.ctx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    state.battle.metrics = computeBattleMetrics(rect.width, rect.height);
  }

  function computeBattleMetrics(width, height) {
    const grid = mapGrid();
    const baseWidth = 1280;
    const baseHeight = 720;
    const scale = Math.max(width / baseWidth, height / baseHeight);
    const imageWidth = baseWidth * scale;
    const imageHeight = baseHeight * scale;
    const imageOffsetX = (width - imageWidth) / 2;
    const imageOffsetY = (height - imageHeight) / 2;
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
    const minX = Math.min(...raw.map((p) => p.x));
    const maxX = Math.max(...raw.map((p) => p.x));
    const minY = Math.min(...raw.map((p) => p.y));
    const maxY = Math.max(...raw.map((p) => p.y));
    return {
      width,
      height,
      grid,
      baseWidth,
      baseHeight,
      imageWidth,
      imageHeight,
      imageOffsetX,
      imageOffsetY,
      scale,
      tileW: baseTileW * scale,
      tileH: baseTileH * scale,
      baseTileW,
      baseTileH,
      baseOffsetX: (baseWidth - (maxX - minX)) / 2 - minX,
      baseOffsetY: (baseHeight - (maxY - minY)) / 2 - minY + 6,
    };
  }

  function rawProject(x, y, tileW, tileH) {
    return {
      x: (x - y) * (tileW / 2),
      y: (x + y) * (tileH / 2),
    };
  }

  function projectCell(x, y) {
    const m = state.battle.metrics;
    const raw = rawProject(x, y, m.baseTileW, m.baseTileH);
    return {
      x: m.imageOffsetX + (raw.x + m.baseOffsetX) * m.scale,
      y: m.imageOffsetY + (raw.y + m.baseOffsetY) * m.scale,
    };
  }

  function screenToCell(sx, sy) {
    const m = state.battle.metrics;
    const designX = (sx - m.imageOffsetX) / m.scale;
    const designY = (sy - m.imageOffsetY) / m.scale;
    const xRaw = designX - m.baseOffsetX;
    const yRaw = designY - m.baseOffsetY;
    const gx = yRaw / m.baseTileH + xRaw / m.baseTileW;
    const gy = yRaw / m.baseTileH - xRaw / m.baseTileW;
    return { x: Math.round(gx), y: Math.round(gy), fx: gx, fy: gy };
  }

  function cellFromCanvasEvent(event) {
    const battle = state.battle;
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
    return isCellInGrid(cell) ? { x: cell.x, y: cell.y } : null;
  }

  function isCellInGrid(cell) {
    const battle = state.battle;
    const grid = mapGrid();
    if (!battle || !cell) return false;
    return (
      cell.x >= 0 &&
      cell.y >= 0 &&
      cell.x < grid.width_cells &&
      cell.y < grid.height_cells
    );
  }

  function pathWaypoints() {
    const routes = mapRuntimePackage().path_routes || [];
    const configPaths = battleConfig().paths || [];
    const firstRoute = routes[0] || configPaths[0] || {};
    return (firstRoute.waypoints || []).map((p) => ({ x: p.x, y: p.y }));
  }

  function allPathRoutes() {
    const routes = mapRuntimePackage().path_routes || [];
    if (routes.length) return routes;
    return (battleConfig().paths || []).map((route) => ({
      route_id: route.stable_internal_id,
      waypoints: route.waypoints || [],
    }));
  }

  function pathCells() {
    const cells = [];
    for (const route of allPathRoutes()) {
      const points = (route.waypoints || []).map((p) => ({ x: p.x, y: p.y }));
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

  function distanceToPath(cell) {
    const cells = pathCells();
    if (!cells.length) return Infinity;
    return Math.min(...cells.map((pathCell) => Math.hypot(pathCell.x - cell.x, pathCell.y - cell.y)));
  }

  function onBattleCanvasClick(event) {
    const battle = state.battle;
    if (!battle || battle.dialogueOpen || battle.finishing) return;
    const cell = cellFromCanvasEvent(event);
    if (cell) deployToolAt(battle.selectedTool, cell);
  }

  function onBattleCanvasPointerMove(event) {
    const battle = state.battle;
    if (!battle || battle.dialogueOpen || battle.finishing) return;
    battle.hoverCell = cellFromCanvasEvent(event);
  }

  function onBattleCanvasPointerLeave() {
    if (state.battle && !state.battle.draggingTool) {
      state.battle.hoverCell = null;
    }
  }

  function beginToolDrag(tool, event) {
    const battle = state.battle;
    if (!battle || battle.dialogueOpen || battle.finishing) return;
    battle.selectedTool = tool || "basic";
    battle.draggingTool = battle.selectedTool;
    battle.dragPointer = { x: event.clientX, y: event.clientY };
    battle.hoverCell = cellFromCanvasEvent(event);
    if (!toolReady(battle.draggingTool)) setBattleToast(toolUnavailableText(battle.draggingTool));
    updateBattleDom();
    event.preventDefault();
  }

  function updateToolDrag(event) {
    const battle = state.battle;
    if (!battle || !battle.draggingTool) return;
    battle.dragPointer = { x: event.clientX, y: event.clientY };
    battle.hoverCell = cellFromCanvasEvent(event);
  }

  function finishToolDrag(event) {
    const battle = state.battle;
    if (!battle || !battle.draggingTool) return;
    const tool = battle.draggingTool;
    const cell = cellFromCanvasEvent(event);
    battle.draggingTool = null;
    battle.dragPointer = null;
    battle.hoverCell = null;
    if (!cell) {
      setBattleToast("拖到战场格位后释放");
      updateBattleDom();
      return;
    }
    deployToolAt(tool, cell);
    updateBattleDom();
  }

  function deployToolAt(tool, cell) {
    if (tool === "basic") placeBasicDefense(cell);
    if (tool === "sample") placeSampleTrap(cell);
    if (tool === "support") useSupportPulse(cell);
  }

  function toolUnavailableText(tool) {
    if (tool === "basic") return "材料或冷却不足";
    if (tool === "sample") return "样品尚未送达";
    if (tool === "support") return "支援尚未就绪";
    return "暂不可用";
  }

  function canPreviewToolAt(tool, cell) {
    if (!isCellInGrid(cell) || !toolReady(tool)) return false;
    if (tool === "basic" || tool === "sample") return canPlaceToolAt(tool, cell);
    if (tool === "support") return true;
    return false;
  }

  function buildSlots() {
    return mapRuntimePackage().build_slots || [];
  }

  function slotAt(cell) {
    return buildSlots().find(
      (slot) => slot.position && slot.position.x === cell.x && slot.position.y === cell.y,
    );
  }

  function assetKindForTool(tool) {
    if (tool === "sample") return "temporary_trap_sample";
    if (tool === "basic") return "tower_blueprint";
    return "support_item";
  }

  function canPlaceToolAt(tool, cell) {
    if (!isCellInGrid(cell) || isOccupied(cell)) return false;
    const slots = buildSlots();
    if (!slots.length) {
      const maxDistance = tool === "sample" ? 0.75 : 1.5;
      return distanceToPath(cell) <= maxDistance;
    }
    const slot = slotAt(cell);
    if (!slot) return false;
    const allowed = slot.allowed_asset_kinds || [];
    return allowed.includes(assetKindForTool(tool));
  }

  function isOccupied(cell) {
    const key = `${cell.x},${cell.y}`;
    return (
      state.battle.defenses.some((item) => item.key === key) ||
      state.battle.traps.some((item) => item.key === key && !item.expired)
    );
  }

  function placeBasicDefense(cell) {
    const battle = state.battle;
    if (battle.basicUses <= 0 || battle.resources < 20 || battle.cooldowns.basic > 0) {
      setBattleToast("材料或冷却不足");
      return;
    }
    if (!canPlaceToolAt("basic", cell)) {
      setBattleToast("灯栏需要放在可部署基座");
      return;
    }
    battle.basicUses -= 1;
    battle.resources -= 20;
    battle.cooldowns.basic = 3600;
    battle.defenses.push({
      key: `${cell.x},${cell.y}`,
      x: cell.x,
      y: cell.y,
      hp: 1,
      until: battle.elapsedMs + Math.max(10000, (battle.config.basic_defense || {}).duration_ms * 2 || 10000),
      shotAt: 0,
      name: "基础灯栏",
    });
    battle.deployedAssetIds.push("basic_lantern_barricade");
    addEffect("ring", cell.x, cell.y, "#ffd37a", 820);
    setBattleToast("基础灯栏已立起");
  }

  function placeSampleTrap(cell) {
    const battle = state.battle;
    if (!battle.sampleDelivered || battle.sampleUses <= 0 || battle.cooldowns.sample > 0) {
      setBattleToast("样品尚不可用");
      return;
    }
    if (!canPlaceToolAt("sample", cell)) {
      setBattleToast("绊索需要放在可部署基座");
      return;
    }
    battle.sampleUses -= 1;
    battle.cooldowns.sample = 1800;
    battle.traps.push({
      key: `${cell.x},${cell.y}`,
      x: cell.x,
      y: cell.y,
      armed: true,
      activeUntil: 0,
      expired: false,
      name: "折光绊索",
    });
    battle.deployedAssetIds.push("sample_trap_7f3a");
    addEffect("ring", cell.x, cell.y, "#9edcff", 1000);
    setBattleToast("折光绊索已部署");
  }

  function useSupportPulse(cell) {
    const battle = state.battle;
    if (battle.supportUses <= 0 || battle.cooldowns.support > 0 || battle.resources < 15) {
      setBattleToast("支援尚未就绪");
      return;
    }
    battle.supportUses -= 1;
    battle.resources -= 15;
    battle.cooldowns.support = 9000;
    for (const enemy of battle.enemies) {
      const dist = Math.hypot(enemy.x - cell.x, enemy.y - cell.y);
      if (dist < 2.1) {
        enemy.hp -= 1;
        enemy.slowUntil = Math.max(enemy.slowUntil, battle.elapsedMs + 2600);
      }
    }
    addEffect("ring", cell.x, cell.y, "#8fcf83", 1200, 1.6);
    addFloating(cell.x, cell.y, "守灯支援", "#c8ffd6");
    setBattleToast("守灯支援已落点");
  }

  function setBattleToast(text) {
    state.battle.toast = text;
    state.battle.toastUntil = state.battle.elapsedMs + 2200;
  }

  function showDialogue(name, line, portraitId) {
    const battle = state.battle;
    if (!battle || !battle.dom) return;
    battle.dialogueOpen = true;
    battle.paused = true;
    const portrait = mediaUrl(portraitId, "portrait", true) || mediaUrl(portraitId, "icon", true);
    battle.dom.dialogue.innerHTML = `
      <div class="dialogue-overlay">
        <div class="dialogue-focus">
          <div class="portrait-slot">${imageTag(portrait, name)}</div>
          <div class="dialogue-box">
            <div class="dialogue-name">${safeText(name)}</div>
            <div class="dialogue-line">${safeText(line)}</div>
            <div class="screen-actions" style="margin-top:12px">
              <button class="primary-button" data-action="close-dialogue">继续</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function closeDialogue() {
    const battle = state.battle;
    if (!battle) return;
    battle.dialogueOpen = false;
    battle.paused = false;
    if (battle.dom && battle.dom.dialogue) battle.dom.dialogue.innerHTML = "";
  }

  function battleFrame(ts) {
    const battle = state.battle;
    if (!battle || !battle.loopActive) return;
    if (!battle.lastFrameAt) battle.lastFrameAt = ts;
    const realDt = clamp(ts - battle.lastFrameAt, 0, 80);
    battle.lastFrameAt = ts;
    const dt = battle.paused ? 0 : realDt * battle.speed;
    updateBattle(dt);
    drawBattle();
    if (battle.elapsedMs - battle.lastDomAt > 180) {
      updateBattleDom();
      battle.lastDomAt = battle.elapsedMs;
    }
    requestAnimationFrame(battleFrame);
  }

  function updateBattle(dt) {
    const battle = state.battle;
    battle.elapsedMs += dt;
    for (const key of Object.keys(battle.cooldowns)) {
      battle.cooldowns[key] = Math.max(0, battle.cooldowns[key] - dt);
    }
    if (!battle.sampleDelivered && battle.elapsedMs >= battle.sampleDeliveryMs) {
      battle.sampleDelivered = true;
      battle.sampleUses = (battle.config.sample_asset || {}).uses_per_battle || 2;
      battle.selectedTool = "sample";
      setBattleToast("样品完成：折光绊索 x2");
      showDialogue(
        "临时工坊老师傅",
        "绊索封装完成。把它压在转角，影潮会被那道折光拖住。",
        "npc_workshop_mentor_portrait",
      );
    }
    spawnEnemies();
    updateEnemies(dt);
    updateDefenses(dt);
    updateTraps(dt);
    updateEffects(dt);
    if (!battle.finishing && battle.coreHp <= 0) {
      finishBattle("defeat");
    }
    if (
      !battle.finishing &&
      battle.spawned >= battle.spawnSchedule.length &&
      battle.enemies.length === 0 &&
      battle.elapsedMs > 5000
    ) {
      finishBattle(battle.coreHp > 0 ? "victory" : "defeat");
    }
  }

  function spawnEnemies() {
    const battle = state.battle;
    while (
      battle.spawned < battle.spawnSchedule.length &&
      battle.elapsedMs >= battle.spawnSchedule[battle.spawned].at
    ) {
      const entry = battle.spawnSchedule[battle.spawned];
      const wave = entry.wave;
      const points = pathWaypoints();
      const first = points[0] || { x: 15, y: 4 };
      battle.enemies.push({
        id: `enemy_${battle.spawned}`,
        type: wave.enemy_archetype,
        waveIndex: wave.wave_index,
        x: first.x,
        y: first.y,
        segment: 0,
        hp: wave.durability || 2,
        maxHp: wave.durability || 2,
        speed: wave.speed_cells_per_sec || 1.2,
        slowUntil: 0,
        hitFlashUntil: 0,
      });
      battle.spawned += 1;
    }
  }

  function updateEnemies(dt) {
    const battle = state.battle;
    const points = pathWaypoints();
    for (const enemy of battle.enemies) {
      if (enemy.hp <= 0) continue;
      const speed = enemy.speed * (enemy.slowUntil > battle.elapsedMs ? 0.42 : 1);
      let remaining = (dt / 1000) * speed;
      while (remaining > 0 && enemy.segment < points.length - 1) {
        const a = points[enemy.segment];
        const b = points[enemy.segment + 1];
        const dist = Math.hypot(b.x - enemy.x, b.y - enemy.y);
        if (dist <= remaining) {
          enemy.x = b.x;
          enemy.y = b.y;
          enemy.segment += 1;
          remaining -= dist;
        } else {
          enemy.x += ((b.x - enemy.x) / dist) * remaining;
          enemy.y += ((b.y - enemy.y) / dist) * remaining;
          remaining = 0;
        }
      }
      if (enemy.segment >= points.length - 1) {
        enemy.leaked = true;
        battle.coreHp -= 1;
        battle.leaks += 1;
        if (battle.optionalHp > 1 && battle.leaks % 2 === 1) battle.optionalHp -= 1;
        addFloating(enemy.x, enemy.y, "漏失", "#ff897a");
      }
    }
    battle.enemies = battle.enemies.filter((enemy) => {
      if (enemy.hp <= 0) {
        battle.kills += 1;
        addEffect("burst", enemy.x, enemy.y, "#777b92", 420);
        return false;
      }
      return !enemy.leaked;
    });
  }

  function updateDefenses() {
    const battle = state.battle;
    for (const defense of battle.defenses) {
      if (battle.elapsedMs > defense.until) {
        defense.expired = true;
        continue;
      }
      if (battle.elapsedMs < defense.shotAt + 760) continue;
      const target = nearestEnemy(defense.x, defense.y, 2.6);
      if (!target) continue;
      defense.shotAt = battle.elapsedMs;
      target.hp -= 1;
      target.hitFlashUntil = battle.elapsedMs + 160;
      addBeam(defense.x, defense.y, target.x, target.y, "#ffd37a");
      addEffect("burst", target.x, target.y, "#ffbf66", 240, 0.55);
    }
    battle.defenses = battle.defenses.filter((item) => !item.expired);
  }

  function updateTraps() {
    const battle = state.battle;
    for (const trap of battle.traps) {
      if (trap.expired) continue;
      if (trap.armed) {
        const enemy = nearestEnemy(trap.x, trap.y, 0.78);
        if (enemy) {
          trap.armed = false;
          trap.activeUntil = battle.elapsedMs + 7800;
          addEffect("ring", trap.x, trap.y, "#9edcff", 1100, 1.8);
          addEffect("aura", trap.x, trap.y, "#9edcff", 7800, 1.5);
          addFloating(trap.x, trap.y, "迟滞", "#b8f1ff");
        }
      }
      if (!trap.armed && battle.elapsedMs <= trap.activeUntil) {
        for (const enemy of battle.enemies) {
          if (Math.hypot(enemy.x - trap.x, enemy.y - trap.y) < 1.65) {
            enemy.slowUntil = Math.max(enemy.slowUntil, battle.elapsedMs + 900);
          }
        }
      }
      if (!trap.armed && battle.elapsedMs > trap.activeUntil) {
        trap.expired = true;
      }
    }
    battle.traps = battle.traps.filter((trap) => !trap.expired);
  }

  function nearestEnemy(x, y, radius) {
    let best = null;
    let bestDist = Infinity;
    for (const enemy of state.battle.enemies) {
      const dist = Math.hypot(enemy.x - x, enemy.y - y);
      if (dist < radius && dist < bestDist) {
        best = enemy;
        bestDist = dist;
      }
    }
    return best;
  }

  function addEffect(type, x, y, color, duration, scale = 1) {
    state.battle.effects.push({
      type,
      x,
      y,
      color,
      duration,
      scale,
      age: 0,
    });
  }

  function addBeam(x1, y1, x2, y2, color) {
    state.battle.effects.push({
      type: "beam",
      x: x1,
      y: y1,
      x2,
      y2,
      color,
      duration: 130,
      age: 0,
    });
  }

  function addFloating(x, y, text, color) {
    state.battle.effects.push({
      type: "text",
      x,
      y,
      text,
      color,
      duration: 900,
      age: 0,
    });
  }

  function updateEffects(dt) {
    const battle = state.battle;
    for (const effect of battle.effects) effect.age += dt;
    battle.effects = battle.effects.filter((effect) => effect.age < effect.duration);
  }

  function waveLabel() {
    const battle = state.battle;
    const active = battle.enemies.reduce((max, enemy) => Math.max(max, enemy.waveIndex || 1), 1);
    const spawned = battle.spawned;
    if (spawned <= 0) return "待接敌";
    return `${active}/${(battle.config.waves || []).length}`;
  }

  function updateBattleDom() {
    const battle = state.battle;
    if (!battle.dom) return;
    const objectives = mapObjectives();
    const coreTarget = objectives.core_target || {};
    const optionalTarget = (objectives.optional_targets || [])[0] || {};
    battle.dom.stats.innerHTML = `
      <div class="top-stat"><span>波次</span><strong>${safeText(waveLabel())}</strong></div>
      <div class="top-stat"><span>核心</span><strong>${battle.coreHp}/${coreTarget.durability || 10}</strong></div>
      <div class="top-stat"><span>电力</span><strong>${battle.power}</strong></div>
      <div class="top-stat"><span>材料</span><strong>${battle.resources}</strong></div>
      <div class="top-stat"><span>漏失</span><strong>${battle.leaks}</strong></div>
    `;
    battle.dom.tasks.innerHTML = `
      <h2 class="panel-title">本场目标</h2>
      <div class="event-list">
        <div class="event-item"><strong>守住核心</strong><span>${safeText(battle.config.victory_condition || "")}</span></div>
        <div class="event-item"><strong>保护信标</strong><span>当前耐久 ${battle.optionalHp}/${optionalTarget.durability || 4}</span></div>
        <div class="event-item"><strong>现场状态</strong><span>${safeText(battle.sampleDelivered ? "折光绊索已送达。" : sampleProgressMessage())}</span></div>
        <div class="event-item"><strong>环境影响</strong><span>低雾压在路径转角，迟滞场更容易成形。</span></div>
      </div>
    `;
    battle.dom.info.innerHTML = `
      <div class="side-avatar">${imageTag(npcPortraitUrl("npc_gray_lantern_keeper"), "灰灯驿站守灯人")}</div>
      <h2 class="panel-title">战术面板</h2>
      <div class="event-list">
        <div class="event-item"><strong>下一波</strong><span>${safeText(nextWaveText())}</span></div>
        <div class="event-item"><strong>敌人弱点</strong><span>低耐久，受灯栏打击后容易散开。</span></div>
        <div class="event-item"><strong>NPC 建议</strong><span>${safeText(battle.sampleDelivered ? "把绊索压在主路转角，能拖住第二波残影。" : "先在主路边缘立灯栏，别让第一波直冲核心。")}</span></div>
      </div>
    `;
    battle.dom.tools.innerHTML = battleToolsMarkup();
    battle.dom.toast.textContent =
      battle.toastUntil && battle.elapsedMs > battle.toastUntil ? "" : battle.toast || "";
    battle.dom.pause.textContent = battle.paused ? "继续" : "暂停";
    battle.dom.speed.textContent = `${battle.speed}x`;
  }

  function sampleProgressMessage() {
    const sample = battleConfig().sample_asset || {};
    const messages = sample.delivery_progress_messages || ["现场试作中。"];
    const ratio = clamp(state.battle.elapsedMs / state.battle.sampleDeliveryMs, 0, 0.99);
    return messages[Math.floor(ratio * messages.length)] || messages[0];
  }

  function nextWaveText() {
    const battle = state.battle;
    const next = battle.spawnSchedule.find((entry, index) => index >= battle.spawned);
    if (!next) return battle.enemies.length ? "场上残敌" : "敌潮将尽";
    const delay = Math.max(0, Math.ceil((next.at - battle.elapsedMs) / 1000));
    return `${next.wave.display_name || "下一波"} · ${delay}s`;
  }

  function toolReady(tool) {
    const battle = state.battle;
    if (tool === "basic") return battle.basicUses > 0 && battle.resources >= 20 && battle.cooldowns.basic <= 0;
    if (tool === "sample") return battle.sampleDelivered && battle.sampleUses > 0 && battle.cooldowns.sample <= 0;
    if (tool === "support") return battle.supportUses > 0 && battle.resources >= 15 && battle.cooldowns.support <= 0;
    return false;
  }

  function toolCooldownFill(tool) {
    const battle = state.battle;
    const max = tool === "basic" ? 3600 : tool === "sample" ? 1800 : 9000;
    return `${100 - Math.round((battle.cooldowns[tool] / max) * 100)}%`;
  }

  function battleToolsMarkup() {
    const battle = state.battle;
    const basicUrl = mediaUrl("defense_basic_lantern_barricade", "icon", true);
    const sampleUrl = sampleIconUrl();
    const npcUrl = mediaUrl("npc_gray_lantern_keeper_portrait", "icon", true);
    const tools = [
      {
        id: "basic",
        name: "基础灯栏",
        img: basicUrl,
        meta: [`材料 20`, `剩余 ${battle.basicUses}`],
        locked: false,
      },
      {
        id: "sample",
        name: "折光绊索",
        img: sampleUrl,
        meta: [battle.sampleDelivered ? `剩余 ${battle.sampleUses}` : "封装中", "减速"],
        locked: !battle.sampleDelivered,
      },
      {
        id: "support",
        name: "守灯支援",
        img: npcUrl,
        meta: [`材料 15`, `剩余 ${battle.supportUses}`],
        locked: false,
      },
    ];
    return tools
      .map(
        (tool) => `
          <button class="toolbar-card ${battle.selectedTool === tool.id ? "is-selected" : ""} ${battle.draggingTool === tool.id ? "is-dragging" : ""} ${tool.locked || !toolReady(tool.id) ? "is-locked" : ""}" data-action="select-tool" data-tool="${tool.id}" draggable="false">
            <span class="tool-icon">${imageTag(tool.img, tool.name)}</span>
            <span class="tool-body">
              <span class="tool-name">${safeText(tool.name)}</span>
              <span class="tool-meta">${tool.meta.map((item) => `<span>${safeText(item)}</span>`).join("")}</span>
              <span class="cooldown-bar"><i style="--fill:${toolCooldownFill(tool.id)}"></i></span>
            </span>
          </button>
        `,
      )
      .join("");
  }

  function drawBattle() {
    const battle = state.battle;
    const ctx = battle.ctx;
    const m = battle.metrics;
    if (!ctx || !m) return;
    ctx.clearRect(0, 0, m.width, m.height);
    drawBackdrop(ctx, m);
    drawSlotAccessTrails(ctx);
    drawPath(ctx);
    drawDeployHints(ctx);
    drawWorldObjects(ctx);
    drawSpawnMarkers(ctx);
    drawEntities(ctx);
    drawEffects(ctx);
    drawDragGhost(ctx);
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
    return profiles[nodeId] || profiles.gray_lantern_station;
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
      wisps,
      roadsideProps,
      accessTrails,
    };
    if (battle) battle.terrainFeatureSet = features;
    return features;
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
    drawProceduralTerrain(ctx, m);
    drawMapDebugOverlay(ctx, m);
    drawEdgeFog(ctx, m);
  }

  function drawProceduralTerrain(ctx, m) {
    const features = terrainFeatureSet();
    const soil = features.profile.soil;
    const grd = ctx.createLinearGradient(0, 0, m.width, m.height);
    grd.addColorStop(0, soil[0]);
    grd.addColorStop(0.36, soil[1]);
    grd.addColorStop(0.68, soil[2]);
    grd.addColorStop(1, soil[3]);
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, m.width, m.height);

    drawTerrainDepthBands(ctx, m, features);

    for (const patch of features.patches) {
      drawOrganicTerrainPatch(ctx, m, patch);
    }

    drawDarkTidePools(ctx, features);

    ctx.save();
    for (const speck of features.specks) {
      ctx.fillStyle = speck.warm
        ? `rgba(209,180,111,${speck.alpha})`
        : `rgba(149,174,151,${speck.alpha})`;
      ctx.beginPath();
      ctx.ellipse(
        speck.x * m.width,
        speck.y * m.height,
        speck.size * m.scale,
        speck.size * 0.42 * m.scale,
        0,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
    ctx.restore();

    drawTerrainDebris(ctx, features);
  }

  function drawTerrainDepthBands(ctx, m, features) {
    ctx.save();
    for (const band of features.bands || []) {
      const y = band.y * m.height;
      const h = band.height * m.height;
      const lean = band.lean * m.width;
      ctx.fillStyle = band.warm
        ? `rgba(193,160,91,${band.alpha})`
        : `rgba(86,132,118,${band.alpha})`;
      ctx.beginPath();
      ctx.moveTo(-80, y);
      ctx.bezierCurveTo(
        m.width * 0.25,
        y + h * 0.3,
        m.width * 0.55,
        y - h * 0.24,
        m.width + 80,
        y + lean * 0.12,
      );
      ctx.lineTo(m.width + 80, y + h + lean * 0.1);
      ctx.bezierCurveTo(
        m.width * 0.6,
        y + h * 1.22,
        m.width * 0.25,
        y + h * 0.76,
        -80,
        y + h * 0.98,
      );
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function drawDarkTidePools(ctx, features) {
    const m = state.battle.metrics;
    ctx.save();
    for (const pool of features.darkPools || []) {
      const p = projectCell(pool.x, pool.y);
      const rx = m.tileW * pool.rx;
      const ry = m.tileH * pool.ry;
      const grd = ctx.createRadialGradient(p.x, p.y, 2, p.x, p.y, rx);
      grd.addColorStop(0, `rgba(18,15,28,${pool.alpha + 0.08})`);
      grd.addColorStop(0.58, `rgba(25,31,29,${pool.alpha})`);
      grd.addColorStop(1, "rgba(9,12,12,0)");
      ctx.fillStyle = grd;
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, rx, ry, pool.rotation, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = `rgba(118,132,118,${pool.alpha * 0.5})`;
      ctx.lineWidth = Math.max(1, m.tileW * 0.01);
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, rx * 0.72, ry * 0.58, pool.rotation, 0.2, Math.PI * 1.25);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawOrganicTerrainPatch(ctx, m, patch) {
    const cx = patch.x * m.width;
    const cy = patch.y * m.height;
    const rx = patch.rx * m.width;
    const ry = patch.ry * m.height;
    const points = patch.wobble.map((scale, index) => {
      const angle = (index / patch.wobble.length) * Math.PI * 2 + patch.rotation;
      return {
        x: cx + Math.cos(angle) * rx * scale,
        y: cy + Math.sin(angle) * ry * scale,
      };
    });
    ctx.save();
    ctx.fillStyle = patch.color;
    ctx.beginPath();
    points.forEach((point, index) => {
      const next = points[(index + 1) % points.length];
      const mx = (point.x + next.x) / 2;
      const my = (point.y + next.y) / 2;
      if (index === 0) ctx.moveTo(mx, my);
      const afterNext = points[(index + 2) % points.length];
      ctx.quadraticCurveTo(
        next.x,
        next.y,
        (next.x + afterNext.x) / 2,
        (next.y + afterNext.y) / 2,
      );
    });
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawTerrainDebris(ctx, features) {
    const m = state.battle.metrics;
    ctx.save();
    for (const item of features.debris) {
      const p = projectCell(item.x + item.dx, item.y + item.dy);
      if (p.x < -80 || p.y < -80 || p.x > m.width + 80 || p.y > m.height + 80) continue;
      const size = item.size * Math.max(5, m.tileH * 0.22);
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(item.rotation);
      if (item.kind === "reed") {
        ctx.strokeStyle = item.shade > 0.5 ? "rgba(139,159,103,0.26)" : "rgba(88,117,96,0.28)";
        ctx.lineWidth = Math.max(1, size * 0.1);
        for (let i = 0; i < 3; i += 1) {
          const lean = (i - 1) * size * 0.16;
          ctx.beginPath();
          ctx.moveTo(lean, size * 0.2);
          ctx.quadraticCurveTo(lean + size * 0.28, -size * 0.35, lean + size * 0.1, -size);
          ctx.stroke();
        }
      } else if (item.kind === "scrap") {
        ctx.fillStyle = "rgba(126,110,82,0.34)";
        ctx.strokeStyle = "rgba(235,199,126,0.12)";
        ctx.lineWidth = 1;
        ctx.fillRect(-size * 0.45, -size * 0.12, size * 0.9, size * 0.24);
        ctx.strokeRect(-size * 0.45, -size * 0.12, size * 0.9, size * 0.24);
      } else {
        ctx.fillStyle = item.shade > 0.5 ? "rgba(103,95,75,0.46)" : "rgba(68,72,59,0.48)";
        ctx.beginPath();
        ctx.ellipse(0, 0, size * 0.42, size * 0.24, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }
    ctx.restore();
  }

  function drawMapDebugOverlay(ctx, m) {
    const debugUrl = debugBattleMapVisualUrls()[0];
    const debugBoard = debugUrl ? getImage(debugUrl) : null;
    if (!debugBoard || !debugBoard.complete || !debugBoard.naturalWidth) return;
    ctx.save();
    ctx.globalAlpha = 0.16;
    ctx.filter = "grayscale(0.8) sepia(0.24) contrast(0.72)";
    ctx.drawImage(debugBoard, m.imageOffsetX, m.imageOffsetY, m.imageWidth, m.imageHeight);
    ctx.restore();
  }

  function drawEdgeFog(ctx, m) {
    const top = ctx.createLinearGradient(0, 0, 0, m.height * 0.34);
    top.addColorStop(0, "rgba(3,5,5,0.46)");
    top.addColorStop(1, "rgba(3,5,5,0)");
    ctx.fillStyle = top;
    ctx.fillRect(0, 0, m.width, m.height * 0.36);

    const bottom = ctx.createLinearGradient(0, m.height, 0, m.height * 0.58);
    bottom.addColorStop(0, "rgba(0,0,0,0.58)");
    bottom.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = bottom;
    ctx.fillRect(0, m.height * 0.56, m.width, m.height * 0.44);

    const side = ctx.createLinearGradient(0, 0, m.width, 0);
    side.addColorStop(0, "rgba(0,0,0,0.42)");
    side.addColorStop(0.16, "rgba(0,0,0,0)");
    side.addColorStop(0.84, "rgba(0,0,0,0)");
    side.addColorStop(1, "rgba(0,0,0,0.46)");
    ctx.fillStyle = side;
    ctx.fillRect(0, 0, m.width, m.height);

    const features = terrainFeatureSet();
    const time = (state.battle.elapsedMs || 0) / 1200;
    ctx.save();
    ctx.lineCap = "round";
    for (const wisp of features.wisps) {
      const fromLeft = wisp.edge === 0;
      const fromRight = wisp.edge === 1;
      const fromTop = wisp.edge === 2;
      const x = fromLeft
        ? -20
        : fromRight
          ? m.width + 20
          : wisp.offset * m.width;
      const y = fromTop
        ? -16
        : wisp.offset * m.height;
      const drift = Math.sin(time + wisp.sway * Math.PI * 2) * 18;
      ctx.strokeStyle = `rgba(153,171,157,${wisp.alpha})`;
      ctx.lineWidth = Math.max(16, wisp.width * 0.18);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.bezierCurveTo(
        x + (fromLeft ? wisp.width : fromRight ? -wisp.width : drift),
        y + (fromTop ? wisp.width * 0.35 : drift),
        x + (fromLeft ? wisp.width * 1.6 : fromRight ? -wisp.width * 1.6 : -drift),
        y + wisp.width * 0.2,
        x + (fromLeft ? wisp.width * 2.2 : fromRight ? -wisp.width * 2.2 : drift * 0.5),
        y + (fromTop ? wisp.width * 0.74 : drift * 0.4),
      );
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawPath(ctx) {
    const m = state.battle.metrics;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const route of allPathRoutes()) {
      const points = (route.waypoints || []).map((p) => projectCell(p.x, p.y));
      if (points.length < 2) continue;
      const roadWidth = Math.max(34, m.tileW * 0.48);
      drawRouteShoulders(ctx, route, points, roadWidth);
      ctx.strokeStyle = "rgba(18,13,10,0.54)";
      ctx.lineWidth = roadWidth * 1.18;
      traceRoutePath(ctx, points);
      ctx.stroke();
      ctx.strokeStyle = "rgba(82,62,37,0.86)";
      ctx.lineWidth = roadWidth;
      traceRoutePath(ctx, points);
      ctx.stroke();
      ctx.strokeStyle = "rgba(143,112,64,0.64)";
      ctx.lineWidth = roadWidth * 0.68;
      traceRoutePath(ctx, points);
      ctx.stroke();
      ctx.strokeStyle = "rgba(201,169,103,0.18)";
      ctx.lineWidth = Math.max(5, roadWidth * 0.14);
      traceRoutePath(ctx, points);
      ctx.stroke();
      drawRoadPebbles(ctx, route, points, roadWidth);
      drawRoadRuts(ctx, route, points, roadWidth);
      drawRouteEdgeProps(ctx, route, roadWidth);
    }
    ctx.restore();
  }

  function drawRouteEdgeProps(ctx, route, roadWidth) {
    const m = state.battle.metrics;
    const props = (terrainFeatureSet().roadsideProps || []).filter(
      (item) => item.routeId === (route.route_id || "route"),
    );
    ctx.save();
    for (const item of props) {
      const p = projectCell(item.x, item.y);
      if (p.x < -80 || p.y < -80 || p.x > m.width + 80 || p.y > m.height + 80) continue;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(item.rotation);
      const scale = item.scale * Math.max(0.72, m.scale) * Math.max(0.78, roadWidth / 56);
      drawRoadsideProp(ctx, item.kind, scale, item.warm);
      ctx.restore();
    }
    ctx.restore();
  }

  function drawRoadsideProp(ctx, kind, scale, warm) {
    ctx.fillStyle = "rgba(0,0,0,0.18)";
    ctx.beginPath();
    ctx.ellipse(0, 5 * scale, 13 * scale, 5 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
    if (kind === "lamp_marker") {
      ctx.strokeStyle = "rgba(118,109,78,0.55)";
      ctx.lineWidth = Math.max(1, 1.2 * scale);
      ctx.beginPath();
      ctx.moveTo(0, 5 * scale);
      ctx.lineTo(0, -17 * scale);
      ctx.stroke();
      ctx.fillStyle = warm ? "rgba(255,213,126,0.42)" : "rgba(158,220,255,0.32)";
      ctx.beginPath();
      ctx.ellipse(0, -20 * scale, 5 * scale, 7 * scale, 0, 0, Math.PI * 2);
      ctx.fill();
    } else if (kind === "pipe") {
      ctx.fillStyle = "rgba(85,88,76,0.54)";
      ctx.strokeStyle = "rgba(190,168,111,0.12)";
      ctx.lineWidth = Math.max(1, 0.9 * scale);
      ctx.fillRect(-12 * scale, -3 * scale, 24 * scale, 6 * scale);
      ctx.strokeRect(-12 * scale, -3 * scale, 24 * scale, 6 * scale);
    } else if (kind === "crate") {
      ctx.fillStyle = "rgba(119,87,49,0.58)";
      ctx.strokeStyle = "rgba(230,193,111,0.16)";
      ctx.lineWidth = Math.max(1, scale);
      ctx.fillRect(-8 * scale, -8 * scale, 16 * scale, 15 * scale);
      ctx.strokeRect(-8 * scale, -8 * scale, 16 * scale, 15 * scale);
    } else if (kind === "signal_stake") {
      ctx.strokeStyle = "rgba(121,137,130,0.46)";
      ctx.lineWidth = Math.max(1, 1.2 * scale);
      ctx.beginPath();
      ctx.moveTo(-4 * scale, 5 * scale);
      ctx.lineTo(2 * scale, -19 * scale);
      ctx.moveTo(2 * scale, -15 * scale);
      ctx.lineTo(13 * scale, -10 * scale);
      ctx.stroke();
    } else if (kind === "scrap") {
      ctx.fillStyle = "rgba(121,111,82,0.48)";
      ctx.fillRect(-10 * scale, -3 * scale, 20 * scale, 6 * scale);
    } else {
      ctx.fillStyle = "rgba(88,82,61,0.5)";
      ctx.beginPath();
      ctx.ellipse(0, 0, 9 * scale, 5 * scale, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function traceRoutePath(ctx, points) {
    ctx.beginPath();
    if (points.length < 2) return;
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length - 1; i += 1) {
      const prev = points[i - 1];
      const cur = points[i];
      const next = points[i + 1];
      const d1 = Math.hypot(cur.x - prev.x, cur.y - prev.y);
      const d2 = Math.hypot(next.x - cur.x, next.y - cur.y);
      const radius = Math.min(48, d1 * 0.32, d2 * 0.32);
      const entry = {
        x: cur.x - ((cur.x - prev.x) / Math.max(1, d1)) * radius,
        y: cur.y - ((cur.y - prev.y) / Math.max(1, d1)) * radius,
      };
      const exit = {
        x: cur.x + ((next.x - cur.x) / Math.max(1, d2)) * radius,
        y: cur.y + ((next.y - cur.y) / Math.max(1, d2)) * radius,
      };
      ctx.lineTo(entry.x, entry.y);
      ctx.quadraticCurveTo(cur.x, cur.y, exit.x, exit.y);
    }
    const last = points[points.length - 1];
    ctx.lineTo(last.x, last.y);
  }

  function drawRouteShoulders(ctx, route, points, roadWidth) {
    const m = state.battle.metrics;
    ctx.save();
    ctx.strokeStyle = "rgba(6,7,6,0.42)";
    ctx.lineWidth = roadWidth * 1.7;
    traceRoutePath(ctx, points);
    ctx.stroke();
    ctx.strokeStyle = "rgba(61,69,46,0.62)";
    ctx.lineWidth = roadWidth * 1.44;
    traceRoutePath(ctx, points);
    ctx.stroke();
    ctx.strokeStyle = "rgba(33,41,32,0.46)";
    ctx.lineWidth = roadWidth * 1.28;
    traceRoutePath(ctx, points);
    ctx.stroke();

    const rng = makeSeededRandom(runtimeMapSeed() ^ hashString(`shoulder:${route.route_id || ""}`));
    ctx.fillStyle = "rgba(169,142,85,0.12)";
    for (let i = 0; i < points.length; i += 1) {
      const p = points[i];
      for (let j = 0; j < 3; j += 1) {
        const angle = rng() * Math.PI * 2;
        const dist = roadWidth * (0.65 + rng() * 0.28);
        ctx.beginPath();
        ctx.ellipse(
          p.x + Math.cos(angle) * dist,
          p.y + Math.sin(angle) * dist * 0.6,
          m.tileW * (0.035 + rng() * 0.04),
          m.tileH * (0.025 + rng() * 0.04),
          angle,
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawRoadPebbles(ctx, route, points, roadWidth) {
    const rng = makeSeededRandom(runtimeMapSeed() ^ hashString(`road:${route.route_id || ""}`));
    ctx.save();
    for (let i = 0; i < points.length - 1; i += 1) {
      const a = points[i];
      const b = points[i + 1];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = Math.max(1, Math.hypot(dx, dy));
      const nx = -dy / len;
      const ny = dx / len;
      const count = Math.max(3, Math.floor(len / 46));
      for (let j = 0; j < count; j += 1) {
        const t = (j + 0.18 + rng() * 0.68) / count;
        const edge = rng() < 0.55 ? -1 : 1;
        const offset = edge * roadWidth * (0.24 + rng() * 0.28);
        const x = a.x + dx * t + nx * offset;
        const y = a.y + dy * t + ny * offset;
        const size = 2.4 + rng() * Math.max(5, roadWidth * 0.1);
        ctx.fillStyle = rng() > 0.4 ? "rgba(196,164,102,0.24)" : "rgba(53,47,36,0.28)";
        ctx.beginPath();
        ctx.ellipse(x, y, size, size * 0.42, rng() * Math.PI, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawRoadRuts(ctx, route, points, roadWidth) {
    const rng = makeSeededRandom(runtimeMapSeed() ^ hashString(`ruts:${route.route_id || ""}`));
    ctx.save();
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(62,45,27,0.24)";
    ctx.lineWidth = Math.max(2, roadWidth * 0.055);
    for (const offset of [-0.18, 0.16]) {
      ctx.beginPath();
      points.forEach((point, index) => {
        const prev = points[Math.max(0, index - 1)];
        const next = points[Math.min(points.length - 1, index + 1)];
        const dx = next.x - prev.x;
        const dy = next.y - prev.y;
        const len = Math.max(1, Math.hypot(dx, dy));
        const nx = -dy / len;
        const ny = dx / len;
        const wobble = (rng() - 0.5) * roadWidth * 0.08;
        const x = point.x + nx * roadWidth * offset + nx * wobble;
        const y = point.y + ny * roadWidth * offset + ny * wobble;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    ctx.strokeStyle = "rgba(207,170,96,0.12)";
    ctx.lineWidth = Math.max(1, roadWidth * 0.04);
    for (let i = 0; i < points.length - 1; i += 1) {
      const a = points[i];
      const b = points[i + 1];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = Math.max(1, Math.hypot(dx, dy));
      const count = Math.max(1, Math.floor(len / 130));
      const nx = -dy / len;
      const ny = dx / len;
      for (let j = 0; j < count; j += 1) {
        if (rng() < 0.42) continue;
        const t = (j + 0.35 + rng() * 0.3) / count;
        const cx = a.x + dx * t;
        const cy = a.y + dy * t;
        ctx.beginPath();
        ctx.moveTo(cx - nx * roadWidth * 0.28, cy - ny * roadWidth * 0.28);
        ctx.lineTo(cx + nx * roadWidth * 0.28, cy + ny * roadWidth * 0.28);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawSlotAccessTrails(ctx) {
    const m = state.battle.metrics;
    const trails = terrainFeatureSet().accessTrails || [];
    if (!trails.length) return;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const trail of trails) {
      const from = projectCell(trail.from.x, trail.from.y);
      const to = projectCell(trail.to.x, trail.to.y);
      const mid = {
        x: (from.x + to.x) / 2,
        y: (from.y + to.y) / 2 - m.tileH * 0.08,
      };
      ctx.strokeStyle = "rgba(23,16,10,0.18)";
      ctx.lineWidth = Math.max(6, m.tileW * 0.072);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y + m.tileH * 0.03);
      ctx.quadraticCurveTo(mid.x, mid.y, to.x, to.y);
      ctx.stroke();
      ctx.strokeStyle = "rgba(167,134,73,0.13)";
      ctx.lineWidth = Math.max(2, m.tileW * 0.026);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y + m.tileH * 0.02);
      ctx.quadraticCurveTo(mid.x, mid.y, to.x, to.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawDeployHints(ctx) {
    const battle = state.battle;
    const m = battle.metrics;
    const activeOverlay = Boolean(battle.draggingTool || battle.hoverCell);
    suggestedSockets().forEach((slot, index) => {
      const cell = slot.position || slot;
      const p = projectCell(cell.x, cell.y);
      drawDeploymentBase(ctx, p, m, index, activeOverlay);
    });
    const previewCell = battle.hoverCell;
    if (previewCell) {
      const p = projectCell(previewCell.x, previewCell.y);
      const tool = battle.draggingTool || battle.selectedTool;
      const valid = canPreviewToolAt(tool, previewCell);
      ctx.save();
      ctx.fillStyle = valid ? "rgba(255,211,122,.17)" : "rgba(255,95,83,.16)";
      ctx.strokeStyle = valid ? "rgba(255,225,161,.74)" : "rgba(255,95,83,.72)";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, m.tileW * 0.31, m.tileH * 0.42, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
      ctx.save();
      ctx.globalAlpha = valid ? 0.92 : 0.42;
      if (tool === "basic") {
        drawSprite(
          ctx,
          mediaSpriteRef("defense_basic_lantern_barricade", "defense_sprite", true),
          p.x,
          p.y,
          62,
        );
      } else if (tool === "sample") {
        drawGroundGlow(ctx, p.x, p.y, "#9edcff", 0.3, 42);
        ctx.strokeStyle = "#9edcff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(p.x, p.y, 24, 10, 0, 0, Math.PI * 2);
        ctx.stroke();
      } else if (tool === "support") {
        drawGroundGlow(ctx, p.x, p.y, "#8fcf83", 0.28, 86);
      }
      ctx.restore();
    }
  }

  function drawDeploymentBase(ctx, p, m, index, active) {
    const rng = makeSeededRandom(runtimeMapSeed() ^ hashString(`slot:${index}`));
    const rx = m.tileW * (0.22 + rng() * 0.035);
    const ry = m.tileH * (0.28 + rng() * 0.04);
    ctx.save();
    ctx.globalAlpha = active ? 0.95 : 0.58;
    ctx.fillStyle = "rgba(0,0,0,0.34)";
    ctx.beginPath();
    ctx.ellipse(p.x, p.y + m.tileH * 0.1, rx * 1.18, ry * 0.76, 0, 0, Math.PI * 2);
    ctx.fill();

    const base = ctx.createLinearGradient(p.x, p.y - ry, p.x, p.y + ry);
    base.addColorStop(0, "rgba(126,111,78,0.72)");
    base.addColorStop(0.54, "rgba(74,69,52,0.76)");
    base.addColorStop(1, "rgba(35,34,28,0.88)");
    ctx.fillStyle = base;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = active ? "rgba(255,225,161,0.68)" : "rgba(213,184,118,0.28)";
    ctx.lineWidth = Math.max(1.4, m.tileW * 0.015);
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, rx, ry, 0, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = active ? "rgba(255,224,145,0.42)" : "rgba(178,156,106,0.2)";
    for (let i = 0; i < 3; i += 1) {
      const a = rng() * Math.PI * 2;
      ctx.beginPath();
      ctx.arc(p.x, p.y, rx * (0.48 + i * 0.12), a, a + Math.PI * (0.2 + rng() * 0.18));
      ctx.stroke();
    }

    ctx.fillStyle = active ? "rgba(255,211,122,0.26)" : "rgba(255,211,122,0.13)";
    ctx.beginPath();
    ctx.ellipse(p.x, p.y - ry * 0.18, rx * 0.28, ry * 0.24, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function suggestedSockets() {
    const slots = buildSlots();
    if (slots.length) return slots;
    return [
      { position: { x: 12, y: 3 } },
      { position: { x: 9, y: 3 } },
      { position: { x: 8, y: 1 } },
      { position: { x: 5, y: 1 } },
      { position: { x: 6, y: 5 } },
      { position: { x: 3, y: 5 } },
    ];
  }

  function drawWorldObjects(ctx) {
    drawBattlefieldLandmarks(ctx);
    const objectives = mapObjectives();
    const core = objectives.core_target || { position: { x: 0, y: 6 } };
    const coreP = projectCell(core.position.x, core.position.y);
    drawTargetFoundation(ctx, coreP.x, coreP.y, "core");
    drawSprite(ctx, mediaSpriteRef("objective_station_core", "objective_sprite", true), coreP.x, coreP.y, 92);
    for (const target of objectives.optional_targets || []) {
      const p = projectCell(target.position.x, target.position.y);
      drawTargetFoundation(ctx, p.x, p.y, "beacon");
      drawSprite(ctx, mediaSpriteRef("objective_signal_beacon", "objective_sprite", true), p.x, p.y, 72);
    }
    for (const defense of state.battle.defenses) {
      const p = projectCell(defense.x, defense.y);
      drawSprite(ctx, mediaSpriteRef("defense_basic_lantern_barricade", "defense_sprite", true), p.x, p.y, 66);
      drawGroundGlow(ctx, p.x, p.y, "#ffd37a", 0.16, 34);
    }
    for (const trap of state.battle.traps) {
      const p = projectCell(trap.x, trap.y);
      drawGroundGlow(ctx, p.x, p.y, "#9edcff", trap.armed ? 0.18 : 0.3, trap.armed ? 28 : 54);
      ctx.strokeStyle = "#9edcff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, 24, 10, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  function drawBattlefieldLandmarks(ctx) {
    const features = terrainFeatureSet();
    const m = state.battle.metrics;
    ctx.save();
    for (const landmark of features.landmarks || []) {
      const p = projectCell(landmark.x, landmark.y);
      if (p.x < -80 || p.y < -80 || p.x > m.width + 80 || p.y > m.height + 80) continue;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(landmark.rotation);
      const scale = landmark.scale * Math.max(0.76, m.scale);
      if (landmark.kind === "supply_cache") {
        drawSupplyCache(ctx, scale, landmark.warm);
      } else if (landmark.kind === "lamp_relic") {
        drawLampRelic(ctx, scale, landmark.warm);
      } else if (landmark.kind === "signal_scrap") {
        drawSignalScrap(ctx, scale);
      } else {
        drawCollapsedWall(ctx, scale);
      }
      ctx.restore();
    }
    ctx.restore();
  }

  function drawCollapsedWall(ctx, scale) {
    ctx.fillStyle = "rgba(0,0,0,0.24)";
    ctx.beginPath();
    ctx.ellipse(0, 8 * scale, 34 * scale, 11 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(84,78,58,0.62)";
    ctx.strokeStyle = "rgba(205,176,111,0.12)";
    ctx.lineWidth = Math.max(1, 1.3 * scale);
    for (let i = 0; i < 4; i += 1) {
      const x = (i - 1.5) * 14 * scale;
      const h = (10 + (i % 2) * 7) * scale;
      ctx.fillRect(x, -h, 12 * scale, h + 8 * scale);
      ctx.strokeRect(x, -h, 12 * scale, h + 8 * scale);
    }
  }

  function drawSupplyCache(ctx, scale, warm) {
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    ctx.beginPath();
    ctx.ellipse(0, 8 * scale, 28 * scale, 10 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = warm ? "rgba(115,88,48,0.72)" : "rgba(82,93,77,0.68)";
    ctx.strokeStyle = "rgba(230,194,112,0.18)";
    ctx.lineWidth = Math.max(1, 1.2 * scale);
    ctx.fillRect(-18 * scale, -10 * scale, 36 * scale, 18 * scale);
    ctx.strokeRect(-18 * scale, -10 * scale, 36 * scale, 18 * scale);
    ctx.fillStyle = "rgba(223,185,103,0.22)";
    ctx.fillRect(-3 * scale, -10 * scale, 6 * scale, 18 * scale);
  }

  function drawLampRelic(ctx, scale, warm) {
    ctx.fillStyle = "rgba(0,0,0,0.23)";
    ctx.beginPath();
    ctx.ellipse(0, 9 * scale, 24 * scale, 9 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(138,126,90,0.48)";
    ctx.lineWidth = Math.max(1.2, 1.6 * scale);
    ctx.beginPath();
    ctx.moveTo(0, 8 * scale);
    ctx.lineTo(0, -24 * scale);
    ctx.stroke();
    const glow = warm ? "rgba(255,210,114,0.38)" : "rgba(142,216,216,0.28)";
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.ellipse(0, -30 * scale, 9 * scale, 13 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawSignalScrap(ctx, scale) {
    ctx.fillStyle = "rgba(0,0,0,0.24)";
    ctx.beginPath();
    ctx.ellipse(0, 9 * scale, 30 * scale, 10 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(111,122,102,0.34)";
    ctx.lineWidth = Math.max(1, 1.25 * scale);
    for (let i = 0; i < 3; i += 1) {
      const x = (i - 1) * 10 * scale;
      ctx.beginPath();
      ctx.moveTo(x, 4 * scale);
      ctx.lineTo(x + 8 * scale, -18 * scale - i * 4 * scale);
      ctx.stroke();
    }
    ctx.strokeStyle = "rgba(204,176,108,0.14)";
    ctx.beginPath();
    ctx.arc(0, -22 * scale, 18 * scale, -0.8, 0.4);
    ctx.stroke();
  }

  function drawTargetFoundation(ctx, x, y, kind) {
    const m = state.battle.metrics;
    const gold = kind === "core" ? "#ffd37a" : "#9edcff";
    drawGroundGlow(ctx, x, y, gold, kind === "core" ? 0.2 : 0.14, kind === "core" ? 72 : 52);
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,0.38)";
    ctx.beginPath();
    ctx.ellipse(x, y + m.tileH * 0.1, m.tileW * 0.36, m.tileH * 0.32, 0, 0, Math.PI * 2);
    ctx.fill();
    const base = ctx.createLinearGradient(x, y - m.tileH * 0.24, x, y + m.tileH * 0.24);
    base.addColorStop(0, "rgba(151,128,82,0.66)");
    base.addColorStop(1, "rgba(42,39,31,0.88)");
    ctx.fillStyle = base;
    ctx.beginPath();
    ctx.ellipse(x, y, m.tileW * 0.31, m.tileH * 0.3, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = kind === "core" ? "rgba(255,225,161,0.46)" : "rgba(158,220,255,0.32)";
    ctx.lineWidth = Math.max(1.4, m.tileW * 0.015);
    ctx.beginPath();
    ctx.ellipse(x, y, m.tileW * 0.31, m.tileH * 0.3, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  function drawSpawnMarkers(ctx) {
    const battle = state.battle;
    const spawns = (battle.mapPackage || {}).spawn_points || [];
    ctx.save();
    spawns.forEach((spawn, index) => {
      if (!spawn.position) return;
      const p = projectCell(spawn.position.x, spawn.position.y);
      drawSpawnRift(ctx, p.x, p.y, index);
    });
    ctx.restore();
  }

  function drawSpawnRift(ctx, x, y, index) {
    const m = state.battle.metrics;
    const phase = (state.battle.elapsedMs || 0) / 900 + index * 1.7;
    drawGroundGlow(ctx, x, y, "#8f7cff", 0.16, Math.max(58, m.tileW * 0.58));
    ctx.save();
    ctx.fillStyle = "rgba(15,10,24,0.72)";
    ctx.beginPath();
    ctx.ellipse(x, y + m.tileH * 0.04, m.tileW * 0.28, m.tileH * 0.2, -0.08, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(187,166,255,0.36)";
    ctx.lineWidth = Math.max(1.4, m.tileW * 0.013);
    ctx.beginPath();
    ctx.ellipse(x, y, m.tileW * 0.31, m.tileH * 0.24, -0.08, 0, Math.PI * 2);
    ctx.stroke();

    ctx.lineCap = "round";
    for (let i = 0; i < 6; i += 1) {
      const t = i / 5;
      const drift = Math.sin(phase + i * 1.3) * m.tileW * 0.08;
      const startX = x + (t - 0.5) * m.tileW * 0.38;
      const startY = y - m.tileH * (0.08 + t * 0.08);
      ctx.strokeStyle = `rgba(190,177,255,${0.18 - t * 0.018})`;
      ctx.lineWidth = Math.max(2, m.tileW * (0.016 + t * 0.006));
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.bezierCurveTo(
        startX + drift,
        startY - m.tileH * 0.48,
        startX - drift * 0.7,
        startY - m.tileH * 0.78,
        startX + drift * 0.42,
        startY - m.tileH * 1.1,
      );
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawEntities(ctx) {
    const battle = state.battle;
    const sorted = [...battle.enemies].sort((a, b) => projectCell(a.x, a.y).y - projectCell(b.x, b.y).y);
    for (const enemy of sorted) {
      const p = projectCell(enemy.x, enemy.y);
      drawGroundGlow(ctx, p.x, p.y, enemy.slowUntil > battle.elapsedMs ? "#9edcff" : "#352044", 0.26, 30);
      const assetId = enemy.type === "shadow_tide_shade" ? "enemy_shadow_tide_shade" : "enemy_shadow_tide_runner";
      drawSprite(ctx, mediaSpriteRef(assetId, "unit_sprite", true), p.x, p.y, enemy.type === "shadow_tide_shade" ? 58 : 54, enemy.hitFlashUntil > battle.elapsedMs);
      drawHealth(ctx, p.x, p.y - 62, enemy.hp / enemy.maxHp);
    }
  }

  function drawEffects(ctx) {
    const effects = state.battle.effects;
    for (const effect of effects) {
      const p = projectCell(effect.x, effect.y);
      const ratio = clamp(effect.age / effect.duration, 0, 1);
      if (effect.type === "ring") {
        ctx.strokeStyle = alphaColor(effect.color, 1 - ratio);
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.ellipse(p.x, p.y, 18 + ratio * 60 * effect.scale, 8 + ratio * 26 * effect.scale, 0, 0, Math.PI * 2);
        ctx.stroke();
      } else if (effect.type === "aura") {
        drawGroundGlow(ctx, p.x, p.y, effect.color, 0.22 * (1 - ratio * 0.35), 64 * effect.scale);
      } else if (effect.type === "burst") {
        ctx.fillStyle = alphaColor(effect.color, 1 - ratio);
        for (let i = 0; i < 10; i += 1) {
          const a = (i / 10) * Math.PI * 2;
          ctx.beginPath();
          ctx.arc(p.x + Math.cos(a) * ratio * 34 * effect.scale, p.y + Math.sin(a) * ratio * 18 * effect.scale, 3, 0, Math.PI * 2);
          ctx.fill();
        }
      } else if (effect.type === "beam") {
        const p2 = projectCell(effect.x2, effect.y2);
        ctx.strokeStyle = alphaColor(effect.color, 1 - ratio);
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y - 28);
        ctx.lineTo(p2.x, p2.y - 28);
        ctx.stroke();
      } else if (effect.type === "text") {
        ctx.fillStyle = alphaColor(effect.color, 1 - ratio);
        ctx.font = "700 15px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(effect.text, p.x, p.y - 34 - ratio * 24);
      }
    }
  }

  function drawDragGhost(ctx) {
    const battle = state.battle;
    if (!battle.draggingTool || !battle.dragPointer || !battle.canvas) return;
    const rect = battle.canvas.getBoundingClientRect();
    const x = battle.dragPointer.x - rect.left;
    const y = battle.dragPointer.y - rect.top;
    if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;
    ctx.save();
    ctx.globalAlpha = battle.hoverCell ? 0.36 : 0.72;
    if (battle.draggingTool === "basic") {
      drawSprite(ctx, mediaSpriteRef("defense_basic_lantern_barricade", "defense_sprite", true), x, y + 28, 68);
    } else if (battle.draggingTool === "sample") {
      drawGroundGlow(ctx, x, y, "#9edcff", 0.42, 42);
      ctx.strokeStyle = "#9edcff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(x, y, 24, 10, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      drawGroundGlow(ctx, x, y, "#8fcf83", 0.32, 72);
    }
    ctx.restore();
  }

  function drawGroundGlow(ctx, x, y, color, alpha, radius) {
    ctx.save();
    ctx.globalAlpha = alpha;
    const grd = ctx.createRadialGradient(x, y, 3, x, y, radius);
    grd.addColorStop(0, color);
    grd.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grd;
    ctx.beginPath();
    ctx.ellipse(x, y, radius, radius * 0.45, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawSprite(ctx, spriteRef, x, y, size, flash = false) {
    const ref = typeof spriteRef === "string" ? { url: spriteRef, source: null } : spriteRef || {};
    const img = getImage(ref.url);
    const source = ref.source || null;
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,.32)";
    ctx.beginPath();
    ctx.ellipse(x, y + 4, size * 0.34, size * 0.13, 0, 0, Math.PI * 2);
    ctx.fill();
    if (img && img.complete && img.naturalWidth) {
      const sourceWidth = source ? source.width : img.naturalWidth;
      const sourceHeight = source ? source.height : img.naturalHeight;
      const ratio = sourceWidth / sourceHeight;
      const w = ratio >= 1 ? size : size * ratio;
      const h = ratio >= 1 ? size / ratio : size;
      ctx.globalAlpha = flash ? 0.62 : 1;
      if (source) {
        ctx.drawImage(img, source.x, source.y, source.width, source.height, x - w / 2, y - h, w, h);
      } else {
        ctx.drawImage(img, x - w / 2, y - h, w, h);
      }
      if (flash) {
        ctx.globalCompositeOperation = "screen";
        ctx.fillStyle = "rgba(255,255,255,.42)";
        ctx.fillRect(x - w / 2, y - h, w, h);
      }
    } else {
      ctx.fillStyle = flash ? "#fff1bf" : "#2a2631";
      ctx.strokeStyle = "#9edcff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(x, y - size * 0.45, size * 0.24, size * 0.42, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawHealth(ctx, x, y, ratio) {
    ctx.fillStyle = "rgba(0,0,0,.54)";
    ctx.fillRect(x - 18, y, 36, 5);
    ctx.fillStyle = ratio > 0.5 ? "#8fcf83" : ratio > 0.25 ? "#f0bd58" : "#ff6666";
    ctx.fillRect(x - 18, y, 36 * clamp(ratio, 0, 1), 5);
  }

  function alphaColor(hex, alpha) {
    const value = hex.replace("#", "");
    const r = parseInt(value.slice(0, 2), 16);
    const g = parseInt(value.slice(2, 4), 16);
    const b = parseInt(value.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${clamp(alpha, 0, 1)})`;
  }

  async function finishBattle(result) {
    const battle = state.battle;
    if (!battle || battle.finishing) return;
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
    let settlement = buildLocalSettlement(state.battleOutcome);
    if (isApiMode()) {
      try {
        const response = await apiPost(
          sessionApiPath(`/battles/${currentNodeId()}/results`),
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
    }
    state.settlement = settlement;
    saveProfile({ completedBattle: true });
    state.view = "settlement";
    render();
  }

  function buildLocalSettlement(outcome) {
    return {
      node_id: currentNodeId(),
      result: outcome.result,
      battle_summary:
        outcome.result === "victory"
          ? "节点守住，但信标天线受损。样品表现被记录下来。"
          : "节点灯火几乎熄灭，仍记录到样品在转角处产生了迟滞。",
      sample_performance: "折光绊索对高速影潮有效，但稳定性偏低，适合进入后续正式研发。",
      npc_feedback: "在场技师记录了迟滞场的偏移，建议把光幕干扰方向保留下来。",
      world_delta: {
        summary: "灰灯驿站状态改变，影潮压力略有回落，正式研发线索出现。",
      },
    };
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
    const settlement = state.settlement || buildLocalSettlement(state.battleOutcome || {});
    const outcome = state.battleOutcome || {};
    const isVictory = settlement.result !== "defeat";
    ROOT.innerHTML = `
      <main class="screen">
        ${screenHeader("战后结算", "战斗结果已经反映到局势变化与后续研发线索。", "灰灯驿站")}
        <section class="settlement-grid">
          <article class="settlement-card">
            <div class="result-banner">
              <h2>${isVictory ? "节点守住" : "节点濒危"}</h2>
              <p class="panel-text">${safeText(settlement.battle_summary || "")}</p>
            </div>
            <div class="event-list" style="margin-top:14px">
              <div class="event-item"><strong>核心耐久</strong><span>${safeText(outcome.protected_core_hp ?? "-")}</span></div>
              <div class="event-item"><strong>漏失数量</strong><span>${safeText(outcome.leaked_enemy_count ?? 0)}</span></div>
              <div class="event-item"><strong>样品表现</strong><span>${safeText(settlement.sample_performance || "")}</span></div>
              <div class="event-item"><strong>世界变化</strong><span>${safeText(((settlement.world_delta || {}).summary) || "驿站状态改变，新的研究线索出现。")}</span></div>
            </div>
            ${evidenceMarkup()}
          </article>
          <aside class="settlement-card">
            <div class="side-avatar">${imageTag(npcPortraitUrl("npc_workshop_mentor"), "临时工坊老师傅")}</div>
            <h2 class="panel-title">NPC 反馈</h2>
            <p class="panel-text">${safeText(settlement.npc_feedback || "")}</p>
            <div class="tag-row">
              <span class="tag">光幕干扰</span>
              <span class="tag">正式研发线索</span>
              <span class="tag">样品缺陷已暴露</span>
            </div>
            <div class="screen-actions" style="margin-top:16px">
              <button class="primary-button" data-action="return-map">返回大地图</button>
              <button class="ghost-button" data-action="restart-battle">重放战斗</button>
            </div>
          </aside>
        </section>
      </main>
    `;
  }

  function evidenceMarkup() {
    const evidence = state.evidence;
    if (!evidence) {
      return `
        <details class="evidence-drawer">
          <summary>留档片段</summary>
          <div class="log-lines">
            <span>方案：折光绊索</span>
            <span>试作：战场送达</span>
            <span>战斗：${safeText((state.battleOutcome || {}).result || "完成")}</span>
          </div>
        </details>
      `;
    }
    const proposal = evidence.proposal || {};
    const job = evidence.research_job || {};
    const battle = evidence.battle_result || {};
    return `
      <details class="evidence-drawer">
        <summary>留档片段</summary>
        <div class="log-lines">
          <span>方案：${safeText(proposal.display_name || "折光绊索")}</span>
          <span>试作：${safeText(job.status || "已完成")}</span>
          <span>战斗：${safeText(((battle.settlement || {}).result) || (state.battleOutcome || {}).result || "完成")}</span>
          <span>封存：${safeText(((evidence.audit_summary || {}).overall_status) || "通过")}</span>
        </div>
      </details>
    `;
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
    state.view = "map";
    render();
  }

  function handleAction(action, target) {
    const value = target.dataset.value;
    switch (action) {
      case "boot":
        boot();
        break;
      case "continue":
        state.view = state.profile.worldCreated ? "map" : "world-config";
        render();
        break;
      case "new-archive":
        startNewArchive();
        break;
      case "reset-demo":
        resetDemo();
        break;
      case "settings":
        renderError(state.dataMode === "api" ? "当前使用中枢档案。重置演示可重新开始。" : "当前使用本机档案。");
        break;
      case "select-creativity":
        state.selectedOptions.creativity_mode = value;
        saveProfile();
        renderWorldConfig();
        break;
      case "select-origin":
        state.selectedOptions.player_origin = value;
        saveProfile();
        renderWorldConfig();
        break;
      case "use-recommended":
        state.selectedOptions = { ...DEFAULT_WORLD_CONFIG.recommended_defaults };
        saveProfile();
        renderWorldConfig();
        break;
      case "begin-world":
        beginWorld();
        break;
      case "opening-next":
        state.openingIndex += 1;
        if (state.openingIndex >= ((state.data.opening || {}).segments || []).length) {
          state.view = "map";
        }
        render();
        break;
      case "opening-skip":
        state.view = "map";
        render();
        break;
      case "select-map-node":
        state.selectedMapNodeId = target.dataset.nodeId;
        renderMap();
        break;
      case "enter-node":
        enterCurrentNode();
        break;
      case "refresh-map":
        loadMap().finally(renderMap);
        break;
      case "proposal-refresh":
        refreshProposal();
        break;
      case "confirm-prototype":
        confirmPrototype();
        break;
      case "toggle-pause":
        if (state.battle) state.battle.paused = !state.battle.paused;
        break;
      case "cycle-speed":
        if (state.battle) state.battle.speed = state.battle.speed === 1 ? 2 : state.battle.speed === 2 ? 0.5 : 1;
        break;
      case "select-tool":
        if (state.battle) {
          state.battle.selectedTool = target.dataset.tool || "basic";
          updateBattleDom();
        }
        break;
      case "close-dialogue":
        closeDialogue();
        break;
      case "back-to-map":
        if (state.battle) {
          state.battle.paused = true;
          setBattleToast("战斗中只能查看当前态势");
          updateBattleDom();
        }
        break;
      case "return-map":
        returnToMap();
        break;
      case "restart-battle":
        state.battle = null;
        state.view = "battle";
        render();
        break;
      default:
        break;
    }
  }

  ROOT.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    event.preventDefault();
    handleAction(target.dataset.action, target);
  });

  ROOT.addEventListener("pointerdown", (event) => {
    const target = event.target.closest(".toolbar-card[data-tool]");
    if (!target || state.view !== "battle" || event.button !== 0) return;
    beginToolDrag(target.dataset.tool, event);
  });

  window.addEventListener("pointermove", updateToolDrag);
  window.addEventListener("pointerup", finishToolDrag);

  ROOT.addEventListener("input", (event) => {
    const target = event.target;
    if (target && target.dataset && target.dataset.field === "intent") {
      state.intentText = target.value;
    }
  });

  boot();
})();
