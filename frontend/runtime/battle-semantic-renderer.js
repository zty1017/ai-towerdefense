function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function createBattleSemanticRenderer({
  getBattle,
  getResourceNodes,
  getHazardZones,
  getDefenseAnchors,
  getBlockedAreas,
  getVisualProfile,
  getRoutes,
  projectCell,
  routeSamplesBetween,
  routeRoadWidthCells,
  traceRoutePath,
  drawGroundGlow,
  drawComponentTextureEllipse,
  drawCollapsedWall,
  hashString,
  isCellInGrid,
} = {}) {
  const dependencies = {
    getBattle,
    getResourceNodes,
    getHazardZones,
    getDefenseAnchors,
    getBlockedAreas,
    getVisualProfile,
    getRoutes,
    projectCell,
    routeSamplesBetween,
    routeRoadWidthCells,
    traceRoutePath,
    drawGroundGlow,
    drawComponentTextureEllipse,
    drawCollapsedWall,
    hashString,
    isCellInGrid,
  };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleSemanticRenderer requires ${name}`);
    }
  }

  function drawMapResourceNodes(ctx) {
    const battle = getBattle();
    const nodes = getResourceNodes();
    if (!battle || !battle.metrics || !nodes.length) return;
    const metrics = battle.metrics;
    const color = (getVisualProfile().objective || {}).optional || "#9edcff";
    ctx.save();
    for (const node of nodes) {
      if (!node.position) continue;
      const point = projectCell(node.position.x, node.position.y);
      const footprint = node.footprint || {};
      const radiusX = metrics.tileW * (0.28 + Math.max(0, Number(footprint.width_cells || 1) - 1) * 0.08);
      const radiusY = metrics.tileH * (0.24 + Math.max(0, Number(footprint.height_cells || 1) - 1) * 0.08);
      drawGroundGlow(ctx, point.x, point.y, color, 0.2, Math.max(42, metrics.tileW * 0.38));
      ctx.fillStyle = "rgba(8,17,19,0.42)";
      ctx.beginPath();
      ctx.ellipse(point.x, point.y + metrics.tileH * 0.1, radiusX * 1.22, radiusY * 0.72, 0, 0, Math.PI * 2);
      ctx.fill();
      drawComponentTextureEllipse(
        ctx,
        "resource_marker",
        point.x,
        point.y - metrics.tileH * 0.03,
        radiusX * 2.15,
        radiusY * 1.92,
        {
          variant: hashString(node.node_id || node.resource_id || `${node.position.x},${node.position.y}`),
          rotation: -0.04,
          alpha: 0.26,
          composite: "soft-light",
        },
      );
      ctx.strokeStyle = "rgba(158,220,255,0.38)";
      ctx.lineWidth = Math.max(1.4, metrics.tileW * 0.014);
      ctx.beginPath();
      ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = "rgba(158,220,255,0.22)";
      ctx.beginPath();
      ctx.ellipse(point.x, point.y - metrics.tileH * 0.05, radiusX * 0.58, radiusY * 0.42, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "rgba(218,247,255,0.68)";
      for (let index = 0; index < 5; index += 1) {
        const angle = (index / 5) * Math.PI * 2;
        const shardX = point.x + Math.cos(angle) * radiusX * 0.32;
        const shardY = point.y + Math.sin(angle) * radiusY * 0.28;
        ctx.beginPath();
        ctx.moveTo(shardX, shardY - metrics.tileH * 0.2);
        ctx.lineTo(shardX + metrics.tileW * 0.06, shardY);
        ctx.lineTo(shardX - metrics.tileW * 0.05, shardY + metrics.tileH * 0.03);
        ctx.closePath();
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawMapHazardZones(ctx) {
    const battle = getBattle();
    const zones = getHazardZones();
    if (!battle || !battle.metrics || !zones.length) return;
    const metrics = battle.metrics;
    const hazardColor = (getVisualProfile().road || {}).shadow || "rgba(18,13,10,0.54)";
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const zone of zones) {
      const route = getRoutes().find((item) => item.route_id === zone.anchor_route_id);
      const range = zone.path_t_range || {};
      if (route && range.start !== undefined && range.end !== undefined) {
        const samples = routeSamplesBetween(route, range.start, range.end, 8);
        const points = samples.map((point) => projectCell(point.x, point.y));
        if (points.length >= 2) {
          const width = Math.max(26, metrics.tileW * routeRoadWidthCells(route) * 0.74);
          ctx.strokeStyle = "rgba(22,11,32,0.42)";
          ctx.lineWidth = width * 1.28;
          traceRoutePath(ctx, points);
          ctx.stroke();
          ctx.strokeStyle = "rgba(143,124,255,0.2)";
          ctx.lineWidth = width * 0.78;
          traceRoutePath(ctx, points);
          ctx.stroke();
          points.forEach((point, index) => {
            if (index % 2 !== 0) return;
            drawComponentTextureEllipse(ctx, "hazard_marker", point.x, point.y, width * 1.05, width * 0.62, {
              variant: index,
              rotation: 0.1 * (index % 3),
              alpha: 0.2,
              composite: "soft-light",
            });
            drawGroundGlow(ctx, point.x, point.y, "#8f7cff", 0.08, Math.max(34, width * 0.88));
          });
          continue;
        }
      }
      if (!zone.position) continue;
      const point = projectCell(zone.position.x, zone.position.y);
      drawGroundGlow(ctx, point.x, point.y, "#8f7cff", 0.13, Math.max(52, metrics.tileW * 0.48));
      ctx.fillStyle = hazardColor;
      ctx.beginPath();
      ctx.ellipse(point.x, point.y, metrics.tileW * 0.36, metrics.tileH * 0.28, 0, 0, Math.PI * 2);
      ctx.fill();
      drawComponentTextureEllipse(ctx, "hazard_marker", point.x, point.y, metrics.tileW * 0.72, metrics.tileH * 0.54, {
        variant: hashString(zone.zone_id || `${zone.position.x},${zone.position.y}`),
        rotation: -0.1,
        alpha: 0.24,
        composite: "soft-light",
      });
    }
    ctx.restore();
  }

  function drawMapDefenseAnchors(ctx) {
    const battle = getBattle();
    const anchors = getDefenseAnchors();
    if (!battle || !battle.metrics || !anchors.length) return;
    const metrics = battle.metrics;
    ctx.save();
    for (const anchor of anchors) {
      if (!anchor.position) continue;
      const point = projectCell(anchor.position.x, anchor.position.y);
      const radiusCells = clamp(Number(anchor.influence_radius_cells) || 1.4, 0.8, 3.5);
      const radiusX = metrics.tileW * radiusCells * 0.34;
      const radiusY = metrics.tileH * radiusCells * 0.28;
      ctx.fillStyle = "rgba(255,211,122,0.055)";
      ctx.strokeStyle = "rgba(255,211,122,0.2)";
      ctx.lineWidth = Math.max(1.2, metrics.tileW * 0.012);
      ctx.beginPath();
      ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.strokeStyle = "rgba(255,225,161,0.32)";
      ctx.lineWidth = Math.max(1, metrics.tileW * 0.01);
      ctx.beginPath();
      ctx.moveTo(point.x - metrics.tileW * 0.12, point.y);
      ctx.lineTo(point.x + metrics.tileW * 0.12, point.y);
      ctx.moveTo(point.x, point.y - metrics.tileH * 0.12);
      ctx.lineTo(point.x, point.y + metrics.tileH * 0.12);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawMapBlockedAreas(ctx) {
    const battle = getBattle();
    const areas = getBlockedAreas();
    if (!battle || !battle.metrics || !areas.length) return;
    const metrics = battle.metrics;
    ctx.save();
    for (const area of areas) {
      const cells = Array.isArray(area.cells) ? area.cells : area.position ? [area.position] : [];
      cells.forEach((cell, index) => {
        if (!isCellInGrid(cell)) return;
        const point = projectCell(cell.x, cell.y);
        const scale = 0.72 * Math.max(0.72, metrics.scale || 1);
        ctx.save();
        ctx.translate(point.x, point.y);
        ctx.rotate(((index % 3) - 1) * 0.12);
        drawComponentTextureEllipse(ctx, "blocking_prop", 0, 1 * scale, 58 * scale, 34 * scale, {
          variant: index + hashString(area.area_id || ""),
          rotation: ((index % 3) - 1) * 0.08,
          alpha: 0.18,
          composite: "soft-light",
        });
        drawCollapsedWall(ctx, scale);
        ctx.restore();
      });
    }
    ctx.restore();
  }

  function drawMapRuntimeStrongSemantics(ctx) {
    drawMapBlockedAreas(ctx);
    drawMapHazardZones(ctx);
    drawMapResourceNodes(ctx);
    drawMapDefenseAnchors(ctx);
  }

  return { drawMapRuntimeStrongSemantics };
}
