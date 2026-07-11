export const STRATEGIC_MAP_WIDTH = 1280;
export const STRATEGIC_MAP_HEIGHT = 720;
export const STRATEGIC_MAP_MIN_ZOOM = 1;
export const STRATEGIC_MAP_MAX_ZOOM = 2.8;

const CAMERA_NODE_KINDS = new Set([
  "main_city",
  "battle_hotspot",
  "research_facility",
  "resource_storage",
]);

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function normalizeStrategicMapCamera(camera = {}) {
  const zoom = clamp(
    Number(camera.zoom) || 1,
    STRATEGIC_MAP_MIN_ZOOM,
    STRATEGIC_MAP_MAX_ZOOM,
  );
  const width = STRATEGIC_MAP_WIDTH / zoom;
  const height = STRATEGIC_MAP_HEIGHT / zoom;
  const minX = width / 2;
  const maxX = STRATEGIC_MAP_WIDTH - width / 2;
  const minY = height / 2;
  const maxY = STRATEGIC_MAP_HEIGHT - height / 2;
  const centerX = clamp(Number(camera.centerX) || STRATEGIC_MAP_WIDTH / 2, minX, maxX);
  const centerY = clamp(Number(camera.centerY) || STRATEGIC_MAP_HEIGHT / 2, minY, maxY);
  return {
    zoom,
    centerX,
    centerY,
    x: centerX - width / 2,
    y: centerY - height / 2,
    width,
    height,
  };
}

export function strategicMapCameraViewBox(camera = normalizeStrategicMapCamera()) {
  return `${camera.x.toFixed(2)} ${camera.y.toFixed(2)} ${camera.width.toFixed(2)} ${camera.height.toFixed(2)}`;
}

export function fitStrategicMapCamera(map = {}, isNodeVisible = () => true) {
  const nodes = (map.nodes || [])
    .filter((node) => node && node.position && isNodeVisible(node))
    .filter((node) => CAMERA_NODE_KINDS.has(node.kind || ""));
  if (!nodes.length) {
    return normalizeStrategicMapCamera({
      zoom: 1,
      centerX: STRATEGIC_MAP_WIDTH / 2,
      centerY: STRATEGIC_MAP_HEIGHT / 2,
    });
  }
  const xs = nodes.map((node) => Number(node.position.x) || STRATEGIC_MAP_WIDTH / 2);
  const ys = nodes.map((node) => Number(node.position.y) || STRATEGIC_MAP_HEIGHT / 2);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const desiredWidth = clamp(maxX - minX + 520, 920, STRATEGIC_MAP_WIDTH);
  const desiredHeight = clamp(maxY - minY + 360, 480, STRATEGIC_MAP_HEIGHT);
  return normalizeStrategicMapCamera({
    zoom: clamp(
      Math.min(STRATEGIC_MAP_WIDTH / desiredWidth, STRATEGIC_MAP_HEIGHT / desiredHeight),
      STRATEGIC_MAP_MIN_ZOOM,
      1.32,
    ),
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
  });
}

export function createStrategicMapController({
  state,
  root,
  getMapData = () => ({}),
  isNodeVisible = () => true,
} = {}) {
  if (!state || typeof state !== "object") {
    throw new TypeError("createStrategicMapController requires mutable state");
  }
  if (!root || typeof root.querySelector !== "function") {
    throw new TypeError("createStrategicMapController requires a root element");
  }

  function strategicMapDefaultCamera(map = getMapData()) {
    return fitStrategicMapCamera(map, isNodeVisible);
  }

  function normalizedStrategicMapCamera(camera = state.mapCamera || {}) {
    return normalizeStrategicMapCamera(camera);
  }

  function activeStrategicMapCamera(map = getMapData()) {
    if (state.mapCameraMode === "manual") {
      return normalizedStrategicMapCamera(state.mapCamera);
    }
    return strategicMapDefaultCamera(map);
  }

  function setStrategicMapCamera(camera, options = {}) {
    const next = normalizedStrategicMapCamera(camera);
    state.mapCamera = {
      zoom: next.zoom,
      centerX: next.centerX,
      centerY: next.centerY,
    };
    if (options.mode) state.mapCameraMode = options.mode;
    return next;
  }

  function strategicMapViewBox(camera = normalizedStrategicMapCamera()) {
    return strategicMapCameraViewBox(camera);
  }

  function applyStrategicMapCameraToDom() {
    if (state.view !== "map") return;
    const camera = setStrategicMapCamera(
      state.mapCameraMode === "manual" ? state.mapCamera : strategicMapDefaultCamera(),
      { mode: state.mapCameraMode === "manual" ? "manual" : "auto" },
    );
    const svg = root.querySelector("[data-map-camera-svg]");
    if (svg) svg.setAttribute("viewBox", strategicMapViewBox(camera));
    const readout = root.querySelector("[data-map-camera-readout]");
    if (readout) readout.textContent = `${Math.round(camera.zoom * 100)}%`;
    const zoomOut = root.querySelector("[data-action='map-zoom-out']");
    const zoomIn = root.querySelector("[data-action='map-zoom-in']");
    if (zoomOut) zoomOut.disabled = camera.zoom <= STRATEGIC_MAP_MIN_ZOOM + 0.01;
    if (zoomIn) zoomIn.disabled = camera.zoom >= STRATEGIC_MAP_MAX_ZOOM - 0.01;
  }

  function zoomStrategicMapTo(nextZoom, anchor = null) {
    const current = activeStrategicMapCamera();
    const zoom = clamp(nextZoom, STRATEGIC_MAP_MIN_ZOOM, STRATEGIC_MAP_MAX_ZOOM);
    if (!anchor) {
      setStrategicMapCamera({ ...current, zoom }, { mode: "manual" });
      applyStrategicMapCameraToDom();
      return;
    }
    const width = STRATEGIC_MAP_WIDTH / zoom;
    const height = STRATEGIC_MAP_HEIGHT / zoom;
    const x = anchor.mapX - anchor.rx * width;
    const y = anchor.mapY - anchor.ry * height;
    setStrategicMapCamera(
      {
        zoom,
        centerX: x + width / 2,
        centerY: y + height / 2,
      },
      { mode: "manual" },
    );
    applyStrategicMapCameraToDom();
  }

  function zoomStrategicMapBy(factor) {
    const current = activeStrategicMapCamera();
    zoomStrategicMapTo(current.zoom * factor);
  }

  function resetStrategicMapCamera() {
    setStrategicMapCamera(strategicMapDefaultCamera(), { mode: "auto" });
    applyStrategicMapCameraToDom();
  }

  function strategicMapAnchorFromPointer(event, mapEl) {
    const rect = mapEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const camera = setStrategicMapCamera(activeStrategicMapCamera(getMapData()), {
      mode: state.mapCameraMode === "manual" ? "manual" : "auto",
    });
    const rx = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    const ry = clamp((event.clientY - rect.top) / rect.height, 0, 1);
    return {
      rx,
      ry,
      mapX: camera.x + rx * camera.width,
      mapY: camera.y + ry * camera.height,
    };
  }

  function handleStrategicMapWheel(event) {
    if (state.view !== "map") return false;
    const mapEl = event.target.closest(".strategic-map");
    if (!mapEl || event.target.closest(".map-overlay")) return false;
    const anchor = strategicMapAnchorFromPointer(event, mapEl);
    const camera = normalizedStrategicMapCamera();
    const factor = event.deltaY < 0 ? 1.16 : 1 / 1.16;
    zoomStrategicMapTo(camera.zoom * factor, anchor);
    return true;
  }

  function beginStrategicMapDrag(event) {
    if (state.view !== "map" || event.button !== 0) return;
    const mapEl = event.target.closest(".strategic-map");
    if (!mapEl || event.target.closest(".map-overlay")) return;
    if (event.target.closest("[data-action]")) return;
    const rect = mapEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const camera = setStrategicMapCamera(activeStrategicMapCamera(getMapData()), {
      mode: state.mapCameraMode === "manual" ? "manual" : "auto",
    });
    state.mapDrag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      camera,
      rect: { width: rect.width, height: rect.height },
      moved: false,
    };
    mapEl.classList.add("is-dragging");
    if (mapEl.setPointerCapture) {
      try {
        mapEl.setPointerCapture(event.pointerId);
      } catch {
        // Window listeners still track the drag when pointer capture is unavailable.
      }
    }
    event.preventDefault();
  }

  function updateStrategicMapDrag(event) {
    const drag = state.mapDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (Math.hypot(dx, dy) > 3) drag.moved = true;
    setStrategicMapCamera(
      {
        zoom: drag.camera.zoom,
        centerX: drag.camera.centerX - (dx / drag.rect.width) * drag.camera.width,
        centerY: drag.camera.centerY - (dy / drag.rect.height) * drag.camera.height,
      },
      { mode: "manual" },
    );
    applyStrategicMapCameraToDom();
    event.preventDefault();
  }

  function finishStrategicMapDrag(event) {
    const drag = state.mapDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const mapEl = root.querySelector(".strategic-map");
    if (mapEl) {
      mapEl.classList.remove("is-dragging");
      if (mapEl.releasePointerCapture) {
        try {
          mapEl.releasePointerCapture(event.pointerId);
        } catch {
          // The pointer may already have been released outside the map.
        }
      }
    }
    if (drag.moved) state.suppressMapClick = true;
    state.mapDrag = null;
  }

  return {
    activeStrategicMapCamera,
    applyStrategicMapCameraToDom,
    beginStrategicMapDrag,
    finishStrategicMapDrag,
    handleStrategicMapWheel,
    normalizedStrategicMapCamera,
    resetStrategicMapCamera,
    setStrategicMapCamera,
    strategicMapAnchorFromPointer,
    strategicMapDefaultCamera,
    strategicMapViewBox,
    updateStrategicMapDrag,
    zoomStrategicMapBy,
    zoomStrategicMapTo,
  };
}
