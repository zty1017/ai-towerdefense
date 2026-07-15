const WORLD_TONES = {
  xianxia_cloud_frontier: {
    matrix: "1.02 0.04 0 0 0.01  0.01 1.10 0.03 0 0.03  0 0.08 1.02 0 0.04  0 0 0 1 0",
    veil: "rgba(76,184,158,.10)",
  },
  stonewind_border_march: {
    matrix: "1.08 0.04 0 0 0.03  0.02 0.96 0 0 0.01  0 0.01 0.82 0 0  0 0 0 1 0",
    veil: "rgba(174,126,63,.12)",
  },
  stellar_anchor: {
    matrix: "0.78 0.05 0.08 0 0.01  0 0.98 0.08 0 0.03  0.04 0.10 1.22 0 0.08  0 0 0 1 0",
    veil: "rgba(39,126,176,.13)",
  },
};

const WORLD_BACKDROPS = {
  xianxia_cloud_frontier: "/assets/map_visual_reference/strategic_xianxia_cloud_frontier.v0.1.jpg",
  stonewind_border_march: "/assets/map_visual_reference/strategic_stonewind_border_march.v0.1.jpg",
  stellar_anchor: "/assets/map_visual_reference/strategic_stellar_anchor.v0.1.jpg",
};

function worldTone(worldbookId) {
  return WORLD_TONES[worldbookId] || {
    matrix: "1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0",
    veil: "rgba(0,0,0,0)",
  };
}

export function createStrategicMapFeatureController({
  root,
  projection,
  camera,
  runtime,
  presentation,
} = {}) {
  if (!root || !projection || !camera || !runtime || !presentation) {
    throw new TypeError("createStrategicMapFeatureController requires root, projection, camera, runtime, and presentation");
  }

  function renderMap() {
    const snapshot = projection.snapshot();
    const { map, nodes, selected, objectives, participants, badges } = snapshot;
    const byId = new Map(nodes.map((node) => [node.stable_internal_id, node]));
    const activeCamera = camera.set(camera.active(map), {
      mode: camera.mode() === "manual" ? "manual" : "auto",
    });
    const zoomPercent = Math.round(activeCamera.zoom * 100);
    const syncStatus = runtime.mapSyncStatus ? runtime.mapSyncStatus() : "idle";
    const tone = worldTone(map.worldbook_id || map.worldbook_template_id);
    const lines = (map.supply_lines || [])
      .map((line) => {
        const from = byId.get(line.from_node_id);
        const to = byId.get(line.to_node_id);
        if (!from || !to || !projection.mapNodeVisible(from) || !projection.mapNodeVisible(to)) return "";
        const path = presentation.routePath(from.position, to.position);
        return `
          <path d="${path}" class="map-supply-shadow" />
          <path d="${path}" class="map-supply-line" />
          <path d="${path}" class="map-supply-glint" />
          <path d="${path}" class="map-supply-dots" />
        `;
      })
      .join("");
    const dark = (map.dark_regions || []).map(presentation.darkRegionMarkup).join("");
    const threats = (map.threat_edges || []).map(presentation.threatEdgeMarkup).join("");
    presentation.markerPreloadUrls().forEach((url) => presentation.getImage(url));
    const worldbookId = map.worldbook_id || map.worldbook_template_id;
    const backdropUrl = presentation.assetUrl(
      WORLD_BACKDROPS[worldbookId] || "/assets/map_visual_reference/strategic_region_map_clean_v0_1.png",
    );
    const terrain = `
      <defs>
        <radialGradient id="strategicFocusGlow" cx="35%" cy="52%" r="40%">
          <stop offset="0" stop-color="rgba(255,210,124,.24)" />
          <stop offset=".48" stop-color="rgba(240,189,88,.06)" />
          <stop offset="1" stop-color="rgba(240,189,88,0)" />
        </radialGradient>
        <radialGradient id="strategicColdFog" cx="82%" cy="78%" r="42%">
          <stop offset="0" stop-color="rgba(88,108,150,.30)" />
          <stop offset=".46" stop-color="rgba(54,68,104,.18)" />
          <stop offset="1" stop-color="rgba(18,20,30,0)" />
        </radialGradient>
        <linearGradient id="strategicVignette" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="rgba(0,0,0,.42)" />
          <stop offset=".52" stop-color="rgba(0,0,0,0)" />
          <stop offset="1" stop-color="rgba(0,0,0,.48)" />
        </linearGradient>
        <filter id="strategicSoftGlow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="8" /></filter>
        <filter id="strategicRegionBlur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="22" /></filter>
        <filter id="strategicThreatBlur" x="-35%" y="-45%" width="170%" height="190%"><feGaussianBlur stdDeviation="10" /></filter>
        <filter id="strategicWorldTone" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="${tone.matrix}" /></filter>
      </defs>
      <rect x="0" y="0" width="1280" height="720" fill="#060908" />
      <image href="${presentation.safeText(backdropUrl)}" x="0" y="0" width="1280" height="720" preserveAspectRatio="xMidYMid slice" class="strategic-map-backdrop" filter="url(#strategicWorldTone)" />
      <rect x="0" y="0" width="1280" height="720" fill="${tone.veil}" />
      <rect x="0" y="0" width="1280" height="720" fill="url(#strategicVignette)" />
      <ellipse cx="410" cy="380" rx="330" ry="225" fill="url(#strategicFocusGlow)" />
      <ellipse cx="1080" cy="600" rx="310" ry="190" fill="url(#strategicColdFog)" />
    `;
    const nodeMarkup = nodes
      .filter(projection.mapNodeVisible)
      .map((node) => {
        const stateName = projection.nodeState(node);
        const color = presentation.nodeColor(node.kind, stateName);
        const radius = node.kind === "main_city" ? 38 : node.kind === "battle_hotspot" ? 34 : 28;
        const pulse = node.stable_internal_id === runtime.currentNodeId()
          ? `<circle class="map-node-pulse" cx="${node.position.x}" cy="${node.position.y}" r="${radius + 4}" fill="none" stroke="${color}"><animate attributeName="r" values="${radius};${radius + 18};${radius}" dur="1.8s" repeatCount="indefinite" /></circle>`
          : "";
        return `
          <g class="map-node map-node--${presentation.safeText(node.kind || "node")}" data-action="select-map-node" data-node-id="${presentation.safeText(node.stable_internal_id)}">
            <circle class="map-node-hit" cx="${node.position.x}" cy="${node.position.y}" r="${radius + 18}" />
            ${pulse}
            <circle cx="${node.position.x}" cy="${node.position.y}" r="${radius + 8}" fill="${color}" opacity=".08" filter="url(#strategicSoftGlow)" />
            ${presentation.nodeMarkerMarkup(node, color, stateName)}
            ${presentation.nodeLabel(node, color)}
          </g>
        `;
      })
      .join("");
    root.innerHTML = `
      <main class="screen map-screen">
        ${presentation.screenHeader(map.display_name || "余灯中枢态势图", map.summary || "", "战略态势")}
        <section class="map-layout"><div class="strategic-map-stage">
          <div class="strategic-map" aria-label="${presentation.safeText(map.display_name || "态势图")}">
            <svg data-map-camera-svg viewBox="${camera.viewBox(activeCamera)}" role="img">${terrain}${dark}${lines}${threats}${nodeMarkup}</svg>
          </div>
          <div class="map-camera-controls" aria-label="地图视野控制">
            <button class="map-camera-button" data-action="map-zoom-out" title="缩小" aria-label="缩小" ${activeCamera.zoom <= camera.minZoom + 0.01 ? "disabled" : ""}>-</button>
            <span class="map-camera-readout" data-map-camera-readout>${zoomPercent}%</span>
            <button class="map-camera-button" data-action="map-zoom-in" title="放大" aria-label="放大" ${activeCamera.zoom >= camera.maxZoom - 0.01 ? "disabled" : ""}>+</button>
            <button class="map-camera-button map-camera-button--reset" data-action="map-camera-reset" title="复位" aria-label="复位">复位</button>
          </div>
          <aside class="panel map-overlay map-overlay--objectives">
            <h2 class="panel-title">当前目标</h2>
            <div class="event-list">${objectives.map((item) => `<div class="event-item"><strong>${presentation.safeText(item.title)}</strong><span>${presentation.safeText(item.summary)}</span></div>`).join("")}</div>
          </aside>
          <aside class="panel map-overlay map-overlay--node">
            <h2 class="panel-title">${presentation.safeText(selected ? selected.display_name : "节点")}</h2>
            <p class="panel-text">${presentation.safeText(selected ? selected.summary : "")}</p>
            <div class="tag-row">
              <span class="tag">${presentation.safeText(selected ? selected.kind : "node")}</span>
              <span class="tag">${presentation.safeText(selected ? projection.nodeState(selected) : "")}</span>
              ${badges.map((badge) => `<span class="tag" data-tone="${presentation.safeText(badge.tone)}">${presentation.safeText(badge.label)}</span>`).join("")}
            </div>
            <div class="screen-actions">
              <button class="primary-button" data-action="enter-node" ${selected && runtime.isCurrentNode(selected.stable_internal_id) && runtime.nodePlayable(selected.stable_internal_id) ? "" : "disabled"}>进入当前节点</button>
              <button class="ghost-button" data-action="refresh-map" ${syncStatus === "loading" ? "disabled" : ""}>${syncStatus === "loading" ? "同步中..." : "刷新态势"}</button>
            </div>
            ${syncStatus === "success" ? `<div class="map-sync-feedback" role="status">态势已同步</div>` : ""}
            ${runtime.routeNext() ? `<div class="event-list map-next-list"><div class="event-item"><strong>下一处</strong><span>${presentation.safeText(runtime.routeNext().display_name || "前方节点")}</span></div></div>` : ""}
            ${participants.length ? `<div class="event-list map-next-list">${participants.map((npc) => `<div class="event-item"><strong>${presentation.safeText(npc.title)}</strong><span>${presentation.safeText(npc.summary)}</span></div>`).join("")}</div>` : ""}
            ${!runtime.routeCurrent() ? `<div class="event-list map-next-list"><div class="event-item"><strong>本章完成</strong><span>三处防线均已完成演示，新的北路分潮线留作后续版本。</span></div></div>` : ""}
          </aside>
        </div></section>
      </main>
    `;
  }

  return { renderMap };
}
