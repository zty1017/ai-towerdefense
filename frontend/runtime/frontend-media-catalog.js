import { manifestItems } from "./media-resolver.js";

function defaultClock() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function defaultCreateImage() {
  return new Image();
}

export function createFrontendMediaCatalog({
  getData,
  getBattle = () => null,
  getMapRuntimePackage = () => ({}),
  getCurrentNodeId = () => "",
  resolveAssetUrl,
  clock = defaultClock,
  createImage = defaultCreateImage,
  fallbackNodeId = "",
} = {}) {
  const dependencies = { getData, getBattle, getMapRuntimePackage, getCurrentNodeId, resolveAssetUrl, clock, createImage };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createFrontendMediaCatalog requires ${name}`);
    }
  }
  const images = new Map();

  function data() {
    return getData() || {};
  }

  function assetUrl(url) {
    if (!url) return "";
    if (/^https?:\/\//.test(url)) return url;
    return resolveAssetUrl(url);
  }

  function mediaItem(assetId, role, runtime = false) {
    const manifest = runtime ? data().runtimeMediaManifest : data().mediaManifest;
    return manifestItems(manifest).find(
      (item) =>
        (item.asset_id === assetId || item.source_game_id === assetId) &&
        item.media_role === role,
    );
  }

  function atlasItems(runtime = false) {
    const manifest = runtime ? data().runtimeArtAtlasManifest : data().mediaAtlasManifest;
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
    const battle = getBattle();
    if (battle && Number.isFinite(battle.elapsedMs)) return battle.elapsedMs;
    return clock();
  }

  function atlasFrameIndex(item) {
    const frames = Array.isArray(item && item.frames) ? item.frames : [];
    if (frames.length <= 1) return 0;
    const playback = item.playback || {};
    const fps = Number(playback.fps) > 0 ? Number(playback.fps) : 6;
    const rawIndex = Math.floor(atlasClockMs() / (1000 / fps));
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
    return frame.url ? { url: assetUrl(frame.url), source: null } : null;
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

  function mediaUrl(assetId, role, runtime = false) {
    const frameUrl = atlasFrameUrl(assetId, role, runtime);
    if (frameUrl) return frameUrl;
    const item = mediaItem(assetId, role, runtime);
    return item ? assetUrl(item.url) : "";
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

  function battleObjectMediaCandidates(object = {}) {
    const objectId = object.objectId || object.object_id || object.runtimeToolId || object.id || "";
    const assetKind = object.assetKind || object.asset_kind || "";
    const ids = [objectId];
    if (objectId === "basic_lantern_tower_001") ids.push("defense_basic_lantern_barricade");
    const roles = String(assetKind).includes("trap") || String(assetKind).includes("device")
      ? ["trap_sprite", "item_sprite", "tower_sprite", "defense_sprite"]
      : ["tower_sprite", "defense_sprite"];
    return { ids: [...new Set(ids.filter(Boolean))], roles };
  }

  function battleObjectSpriteRef(object = {}) {
    const direct = object.mediaRefs || object.media_refs || {};
    const directSprite = direct.sprite || {};
    const directIcon = direct.icon || {};
    const directUrl = directSprite.image || directIcon.url || "";
    if (directUrl) return { url: assetUrl(directUrl), source: null };
    const candidates = battleObjectMediaCandidates(object);
    for (const assetId of candidates.ids) {
      for (const role of candidates.roles) {
        const compiledRef = mediaSpriteRef(assetId, role, false);
        if (compiledRef) return compiledRef;
        const runtimeRef = mediaSpriteRef(assetId, role, true);
        if (runtimeRef) return runtimeRef;
      }
    }
    return null;
  }

  function battleObjectPreloadUrls(objects = []) {
    const urls = [];
    for (const object of objects) {
      const direct = (object && (object.mediaRefs || object.media_refs)) || {};
      if (direct.sprite && direct.sprite.image) urls.push(assetUrl(direct.sprite.image));
      if (direct.icon && direct.icon.url) urls.push(assetUrl(direct.icon.url));
      const candidates = battleObjectMediaCandidates(object);
      for (const assetId of candidates.ids) {
        for (const role of candidates.roles) {
          urls.push(...mediaPreloadUrls(assetId, role, false));
          urls.push(...mediaPreloadUrls(assetId, role, true));
        }
      }
    }
    return [...new Set(urls.filter(Boolean))];
  }

  function playerReadyMapLayer(entry) {
    return Boolean(
      entry &&
      entry.authority === "published_visual_layer" &&
      entry.player_visible_quality === "passed",
    );
  }

  function mapVisualUrl(role, options = {}) {
    const playerOnly = Boolean(options.playerOnly);
    const packageLayer = (getMapRuntimePackage().visual_layers || []).find(
      (entry) => entry.role === role && (!playerOnly || playerReadyMapLayer(entry)),
    );
    if (packageLayer && packageLayer.url) return assetUrl(packageLayer.url);
    const item = manifestItems(data().mapVisualManifest).find(
      (entry) => entry.role === role && (!playerOnly || playerReadyMapLayer(entry)),
    );
    return item ? assetUrl(item.url) : "";
  }

  function activeNodeId() {
    return String(getMapRuntimePackage().node_id || getCurrentNodeId() || fallbackNodeId);
  }

  function mapComponentItems(role) {
    return manifestItems(data().mapComponentManifest || {}).filter(
      (item) =>
        item &&
        item.component_role === role &&
        (!item.node_id || item.node_id === activeNodeId()) &&
        item.url,
    );
  }

  function mapComponentItem(role, variant = 0) {
    const items = mapComponentItems(role);
    return items.length ? items[Math.abs(variant) % items.length] : null;
  }

  function mapComponentUrl(role, variant = 0) {
    const item = mapComponentItem(role, variant);
    return item && item.url ? assetUrl(item.url) : "";
  }

  function mapComponentImage(role, variant = 0) {
    const url = mapComponentUrl(role, variant);
    return url ? getImage(url) : null;
  }

  function mapComponentPreloadUrls() {
    return manifestItems(data().mapComponentManifest || {})
      .filter((item) => item && (!item.node_id || item.node_id === activeNodeId()) && item.url)
      .map((item) => assetUrl(item.url));
  }

  function strategicMarkerManifest() {
    return data().strategicMapMarkerManifest || {};
  }

  function strategicMarkerAtlas() {
    const atlas = strategicMarkerManifest().atlas;
    return atlas && atlas.url ? { ...atlas, url: assetUrl(atlas.url) } : null;
  }

  function strategicMarkerItem(kind, stateName) {
    const items = manifestItems(strategicMarkerManifest()).filter(
      (item) => item && item.media_role === "strategic_node_marker",
    );
    return (
      items.find((item) => item.node_kind === kind && item.state_hint === stateName) ||
      items.find((item) => item.node_kind === kind) ||
      items.find((item) => item.node_kind === "generic") ||
      null
    );
  }

  function strategicMarkerPreloadUrls() {
    const atlas = strategicMarkerAtlas();
    return atlas && atlas.url ? [atlas.url] : [];
  }

  function layeredMapVisualPackage() {
    return data().layeredMapVisualPackage || {};
  }

  function playerReadyLayeredMapLayer(entry) {
    const quality = (entry && entry.quality) || {};
    return Boolean(
      entry &&
      entry.player_default === true &&
      quality.gate_status === "passed" &&
      quality.alignment_status === "passed" &&
      quality.player_visible_quality === "passed",
    );
  }

  function layeredMapVisualLayer(role = "composited") {
    const layers = layeredMapVisualPackage().layers;
    if (!Array.isArray(layers)) return null;
    return layers.find(
      (entry) => entry && entry.role === role && playerReadyLayeredMapLayer(entry),
    ) || null;
  }

  function layeredMapVisualUrl(role = "composited") {
    const layer = layeredMapVisualLayer(role);
    return layer && layer.url ? assetUrl(layer.url) : "";
  }

  function layeredMapBackdropImage() {
    const url = layeredMapVisualUrl("composited");
    return url ? getImage(url) : null;
  }

  function layeredMapVisualPreloadUrls() {
    const layers = layeredMapVisualPackage().layers;
    if (!Array.isArray(layers)) return [];
    return layers
      .filter((entry) => entry && entry.role === "composited" && playerReadyLayeredMapLayer(entry))
      .map((entry) => assetUrl(entry.url))
      .filter(Boolean);
  }

  function getImage(url) {
    const resolved = assetUrl(url);
    if (!resolved) return null;
    if (images.has(resolved)) return images.get(resolved);
    const image = createImage();
    image.decoding = "async";
    image.src = resolved;
    images.set(resolved, image);
    return image;
  }

  return {
    assetUrl,
    atlasFrameIndex,
    battleObjectMediaCandidates,
    battleObjectPreloadUrls,
    battleObjectSpriteRef,
    getImage,
    layeredMapBackdropImage,
    layeredMapVisualLayer,
    layeredMapVisualPreloadUrls,
    layeredMapVisualUrl,
    mapComponentImage,
    mapComponentItem,
    mapComponentItems,
    mapComponentPreloadUrls,
    mapComponentUrl,
    mapVisualUrl,
    mediaItem,
    mediaPreloadUrls,
    mediaSpriteRef,
    mediaUrl,
    playerReadyLayeredMapLayer,
    playerReadyMapLayer,
    strategicMarkerAtlas,
    strategicMarkerItem,
    strategicMarkerPreloadUrls,
  };
}
