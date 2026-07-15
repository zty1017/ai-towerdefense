export function createBattleDeploymentRenderer({
  getBattle,
  getSlots,
  isCellInGrid,
  projectCell,
  makeSeededRandom,
  runtimeMapSeed,
  hashString,
  slotFootprintScale,
  getVisualProfile,
  drawComponentTextureEllipse,
  canPreviewToolAt,
  drawSprite,
  drawGroundGlow,
  mapSpriteSize,
  resolveToolSpriteRef,
  getToolProjection = () => null,
} = {}) {
  const dependencies = {
    getBattle,
    getSlots,
    isCellInGrid,
    projectCell,
    makeSeededRandom,
    runtimeMapSeed,
    hashString,
    slotFootprintScale,
    getVisualProfile,
    drawComponentTextureEllipse,
    canPreviewToolAt,
    drawSprite,
    drawGroundGlow,
    mapSpriteSize,
    resolveToolSpriteRef,
  };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleDeploymentRenderer requires ${name}`);
    }
  }

  function projectedTool(toolId) {
    return (toolId && getToolProjection(toolId)) || {};
  }

  function toolRangeCells(toolId) {
    const tool = projectedTool(toolId);
    const targeting = (tool.behaviorAbi && tool.behaviorAbi.targeting) || {};
    const fallback = tool.assetKind === "support_item"
      ? 2.1
      : ["temporary_trap_sample", "field_device"].includes(tool.assetKind)
        ? 1.65
        : 2.6;
    const value = Number(targeting.radius_cells || targeting.range_cells || fallback);
    return Math.max(0.3, Math.min(5, Number.isFinite(value) ? value : fallback));
  }

  function previewPalette(toolId, valid) {
    if (!valid) return { line: "rgba(255,92,82,0.92)", fill: "rgba(255,65,58,0.11)" };
    const kind = projectedTool(toolId).assetKind;
    if (["temporary_trap_sample", "field_device"].includes(kind)) {
      return { line: "rgba(119,220,238,0.92)", fill: "rgba(61,187,214,0.1)" };
    }
    if (kind === "support_item") {
      return { line: "rgba(143,207,131,0.92)", fill: "rgba(92,185,112,0.1)" };
    }
    return { line: "rgba(255,211,122,0.94)", fill: "rgba(240,189,88,0.1)" };
  }

  function drawRangePreview(ctx, point, metrics, toolId, valid) {
    const range = toolRangeCells(toolId);
    const radiusX = metrics.tileW * range / Math.SQRT2;
    const radiusY = metrics.tileH * range / Math.SQRT2;
    const palette = previewPalette(toolId, valid);
    ctx.save();
    ctx.fillStyle = palette.fill;
    ctx.strokeStyle = palette.line;
    ctx.lineWidth = Math.max(2, metrics.tileW * 0.022);
    ctx.setLineDash(valid ? [Math.max(8, metrics.tileW * 0.12), Math.max(5, metrics.tileW * 0.07)] : [7, 6]);
    ctx.beginPath();
    ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 0.38;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.ellipse(point.x, point.y, radiusX * 0.94, radiusY * 0.94, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  function suggestedSockets() {
    const slots = getSlots();
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

  function drawPlatformGroundStitch(ctx, point, metrics, radiusX, radiusY, random, active) {
    ctx.save();
    ctx.strokeStyle = active ? "rgba(255,225,161,0.2)" : "rgba(103,94,64,0.2)";
    ctx.lineWidth = Math.max(1, metrics.tileW * 0.01);
    for (let index = 0; index < 7; index += 1) {
      const angle = random() * Math.PI * 2;
      const inner = 0.74 + random() * 0.14;
      const outer = 1.08 + random() * 0.22;
      ctx.beginPath();
      ctx.moveTo(
        point.x + Math.cos(angle) * radiusX * inner,
        point.y + Math.sin(angle) * radiusY * inner + metrics.tileH * 0.03,
      );
      ctx.lineTo(
        point.x + Math.cos(angle) * radiusX * outer,
        point.y + Math.sin(angle) * radiusY * outer + metrics.tileH * 0.03,
      );
      ctx.stroke();
    }
    ctx.fillStyle = active ? "rgba(255,225,161,0.1)" : "rgba(87,84,60,0.16)";
    for (let index = 0; index < 5; index += 1) {
      const angle = random() * Math.PI * 2;
      const distance = 0.92 + random() * 0.34;
      ctx.beginPath();
      ctx.ellipse(
        point.x + Math.cos(angle) * radiusX * distance,
        point.y + Math.sin(angle) * radiusY * distance + metrics.tileH * 0.04,
        Math.max(2, metrics.tileW * (0.014 + random() * 0.018)),
        Math.max(1, metrics.tileH * (0.012 + random() * 0.016)),
        angle,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
    ctx.restore();
  }

  function drawBuildableTerrace(ctx, point, metrics, slot, active) {
    const position = slot.position || slot;
    const id = slot.slot_id || `${position.x},${position.y}`;
    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`terrace:${id}`));
    const footprintX = slotFootprintScale(slot, "width");
    const footprintY = slotFootprintScale(slot, "height");
    const radiusX = metrics.tileW * (0.42 + random() * 0.08) * footprintX;
    const radiusY = metrics.tileH * (0.46 + random() * 0.08) * footprintY;
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,0.24)";
    ctx.beginPath();
    ctx.ellipse(point.x, point.y + metrics.tileH * 0.18, radiusX * 1.08, radiusY * 0.78, 0, 0, Math.PI * 2);
    ctx.fill();
    drawPlatformGroundStitch(ctx, point, metrics, radiusX, radiusY, random, active);
    const fill = ctx.createLinearGradient(point.x, point.y - radiusY, point.x, point.y + radiusY);
    const platform = getVisualProfile().platform || {};
    fill.addColorStop(0, active ? platform.fillTop || "rgba(115,104,68,0.54)" : "rgba(75,79,55,0.42)");
    fill.addColorStop(1, "rgba(31,35,28,0.5)");
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.ellipse(point.x, point.y + metrics.tileH * 0.03, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.fill();
    drawComponentTextureEllipse(
      ctx,
      "build_slot_platform",
      point.x,
      point.y + metrics.tileH * 0.03,
      radiusX * 2,
      radiusY * 1.82,
      {
        variant: hashString(id),
        rotation: (random() - 0.5) * 0.24,
        alpha: active ? 0.24 : 0.18,
        composite: "soft-light",
      },
    );
    ctx.strokeStyle = active
      ? platform.active || "rgba(255,225,161,0.48)"
      : platform.stroke || "rgba(179,153,94,0.18)";
    ctx.lineWidth = Math.max(1.3, metrics.tileW * 0.014);
    ctx.beginPath();
    ctx.ellipse(point.x, point.y + metrics.tileH * 0.03, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = "rgba(214,178,104,0.13)";
    for (let index = 0; index < 4; index += 1) {
      const angle = random() * Math.PI * 2;
      const distance = radiusX * (0.35 + random() * 0.48);
      ctx.beginPath();
      ctx.ellipse(
        point.x + Math.cos(angle) * distance,
        point.y + Math.sin(angle) * radiusY * 0.55,
        Math.max(2, metrics.tileW * (0.018 + random() * 0.018)),
        Math.max(1, metrics.tileH * (0.018 + random() * 0.018)),
        angle,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
    ctx.restore();
  }

  function drawBuildableTerraces(ctx) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    ctx.save();
    for (const slot of suggestedSockets()) {
      const cell = slot.position || slot;
      if (!isCellInGrid(cell)) continue;
      const point = projectCell(cell.x, cell.y);
      const active = Boolean(
        battle.hoverCell && battle.hoverCell.x === cell.x && battle.hoverCell.y === cell.y,
      );
      drawBuildableTerrace(ctx, point, metrics, slot, active);
    }
    ctx.restore();
  }

  function drawDeploymentBase(ctx, point, metrics, index, state = {}, slot = {}) {
    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`slot:${index}`));
    const platform = getVisualProfile().platform || {};
    const footprintX = slotFootprintScale(slot, "width");
    const footprintY = slotFootprintScale(slot, "height");
    const radiusX = metrics.tileW * (0.22 + random() * 0.035) * footprintX;
    const radiusY = metrics.tileH * (0.28 + random() * 0.04) * footprintY;
    ctx.save();
    const { dragging = false, hovered = false, valid = true } = state;
    ctx.globalAlpha = hovered ? 0.96 : valid ? 0.46 : 0.2;
    ctx.fillStyle = "rgba(0,0,0,0.34)";
    ctx.beginPath();
    ctx.ellipse(point.x, point.y + metrics.tileH * 0.1, radiusX * 1.18, radiusY * 0.76, 0, 0, Math.PI * 2);
    ctx.fill();
    const base = ctx.createLinearGradient(point.x, point.y - radiusY, point.x, point.y + radiusY);
    base.addColorStop(0, valid ? platform.fillTop || "rgba(126,111,78,0.72)" : "rgba(86,66,62,0.54)");
    base.addColorStop(0.54, "rgba(74,69,52,0.76)");
    base.addColorStop(1, "rgba(35,34,28,0.88)");
    ctx.fillStyle = base;
    ctx.beginPath();
    ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.fill();
    drawComponentTextureEllipse(ctx, "build_slot_platform", point.x, point.y, radiusX * 2, radiusY * 1.86, {
      variant: index,
      rotation: (random() - 0.5) * 0.18,
      alpha: hovered ? 0.34 : dragging ? 0.12 : 0.18,
      composite: "soft-light",
    });
    ctx.strokeStyle = hovered
      ? valid ? platform.active || "rgba(255,225,161,0.82)" : "rgba(255,92,82,0.76)"
      : valid ? "rgba(213,184,118,0.26)" : "rgba(126,75,69,0.2)";
    ctx.lineWidth = Math.max(1.4, metrics.tileW * 0.015);
    ctx.beginPath();
    ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = hovered ? "rgba(255,224,145,0.4)" : "rgba(178,156,106,0.14)";
    for (let ring = 0; ring < 3; ring += 1) {
      const angle = random() * Math.PI * 2;
      ctx.beginPath();
      ctx.arc(point.x, point.y, radiusX * (0.48 + ring * 0.12), angle, angle + Math.PI * (0.2 + random() * 0.18));
      ctx.stroke();
    }
    ctx.fillStyle = hovered ? "rgba(255,211,122,0.28)" : "rgba(255,211,122,0.08)";
    ctx.beginPath();
    ctx.ellipse(point.x, point.y - radiusY * 0.18, radiusX * 0.28, radiusY * 0.24, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawDeployHints(ctx, options = {}) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    const tool = battle.draggingTool || battle.selectedTool;
    if (options.layeredBackdrop && !tool) return;
    suggestedSockets().forEach((slot, index) => {
      const cell = slot.position || slot;
      const point = projectCell(cell.x, cell.y);
      const hovered = Boolean(battle.hoverCell && battle.hoverCell.x === cell.x && battle.hoverCell.y === cell.y);
      const valid = tool ? canPreviewToolAt(tool, cell) : true;
      drawDeploymentBase(ctx, point, metrics, index, { dragging: Boolean(tool), hovered, valid }, slot);
    });
    const previewCell = battle.hoverCell;
    if (!tool || !previewCell) return;
    const point = projectCell(previewCell.x, previewCell.y);
    const valid = canPreviewToolAt(tool, previewCell);
    drawRangePreview(ctx, point, metrics, tool, valid);
    ctx.save();
    ctx.fillStyle = valid ? "rgba(255,211,122,.17)" : "rgba(255,95,83,.16)";
    ctx.strokeStyle = valid ? "rgba(255,225,161,.74)" : "rgba(255,95,83,.72)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.ellipse(point.x, point.y, metrics.tileW * 0.31, metrics.tileH * 0.42, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = valid ? 0.92 : 0.42;
    if (tool === "sample") {
      const spriteRef = resolveToolSpriteRef(tool);
      if (spriteRef) {
        drawSprite(ctx, spriteRef, point.x, point.y, mapSpriteSize(48, 28));
      } else {
        drawGroundGlow(ctx, point.x, point.y, "#9edcff", 0.3, 42);
        ctx.strokeStyle = "#9edcff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(point.x, point.y, 24, 10, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
    } else if (tool === "support") {
      drawGroundGlow(ctx, point.x, point.y, "#8fcf83", 0.28, 86);
    } else {
      const spriteRef = resolveToolSpriteRef(tool);
      if (spriteRef) {
        drawSprite(ctx, spriteRef, point.x, point.y, mapSpriteSize(62, 36));
      } else {
        drawGroundGlow(ctx, point.x, point.y, "#ffd37a", 0.24, 48);
      }
    }
    ctx.restore();
  }

  return {
    drawBuildableTerraces,
    drawDeployHints,
    suggestedSockets,
  };
}
