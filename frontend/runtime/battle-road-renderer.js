function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function createBattleRoadRenderer({
  getBattle,
  getVisualProfile,
  getRoutes,
  projectCell,
  routeRoadWidthCells,
  routeShoulderWidthScale,
  runtimeMapSeed,
  hashString,
  makeSeededRandom,
  drawComponentTextureEllipse,
  terrainFeatureSet,
} = {}) {
  const dependencies = {
    getBattle,
    getVisualProfile,
    getRoutes,
    projectCell,
    routeRoadWidthCells,
    routeShoulderWidthScale,
    runtimeMapSeed,
    hashString,
    makeSeededRandom,
    drawComponentTextureEllipse,
    terrainFeatureSet,
  };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleRoadRenderer requires ${name}`);
    }
  }

  function traceRoutePath(ctx, points) {
    ctx.beginPath();
    if (points.length < 2) return;
    ctx.moveTo(points[0].x, points[0].y);
    for (let index = 1; index < points.length - 1; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      const next = points[index + 1];
      const incomingDistance = Math.hypot(current.x - previous.x, current.y - previous.y);
      const outgoingDistance = Math.hypot(next.x - current.x, next.y - current.y);
      const radius = Math.min(48, incomingDistance * 0.32, outgoingDistance * 0.32);
      const entry = {
        x: current.x - ((current.x - previous.x) / Math.max(1, incomingDistance)) * radius,
        y: current.y - ((current.y - previous.y) / Math.max(1, incomingDistance)) * radius,
      };
      const exit = {
        x: current.x + ((next.x - current.x) / Math.max(1, outgoingDistance)) * radius,
        y: current.y + ((next.y - current.y) / Math.max(1, outgoingDistance)) * radius,
      };
      ctx.lineTo(entry.x, entry.y);
      ctx.quadraticCurveTo(current.x, current.y, exit.x, exit.y);
    }
    const last = points[points.length - 1];
    ctx.lineTo(last.x, last.y);
  }

  function drawRoadComponentStamps(ctx, route, points, roadWidth) {
    if (points.length < 2) return;
    const seed = runtimeMapSeed() ^ hashString(`road-component:${route.route_id || "route"}`);
    const random = makeSeededRandom(seed);
    ctx.save();
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.max(1, Math.hypot(dx, dy));
      const angle = Math.atan2(dy, dx);
      const count = Math.max(1, Math.floor(length / Math.max(64, roadWidth * 1.4)));
      for (let itemIndex = 0; itemIndex < count; itemIndex += 1) {
        const t = (itemIndex + 0.5 + (random() - 0.5) * 0.2) / count;
        const x = start.x + dx * clamp(t, 0.08, 0.92);
        const y = start.y + dy * clamp(t, 0.08, 0.92);
        drawComponentTextureEllipse(ctx, "road_band", x, y, roadWidth * 1.18, roadWidth * 0.72, {
          variant: index + itemIndex,
          rotation: angle + (random() - 0.5) * 0.14,
          alpha: 0.18,
          composite: "soft-light",
        });
      }
    }
    ctx.restore();
  }

  function drawRoadTerrainBlend(ctx, route, points, roadWidth) {
    const road = getVisualProfile().road || {};
    const shoulderScale = routeShoulderWidthScale(route);
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.globalCompositeOperation = "source-over";
    ctx.strokeStyle = road.groundBlend || "rgba(28,34,25,0.36)";
    ctx.lineWidth = roadWidth * (1.55 + shoulderScale * 0.42);
    traceRoutePath(ctx, points);
    ctx.stroke();
    ctx.strokeStyle = road.edgeStain || "rgba(111,77,56,0.22)";
    ctx.lineWidth = roadWidth * (1.18 + shoulderScale * 0.25);
    traceRoutePath(ctx, points);
    ctx.stroke();

    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`road-blend:${route.route_id || ""}`));
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.max(1, Math.hypot(dx, dy));
      const nx = -dy / length;
      const ny = dx / length;
      const count = Math.max(2, Math.floor(length / 96));
      for (let itemIndex = 0; itemIndex < count; itemIndex += 1) {
        const t = (itemIndex + 0.12 + random() * 0.76) / count;
        const side = random() > 0.5 ? -1 : 1;
        const offset = side * roadWidth * (0.62 + random() * 0.32);
        const x = start.x + dx * t + nx * offset;
        const y = start.y + dy * t + ny * offset;
        ctx.fillStyle = random() > 0.45 ? "rgba(33,46,34,0.2)" : "rgba(111,83,52,0.16)";
        ctx.beginPath();
        ctx.ellipse(
          x,
          y,
          roadWidth * (0.11 + random() * 0.12),
          roadWidth * (0.035 + random() * 0.055),
          Math.atan2(dy, dx) + (random() - 0.5) * 0.7,
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
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

  function drawRouteEdgeProps(ctx, route, roadWidth) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    const props = (terrainFeatureSet().roadsideProps || []).filter(
      (item) => item.routeId === (route.route_id || "route"),
    );
    ctx.save();
    for (const item of props) {
      const point = projectCell(item.x, item.y);
      if (point.x < -80 || point.y < -80 || point.x > metrics.width + 80 || point.y > metrics.height + 80) continue;
      ctx.save();
      ctx.translate(point.x, point.y);
      ctx.rotate(item.rotation);
      const scale = item.scale * Math.max(0.72, metrics.scale) * Math.max(0.78, roadWidth / 56);
      drawComponentTextureEllipse(ctx, "road_edge", 0, 0, 42 * scale, 22 * scale, {
        variant: Math.floor(item.x * 31 + item.y * 17),
        rotation: item.warm ? 0.12 : -0.08,
        alpha: 0.16,
        composite: "soft-light",
      });
      drawRoadsideProp(ctx, item.kind, scale, item.warm);
      ctx.restore();
    }
    ctx.restore();
  }

  function drawRouteShoulders(ctx, route, points, roadWidth) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    const road = getVisualProfile().road || {};
    const shoulderScale = routeShoulderWidthScale(route);
    ctx.save();
    ctx.strokeStyle = "rgba(6,7,6,0.24)";
    ctx.lineWidth = roadWidth * (1.16 + shoulderScale * 0.34);
    traceRoutePath(ctx, points);
    ctx.stroke();
    ctx.strokeStyle = road.shoulderDark || "rgba(61,69,46,0.52)";
    ctx.lineWidth = roadWidth * (1.02 + shoulderScale * 0.28);
    traceRoutePath(ctx, points);
    ctx.stroke();
    ctx.strokeStyle = road.shoulderSoft || "rgba(33,41,32,0.4)";
    ctx.lineWidth = roadWidth * (0.94 + shoulderScale * 0.24);
    traceRoutePath(ctx, points);
    ctx.stroke();

    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`shoulder:${route.route_id || ""}`));
    ctx.fillStyle = "rgba(169,142,85,0.12)";
    for (const point of points) {
      for (let index = 0; index < 3; index += 1) {
        const angle = random() * Math.PI * 2;
        const distance = roadWidth * shoulderScale * (0.65 + random() * 0.28);
        ctx.beginPath();
        ctx.ellipse(
          point.x + Math.cos(angle) * distance,
          point.y + Math.sin(angle) * distance * 0.6,
          metrics.tileW * (0.035 + random() * 0.04),
          metrics.tileH * (0.025 + random() * 0.04),
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
    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`road:${route.route_id || ""}`));
    const road = getVisualProfile().road || {};
    ctx.save();
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.max(1, Math.hypot(dx, dy));
      const nx = -dy / length;
      const ny = dx / length;
      const count = Math.max(3, Math.floor(length / 46));
      for (let itemIndex = 0; itemIndex < count; itemIndex += 1) {
        const t = (itemIndex + 0.18 + random() * 0.68) / count;
        const edge = random() < 0.55 ? -1 : 1;
        const offset = edge * roadWidth * (0.24 + random() * 0.28);
        const x = start.x + dx * t + nx * offset;
        const y = start.y + dy * t + ny * offset;
        const size = 2.4 + random() * Math.max(5, roadWidth * 0.1);
        ctx.fillStyle = random() > 0.4 ? road.pebbleWarm || "rgba(196,164,102,0.24)" : "rgba(53,47,36,0.28)";
        ctx.beginPath();
        ctx.ellipse(x, y, size, size * 0.42, random() * Math.PI, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawRoadRuts(ctx, route, points, roadWidth) {
    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`ruts:${route.route_id || ""}`));
    const road = getVisualProfile().road || {};
    ctx.save();
    ctx.lineCap = "round";
    ctx.strokeStyle = road.rut || "rgba(62,45,27,0.24)";
    ctx.lineWidth = Math.max(2, roadWidth * 0.055);
    for (const offset of [-0.18, 0.16]) {
      ctx.beginPath();
      points.forEach((point, index) => {
        const previous = points[Math.max(0, index - 1)];
        const next = points[Math.min(points.length - 1, index + 1)];
        const dx = next.x - previous.x;
        const dy = next.y - previous.y;
        const length = Math.max(1, Math.hypot(dx, dy));
        const nx = -dy / length;
        const ny = dx / length;
        const wobble = (random() - 0.5) * roadWidth * 0.08;
        const x = point.x + nx * roadWidth * offset + nx * wobble;
        const y = point.y + ny * roadWidth * offset + ny * wobble;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    ctx.strokeStyle = "rgba(207,170,96,0.12)";
    ctx.lineWidth = Math.max(1, roadWidth * 0.04);
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.max(1, Math.hypot(dx, dy));
      const count = Math.max(1, Math.floor(length / 130));
      const nx = -dy / length;
      const ny = dx / length;
      for (let itemIndex = 0; itemIndex < count; itemIndex += 1) {
        if (random() < 0.42) continue;
        const t = (itemIndex + 0.35 + random() * 0.3) / count;
        const centerX = start.x + dx * t;
        const centerY = start.y + dy * t;
        ctx.beginPath();
        ctx.moveTo(centerX - nx * roadWidth * 0.28, centerY - ny * roadWidth * 0.28);
        ctx.lineTo(centerX + nx * roadWidth * 0.28, centerY + ny * roadWidth * 0.28);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawRouteFlowCues(ctx, route, points, roadWidth) {
    if (points.length < 2) return;
    const battle = getBattle();
    const phase = (((battle || {}).elapsedMs || 0) / 1400) % 1;
    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`flow:${route.route_id || ""}`));
    const road = getVisualProfile().road || {};
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.max(1, Math.hypot(dx, dy));
      const ux = dx / length;
      const uy = dy / length;
      const nx = -uy;
      const ny = ux;
      const count = Math.max(1, Math.floor(length / 150));
      for (let itemIndex = 0; itemIndex < count; itemIndex += 1) {
        const t = ((itemIndex + 0.35 + phase * 0.42) / count) % 1;
        const centerX = start.x + dx * t;
        const centerY = start.y + dy * t;
        const side = random() < 0.5 ? -1 : 1;
        const offset = side * roadWidth * (0.11 + random() * 0.08);
        const x = centerX + nx * offset;
        const y = centerY + ny * offset;
        const size = Math.max(5, roadWidth * 0.11);
        ctx.strokeStyle = road.flow || `rgba(255,213,126,${0.1 + 0.06 * Math.sin(phase * Math.PI)})`;
        ctx.lineWidth = Math.max(1.5, roadWidth * 0.032);
        ctx.beginPath();
        ctx.moveTo(x - ux * size * 0.7 - nx * size * 0.25, y - uy * size * 0.7 - ny * size * 0.25);
        ctx.lineTo(x, y);
        ctx.lineTo(x - ux * size * 0.7 + nx * size * 0.25, y - uy * size * 0.7 + ny * size * 0.25);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawPath(ctx) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    const road = getVisualProfile().road || {};
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const route of getRoutes()) {
      const points = (route.waypoints || []).map((point) => projectCell(point.x, point.y));
      if (points.length < 2) continue;
      const roadWidth = Math.max(34, metrics.tileW * routeRoadWidthCells(route));
      drawRoadTerrainBlend(ctx, route, points, roadWidth);
      drawRouteShoulders(ctx, route, points, roadWidth);
      ctx.strokeStyle = road.shadow || "rgba(18,13,10,0.54)";
      ctx.lineWidth = roadWidth * 1.18;
      traceRoutePath(ctx, points);
      ctx.stroke();
      ctx.strokeStyle = road.base || "rgba(82,62,37,0.86)";
      ctx.lineWidth = roadWidth;
      traceRoutePath(ctx, points);
      ctx.stroke();
      ctx.strokeStyle = road.crown || "rgba(143,112,64,0.64)";
      ctx.lineWidth = roadWidth * 0.68;
      traceRoutePath(ctx, points);
      ctx.stroke();
      drawRoadComponentStamps(ctx, route, points, roadWidth);
      ctx.strokeStyle = road.highlight || "rgba(201,169,103,0.18)";
      ctx.lineWidth = Math.max(5, roadWidth * 0.14);
      traceRoutePath(ctx, points);
      ctx.stroke();
      drawRoadPebbles(ctx, route, points, roadWidth);
      drawRoadRuts(ctx, route, points, roadWidth);
      drawRouteFlowCues(ctx, route, points, roadWidth);
      drawRouteEdgeProps(ctx, route, roadWidth);
    }
    ctx.restore();
  }

  function drawSlotAccessTrails(ctx) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    const trails = terrainFeatureSet().accessTrails || [];
    if (!trails.length) return;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const trail of trails) {
      const from = projectCell(trail.from.x, trail.from.y);
      const to = projectCell(trail.to.x, trail.to.y);
      const middle = {
        x: (from.x + to.x) / 2,
        y: (from.y + to.y) / 2 - metrics.tileH * 0.08,
      };
      ctx.strokeStyle = "rgba(23,16,10,0.18)";
      ctx.lineWidth = Math.max(6, metrics.tileW * 0.072);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y + metrics.tileH * 0.03);
      ctx.quadraticCurveTo(middle.x, middle.y, to.x, to.y);
      ctx.stroke();
      ctx.strokeStyle = "rgba(167,134,73,0.13)";
      ctx.lineWidth = Math.max(2, metrics.tileW * 0.026);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y + metrics.tileH * 0.02);
      ctx.quadraticCurveTo(middle.x, middle.y, to.x, to.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  return {
    drawPath,
    drawSlotAccessTrails,
    traceRoutePath,
  };
}
