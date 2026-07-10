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

  function drawDeploymentBase(ctx, point, metrics, index, active, slot = {}) {
    const random = makeSeededRandom(runtimeMapSeed() ^ hashString(`slot:${index}`));
    const platform = getVisualProfile().platform || {};
    const footprintX = slotFootprintScale(slot, "width");
    const footprintY = slotFootprintScale(slot, "height");
    const radiusX = metrics.tileW * (0.22 + random() * 0.035) * footprintX;
    const radiusY = metrics.tileH * (0.28 + random() * 0.04) * footprintY;
    ctx.save();
    ctx.globalAlpha = active ? 0.95 : 0.58;
    ctx.fillStyle = "rgba(0,0,0,0.34)";
    ctx.beginPath();
    ctx.ellipse(point.x, point.y + metrics.tileH * 0.1, radiusX * 1.18, radiusY * 0.76, 0, 0, Math.PI * 2);
    ctx.fill();
    const base = ctx.createLinearGradient(point.x, point.y - radiusY, point.x, point.y + radiusY);
    base.addColorStop(0, platform.fillTop || "rgba(126,111,78,0.72)");
    base.addColorStop(0.54, "rgba(74,69,52,0.76)");
    base.addColorStop(1, "rgba(35,34,28,0.88)");
    ctx.fillStyle = base;
    ctx.beginPath();
    ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.fill();
    drawComponentTextureEllipse(ctx, "build_slot_platform", point.x, point.y, radiusX * 2, radiusY * 1.86, {
      variant: index,
      rotation: (random() - 0.5) * 0.18,
      alpha: active ? 0.32 : 0.18,
      composite: "soft-light",
    });
    ctx.strokeStyle = active
      ? platform.active || "rgba(255,225,161,0.68)"
      : platform.stroke || "rgba(213,184,118,0.28)";
    ctx.lineWidth = Math.max(1.4, metrics.tileW * 0.015);
    ctx.beginPath();
    ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = active ? "rgba(255,224,145,0.42)" : "rgba(178,156,106,0.2)";
    for (let ring = 0; ring < 3; ring += 1) {
      const angle = random() * Math.PI * 2;
      ctx.beginPath();
      ctx.arc(point.x, point.y, radiusX * (0.48 + ring * 0.12), angle, angle + Math.PI * (0.2 + random() * 0.18));
      ctx.stroke();
    }
    ctx.fillStyle = active ? "rgba(255,211,122,0.26)" : "rgba(255,211,122,0.13)";
    ctx.beginPath();
    ctx.ellipse(point.x, point.y - radiusY * 0.18, radiusX * 0.28, radiusY * 0.24, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawDeployHints(ctx, options = {}) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    const activeOverlay = Boolean(battle.draggingTool || battle.hoverCell);
    if (options.layeredBackdrop && !activeOverlay) return;
    suggestedSockets().forEach((slot, index) => {
      const cell = slot.position || slot;
      const point = projectCell(cell.x, cell.y);
      drawDeploymentBase(ctx, point, metrics, index, activeOverlay, slot);
    });
    const previewCell = battle.hoverCell;
    if (!previewCell) return;
    const point = projectCell(previewCell.x, previewCell.y);
    const tool = battle.draggingTool || battle.selectedTool;
    const valid = canPreviewToolAt(tool, previewCell);
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
