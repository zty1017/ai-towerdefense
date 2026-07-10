function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function alphaColor(hex, alpha) {
  const value = String(hex || "#000000").replace("#", "");
  const red = parseInt(value.slice(0, 2), 16) || 0;
  const green = parseInt(value.slice(2, 4), 16) || 0;
  const blue = parseInt(value.slice(4, 6), 16) || 0;
  return `rgba(${red},${green},${blue},${clamp(alpha, 0, 1)})`;
}

export function imageRenderable(image) {
  return Boolean(image && image.complete && image.naturalWidth && image.naturalHeight);
}

export function createBattleTerrainRenderer({
  getBattle,
  getLayeredBackdropImage,
  terrainFeatureSet,
  mapGrid,
  runtimeMapSeed,
  projectCell,
  mapComponentImage,
  hashString,
  makeSeededRandom,
} = {}) {
  const dependencies = {
    getBattle,
    getLayeredBackdropImage,
    terrainFeatureSet,
    mapGrid,
    runtimeMapSeed,
    projectCell,
    mapComponentImage,
    hashString,
    makeSeededRandom,
  };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleTerrainRenderer requires ${name}`);
    }
  }

  function drawComponentTextureEllipse(ctx, role, x, y, width, height, options = {}) {
    const image = mapComponentImage(role, options.variant || 0);
    if (!imageRenderable(image)) return false;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(options.rotation || 0);
    ctx.beginPath();
    ctx.ellipse(0, 0, width / 2, height / 2, 0, 0, Math.PI * 2);
    ctx.clip();
    ctx.globalAlpha = options.alpha ?? 0.24;
    ctx.globalCompositeOperation = options.composite || "source-over";
    ctx.drawImage(image, -width / 2, -height / 2, width, height);
    ctx.restore();
    return true;
  }

  function midpoint(left, right) {
    return { x: (left.x + right.x) / 2, y: (left.y + right.y) / 2 };
  }

  function traceOrganicClosedShape(ctx, points) {
    if (!points.length) return;
    const start = midpoint(points[points.length - 1], points[0]);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    points.forEach((point, index) => {
      const next = points[(index + 1) % points.length];
      const middle = midpoint(point, next);
      ctx.quadraticCurveTo(point.x, point.y, middle.x, middle.y);
    });
    ctx.closePath();
  }

  function fieldPerimeterPoints(margin = 0.86) {
    const grid = mapGrid();
    const maxX = Math.max(0, grid.width_cells - 1);
    const maxY = Math.max(0, grid.height_cells - 1);
    const anchors = [
      { x: -margin, y: -margin * 0.72 },
      { x: maxX * 0.34, y: -margin * 1.18 },
      { x: maxX + margin * 0.92, y: -margin * 0.64 },
      { x: maxX + margin * 1.16, y: maxY * 0.48 },
      { x: maxX + margin * 0.58, y: maxY + margin },
      { x: maxX * 0.48, y: maxY + margin * 1.18 },
      { x: -margin * 0.78, y: maxY + margin * 0.72 },
      { x: -margin * 1.12, y: maxY * 0.42 },
    ];
    return anchors.map((point, index) => {
      const jitter = Math.sin((runtimeMapSeed() % 97) + index * 1.73) * 0.1;
      return projectCell(point.x + jitter, point.y - jitter * 0.45);
    });
  }

  function drawLayeredMapBackdrop(ctx, metrics) {
    const image = getLayeredBackdropImage();
    if (!imageRenderable(image)) return false;
    ctx.save();
    ctx.fillStyle = "#050706";
    ctx.fillRect(0, 0, metrics.width, metrics.height);
    const sourceWidth = image.naturalWidth || image.width || metrics.baseWidth || 1280;
    const sourceHeight = image.naturalHeight || image.height || metrics.baseHeight || 720;
    const coverScale = Math.max(metrics.width / sourceWidth, metrics.height / sourceHeight);
    const coverWidth = sourceWidth * coverScale;
    const coverHeight = sourceHeight * coverScale;
    const coverX = (metrics.width - coverWidth) / 2;
    const coverY = (metrics.height - coverHeight) / 2;
    ctx.save();
    const narrowViewport = metrics.width <= 760;
    ctx.globalAlpha = narrowViewport ? 1 : 0.58;
    ctx.filter = narrowViewport
      ? "blur(6px) brightness(0.9) saturate(0.88)"
      : "blur(14px) brightness(0.52) saturate(0.86)";
    ctx.drawImage(image, coverX - 18, coverY - 18, coverWidth + 36, coverHeight + 36);
    ctx.restore();
    ctx.drawImage(
      image,
      metrics.imageOffsetX,
      metrics.imageOffsetY,
      metrics.imageWidth,
      metrics.imageHeight,
    );
    ctx.restore();
    return true;
  }

  function drawScenicBackplate(ctx, metrics, features) {
    const soil = features.profile.soil;
    ctx.save();
    for (const ridge of features.scenicRidges || []) {
      const point = projectCell(ridge.x, ridge.y);
      const rx = Math.max(36, metrics.tileW * ridge.width * 0.34);
      const ry = Math.max(18, metrics.tileH * ridge.height * 0.7);
      const color = ridge.warm ? "rgba(105,88,59," : "rgba(39,64,58,";
      ctx.fillStyle = `${color}${ridge.alpha})`;
      ctx.beginPath();
      ctx.ellipse(point.x, point.y, rx, ry, -0.18, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = alphaColor(soil[1], 0.12);
      ctx.lineWidth = Math.max(2, metrics.tileW * 0.018);
      ctx.beginPath();
      ctx.ellipse(point.x, point.y - ry * 0.08, rx * 0.74, ry * 0.5, -0.18, 0.18, Math.PI * 1.12);
      ctx.stroke();
    }

    const glow = ctx.createRadialGradient(
      metrics.safeArea.left + (metrics.width - metrics.safeArea.left - metrics.safeArea.right) * 0.54,
      metrics.safeArea.top + (metrics.height - metrics.safeArea.top - metrics.safeArea.bottom) * 0.42,
      8,
      metrics.width * 0.54,
      metrics.height * 0.52,
      Math.max(metrics.width, metrics.height) * 0.62,
    );
    glow.addColorStop(0, "rgba(236,204,129,0.07)");
    glow.addColorStop(0.46, "rgba(118,139,109,0.04)");
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, metrics.width, metrics.height);
    ctx.restore();
  }

  function drawTerrainDepthBands(ctx, metrics, features) {
    ctx.save();
    for (const band of features.bands || []) {
      const y = band.y * metrics.height;
      const height = band.height * metrics.height;
      const lean = band.lean * metrics.width;
      ctx.fillStyle = band.warm
        ? `rgba(193,160,91,${band.alpha})`
        : `rgba(86,132,118,${band.alpha})`;
      ctx.beginPath();
      ctx.moveTo(-80, y);
      ctx.bezierCurveTo(
        metrics.width * 0.25,
        y + height * 0.3,
        metrics.width * 0.55,
        y - height * 0.24,
        metrics.width + 80,
        y + lean * 0.12,
      );
      ctx.lineTo(metrics.width + 80, y + height + lean * 0.1);
      ctx.bezierCurveTo(
        metrics.width * 0.6,
        y + height * 1.22,
        metrics.width * 0.25,
        y + height * 0.76,
        -80,
        y + height * 0.98,
      );
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function drawComponentTerrainTextures(ctx, metrics, features) {
    const random = makeSeededRandom(runtimeMapSeed() ^ hashString("component-terrain-texture"));
    const roles = ["terrain_base", "terrain_detail"];
    ctx.save();
    for (let index = 0; index < 8; index += 1) {
      const role = roles[index % roles.length];
      const x = metrics.safeArea.left + random() * Math.max(1, metrics.width - metrics.safeArea.left - metrics.safeArea.right);
      const y = metrics.safeArea.top + random() * Math.max(1, metrics.height - metrics.safeArea.top - metrics.safeArea.bottom);
      const width = metrics.tileW * (1.4 + random() * 1.2);
      const height = metrics.tileH * (1.0 + random() * 0.9);
      drawComponentTextureEllipse(ctx, role, x, y, width, height, {
        variant: index,
        rotation: (random() - 0.5) * 0.7,
        alpha: role === "terrain_base" ? 0.09 : 0.16,
        composite: "soft-light",
      });
    }
    for (const patch of features.patches.slice(0, 5)) {
      drawComponentTextureEllipse(
        ctx,
        "terrain_detail",
        patch.x * metrics.width,
        patch.y * metrics.height,
        patch.rx * metrics.width * 1.7,
        patch.ry * metrics.height * 1.8,
        {
          variant: Math.floor(patch.x * 1000 + patch.y * 100),
          rotation: patch.rotation || 0,
          alpha: 0.1,
          composite: "soft-light",
        },
      );
    }
    ctx.restore();
  }

  function drawPlayableFieldBoundary(ctx, metrics) {
    const points = fieldPerimeterPoints();
    const soil = terrainFeatureSet().profile.soil;
    ctx.save();
    ctx.translate(0, metrics.tileH * 0.52);
    traceOrganicClosedShape(ctx, points);
    ctx.fillStyle = "rgba(0,0,0,0.16)";
    ctx.fill();
    ctx.restore();

    ctx.save();
    traceOrganicClosedShape(ctx, points);
    const fill = ctx.createLinearGradient(
      0,
      metrics.imageOffsetY,
      metrics.width,
      metrics.imageOffsetY + metrics.imageHeight,
    );
    fill.addColorStop(0, alphaColor(soil[0], 0.62));
    fill.addColorStop(0.44, alphaColor(soil[1], 0.58));
    fill.addColorStop(1, alphaColor(soil[2], 0.64));
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = "rgba(7,9,8,0.18)";
    ctx.lineWidth = Math.max(5, metrics.tileW * 0.04);
    traceOrganicClosedShape(ctx, points);
    ctx.stroke();
    ctx.strokeStyle = "rgba(95,96,64,0.16)";
    ctx.lineWidth = Math.max(2, metrics.tileW * 0.018);
    traceOrganicClosedShape(ctx, points);
    ctx.stroke();
    ctx.strokeStyle = "rgba(224,188,105,0.07)";
    ctx.lineWidth = Math.max(1, metrics.tileW * 0.01);
    traceOrganicClosedShape(ctx, points);
    ctx.stroke();
    ctx.restore();
  }

  function drawFieldEdgeBreakup(ctx, metrics, features) {
    const props = features.fieldEdgeProps || [];
    if (!props.length) return;
    const perimeter = fieldPerimeterPoints(1.02);
    ctx.save();
    for (const prop of props) {
      const start = perimeter[prop.edgeIndex % perimeter.length];
      const end = perimeter[(prop.edgeIndex + 1) % perimeter.length];
      const x = start.x + (end.x - start.x) * prop.t;
      const y = start.y + (end.y - start.y) * prop.t;
      if (x < -80 || y < -80 || x > metrics.width + 80 || y > metrics.height + 80) continue;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(Math.atan2(end.y - start.y, end.x - start.x) + prop.angleJitter);
      ctx.globalAlpha = prop.alpha;
      const scale = prop.scale * Math.max(0.72, metrics.scale);
      if (prop.kind === "timber") {
        ctx.fillStyle = "rgba(114,87,48,0.72)";
        ctx.strokeStyle = "rgba(230,190,108,0.2)";
        ctx.lineWidth = Math.max(1, scale);
        ctx.fillRect(-18 * scale, -3 * scale, 36 * scale, 6 * scale);
        ctx.strokeRect(-18 * scale, -3 * scale, 36 * scale, 6 * scale);
      } else if (prop.kind === "reed") {
        ctx.strokeStyle = "rgba(142,161,108,0.78)";
        ctx.lineWidth = Math.max(1, 1.1 * scale);
        for (let index = 0; index < 3; index += 1) {
          const reedX = (index - 1) * 4 * scale;
          ctx.beginPath();
          ctx.moveTo(reedX, 6 * scale);
          ctx.quadraticCurveTo(reedX + 5 * scale, -7 * scale, reedX + 1 * scale, -18 * scale);
          ctx.stroke();
        }
      } else {
        ctx.fillStyle = "rgba(82,80,62,0.74)";
        ctx.beginPath();
        ctx.ellipse(0, 0, 10 * scale, 5 * scale, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }
    ctx.restore();
  }

  function drawOrganicTerrainPatch(ctx, metrics, patch) {
    const centerX = patch.x * metrics.width;
    const centerY = patch.y * metrics.height;
    const radiusX = patch.rx * metrics.width;
    const radiusY = patch.ry * metrics.height;
    const points = patch.wobble.map((scale, index) => {
      const angle = (index / patch.wobble.length) * Math.PI * 2 + patch.rotation;
      return {
        x: centerX + Math.cos(angle) * radiusX * scale,
        y: centerY + Math.sin(angle) * radiusY * scale,
      };
    });
    ctx.save();
    ctx.fillStyle = patch.color;
    ctx.beginPath();
    points.forEach((point, index) => {
      const next = points[(index + 1) % points.length];
      const middleX = (point.x + next.x) / 2;
      const middleY = (point.y + next.y) / 2;
      if (index === 0) ctx.moveTo(middleX, middleY);
      const afterNext = points[(index + 2) % points.length];
      ctx.quadraticCurveTo(next.x, next.y, (next.x + afterNext.x) / 2, (next.y + afterNext.y) / 2);
    });
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawDarkTidePools(ctx, features) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    ctx.save();
    for (const pool of features.darkPools || []) {
      const point = projectCell(pool.x, pool.y);
      const radiusX = metrics.tileW * pool.rx;
      const radiusY = metrics.tileH * pool.ry;
      const gradient = ctx.createRadialGradient(point.x, point.y, 2, point.x, point.y, radiusX);
      gradient.addColorStop(0, `rgba(18,15,28,${pool.alpha + 0.08})`);
      gradient.addColorStop(0.58, `rgba(25,31,29,${pool.alpha})`);
      gradient.addColorStop(1, "rgba(9,12,12,0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.ellipse(point.x, point.y, radiusX, radiusY, pool.rotation, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = `rgba(118,132,118,${pool.alpha * 0.5})`;
      ctx.lineWidth = Math.max(1, metrics.tileW * 0.01);
      ctx.beginPath();
      ctx.ellipse(point.x, point.y, radiusX * 0.72, radiusY * 0.58, pool.rotation, 0.2, Math.PI * 1.25);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawTerrainDebris(ctx, features) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    ctx.save();
    for (const item of features.debris || []) {
      const point = projectCell(item.x + item.dx, item.y + item.dy);
      if (point.x < -80 || point.y < -80 || point.x > metrics.width + 80 || point.y > metrics.height + 80) continue;
      const size = item.size * Math.max(5, metrics.tileH * 0.22);
      ctx.save();
      ctx.translate(point.x, point.y);
      ctx.rotate(item.rotation);
      if (item.kind === "reed") {
        ctx.strokeStyle = item.shade > 0.5 ? "rgba(139,159,103,0.26)" : "rgba(88,117,96,0.28)";
        ctx.lineWidth = Math.max(1, size * 0.1);
        for (let index = 0; index < 3; index += 1) {
          const lean = (index - 1) * size * 0.16;
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

  function drawProceduralTerrain(ctx, metrics) {
    const features = terrainFeatureSet();
    const soil = features.profile.soil;
    const gradient = ctx.createLinearGradient(0, 0, metrics.width, metrics.height);
    gradient.addColorStop(0, soil[0]);
    gradient.addColorStop(0.36, soil[1]);
    gradient.addColorStop(0.68, soil[2]);
    gradient.addColorStop(1, soil[3]);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, metrics.width, metrics.height);
    drawScenicBackplate(ctx, metrics, features);
    drawTerrainDepthBands(ctx, metrics, features);
    drawComponentTerrainTextures(ctx, metrics, features);
    drawPlayableFieldBoundary(ctx, metrics);
    drawFieldEdgeBreakup(ctx, metrics, features);
    for (const patch of features.patches) drawOrganicTerrainPatch(ctx, metrics, patch);
    drawDarkTidePools(ctx, features);

    ctx.save();
    for (const speck of features.specks) {
      ctx.fillStyle = speck.warm
        ? `rgba(209,180,111,${speck.alpha})`
        : `rgba(149,174,151,${speck.alpha})`;
      ctx.beginPath();
      ctx.ellipse(
        speck.x * metrics.width,
        speck.y * metrics.height,
        speck.size * metrics.scale,
        speck.size * 0.42 * metrics.scale,
        0,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
    ctx.restore();
    drawTerrainDebris(ctx, features);
  }

  function drawEdgeFog(ctx, metrics) {
    const top = ctx.createLinearGradient(0, 0, 0, metrics.height * 0.34);
    top.addColorStop(0, "rgba(3,5,5,0.46)");
    top.addColorStop(1, "rgba(3,5,5,0)");
    ctx.fillStyle = top;
    ctx.fillRect(0, 0, metrics.width, metrics.height * 0.36);

    const bottom = ctx.createLinearGradient(0, metrics.height, 0, metrics.height * 0.58);
    bottom.addColorStop(0, "rgba(0,0,0,0.58)");
    bottom.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = bottom;
    ctx.fillRect(0, metrics.height * 0.56, metrics.width, metrics.height * 0.44);

    const side = ctx.createLinearGradient(0, 0, metrics.width, 0);
    side.addColorStop(0, "rgba(0,0,0,0.42)");
    side.addColorStop(0.16, "rgba(0,0,0,0)");
    side.addColorStop(0.84, "rgba(0,0,0,0)");
    side.addColorStop(1, "rgba(0,0,0,0.46)");
    ctx.fillStyle = side;
    ctx.fillRect(0, 0, metrics.width, metrics.height);

    const features = terrainFeatureSet();
    const battle = getBattle();
    const time = (((battle || {}).elapsedMs || 0) / 1200);
    ctx.save();
    ctx.lineCap = "round";
    for (const wisp of features.wisps || []) {
      const fromLeft = wisp.edge === 0;
      const fromRight = wisp.edge === 1;
      const fromTop = wisp.edge === 2;
      const x = fromLeft ? -20 : fromRight ? metrics.width + 20 : wisp.offset * metrics.width;
      const y = fromTop ? -16 : wisp.offset * metrics.height;
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

  function drawBackdrop(ctx, metrics) {
    const layeredBackdrop = drawLayeredMapBackdrop(ctx, metrics);
    if (!layeredBackdrop) drawProceduralTerrain(ctx, metrics);
    drawEdgeFog(ctx, metrics);
    return layeredBackdrop;
  }

  return {
    drawBackdrop,
    drawComponentTextureEllipse,
    drawProceduralTerrain,
    imageRenderable,
  };
}
