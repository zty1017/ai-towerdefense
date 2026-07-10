export function createBattleWorldRenderer({
  getBattle,
  getObjectives,
  getVisualProfile,
  terrainFeatureSet,
  projectCell,
  drawComponentTextureEllipse,
  drawGroundGlow,
  drawSprite,
  drawTowerMuzzle,
  mapSpriteSize,
  mediaSpriteRef,
  resolveBattleObjectSpriteRef,
  hashString,
} = {}) {
  const dependencies = {
    getBattle,
    getObjectives,
    getVisualProfile,
    terrainFeatureSet,
    projectCell,
    drawComponentTextureEllipse,
    drawGroundGlow,
    drawSprite,
    drawTowerMuzzle,
    mapSpriteSize,
    mediaSpriteRef,
    resolveBattleObjectSpriteRef,
    hashString,
  };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleWorldRenderer requires ${name}`);
    }
  }

  function drawCollapsedWall(ctx, scale) {
    ctx.fillStyle = "rgba(0,0,0,0.24)";
    ctx.beginPath();
    ctx.ellipse(0, 8 * scale, 34 * scale, 11 * scale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(84,78,58,0.62)";
    ctx.strokeStyle = "rgba(205,176,111,0.12)";
    ctx.lineWidth = Math.max(1, 1.3 * scale);
    for (let index = 0; index < 4; index += 1) {
      const x = (index - 1.5) * 14 * scale;
      const height = (10 + (index % 2) * 7) * scale;
      ctx.fillRect(x, -height, 12 * scale, height + 8 * scale);
      ctx.strokeRect(x, -height, 12 * scale, height + 8 * scale);
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
    ctx.fillStyle = warm ? "rgba(255,210,114,0.38)" : "rgba(142,216,216,0.28)";
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
    for (let index = 0; index < 3; index += 1) {
      const x = (index - 1) * 10 * scale;
      ctx.beginPath();
      ctx.moveTo(x, 4 * scale);
      ctx.lineTo(x + 8 * scale, -18 * scale - index * 4 * scale);
      ctx.stroke();
    }
    ctx.strokeStyle = "rgba(204,176,108,0.14)";
    ctx.beginPath();
    ctx.arc(0, -22 * scale, 18 * scale, -0.8, 0.4);
    ctx.stroke();
  }

  function drawBattlefieldLandmarks(ctx) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const metrics = battle.metrics;
    ctx.save();
    for (const landmark of terrainFeatureSet().landmarks || []) {
      const point = projectCell(landmark.x, landmark.y);
      if (point.x < -80 || point.y < -80 || point.x > metrics.width + 80 || point.y > metrics.height + 80) {
        continue;
      }
      ctx.save();
      ctx.translate(point.x, point.y);
      ctx.rotate(landmark.rotation);
      const scale = landmark.scale * Math.max(0.76, metrics.scale);
      drawComponentTextureEllipse(ctx, "non_blocking_decoration", 0, 2 * scale, 52 * scale, 34 * scale, {
        variant: hashString(landmark.kind || "") + Math.floor(landmark.x * 11 + landmark.y * 7),
        rotation: 0.05,
        alpha: 0.14,
        composite: "soft-light",
      });
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

  function drawObjectiveDefensiveZone(ctx, x, y, kind) {
    const metrics = getBattle().metrics;
    const accent = kind === "core" ? "rgba(255,211,122," : "rgba(158,220,255,";
    ctx.save();
    ctx.fillStyle = kind === "core" ? "rgba(82,65,34,0.2)" : "rgba(34,61,70,0.16)";
    ctx.strokeStyle = `${accent}0.2)`;
    ctx.lineWidth = Math.max(2, metrics.tileW * 0.02);
    ctx.beginPath();
    ctx.ellipse(x, y + metrics.tileH * 0.06, metrics.tileW * 0.74, metrics.tileH * 0.56, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.strokeStyle = `${accent}0.12)`;
    ctx.lineWidth = Math.max(1, metrics.tileW * 0.012);
    for (let index = 0; index < 4; index += 1) {
      const angle = (index / 4) * Math.PI * 2 + 0.2;
      ctx.beginPath();
      ctx.moveTo(
        x + Math.cos(angle) * metrics.tileW * 0.46,
        y + Math.sin(angle) * metrics.tileH * 0.34,
      );
      ctx.lineTo(
        x + Math.cos(angle) * metrics.tileW * 0.66,
        y + Math.sin(angle) * metrics.tileH * 0.49,
      );
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawTargetFoundation(ctx, x, y, kind) {
    const metrics = getBattle().metrics;
    const objective = getVisualProfile().objective || {};
    const color = kind === "core" ? objective.core || "#ffd37a" : objective.optional || "#9edcff";
    drawObjectiveDefensiveZone(ctx, x, y, kind);
    drawGroundGlow(ctx, x, y, color, kind === "core" ? 0.2 : 0.14, kind === "core" ? 72 : 52);
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,0.38)";
    ctx.beginPath();
    ctx.ellipse(x, y + metrics.tileH * 0.1, metrics.tileW * 0.36, metrics.tileH * 0.32, 0, 0, Math.PI * 2);
    ctx.fill();
    const base = ctx.createLinearGradient(x, y - metrics.tileH * 0.24, x, y + metrics.tileH * 0.24);
    base.addColorStop(0, "rgba(151,128,82,0.66)");
    base.addColorStop(1, "rgba(42,39,31,0.88)");
    ctx.fillStyle = base;
    ctx.beginPath();
    ctx.ellipse(x, y, metrics.tileW * 0.31, metrics.tileH * 0.3, 0, 0, Math.PI * 2);
    ctx.fill();
    drawComponentTextureEllipse(
      ctx,
      "objective_foundation",
      x,
      y,
      metrics.tileW * (kind === "core" ? 0.76 : 0.62),
      metrics.tileH * (kind === "core" ? 0.72 : 0.58),
      {
        variant: kind === "core" ? 0 : 1,
        alpha: kind === "core" ? 0.28 : 0.22,
        composite: "soft-light",
      },
    );
    ctx.strokeStyle = kind === "core" ? "rgba(255,225,161,0.46)" : "rgba(158,220,255,0.32)";
    ctx.lineWidth = Math.max(1.4, metrics.tileW * 0.015);
    ctx.beginPath();
    ctx.ellipse(x, y, metrics.tileW * 0.31, metrics.tileH * 0.3, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  function drawWorldObjects(ctx, options = {}) {
    const battle = getBattle();
    if (!battle || !battle.metrics) return;
    const layeredBackdrop = Boolean(options.layeredBackdrop);
    if (!layeredBackdrop) drawBattlefieldLandmarks(ctx);
    const objectives = getObjectives();
    const core = objectives.core_target || { position: { x: 0, y: 6 } };
    const corePoint = projectCell(core.position.x, core.position.y);
    if (!layeredBackdrop) {
      drawTargetFoundation(ctx, corePoint.x, corePoint.y, "core");
      drawSprite(
        ctx,
        mediaSpriteRef("objective_station_core", "objective_sprite", true),
        corePoint.x,
        corePoint.y,
        mapSpriteSize(92, 46),
      );
      for (const target of objectives.optional_targets || []) {
        if (!target.position) continue;
        const point = projectCell(target.position.x, target.position.y);
        drawTargetFoundation(ctx, point.x, point.y, "beacon");
        drawSprite(
          ctx,
          mediaSpriteRef("objective_signal_beacon", "objective_sprite", true),
          point.x,
          point.y,
          mapSpriteSize(72, 38),
        );
      }
    }
    for (const defense of battle.defenses || []) {
      const point = projectCell(defense.x, defense.y);
      const recentlyFired = Math.max(0, 1 - (battle.elapsedMs - (defense.shotAt || 0)) / 260);
      const attackColor = defense.attackColor || "#ffd37a";
      drawGroundGlow(ctx, point.x, point.y, attackColor, 0.12 + recentlyFired * 0.12, 34 + recentlyFired * 20);
      const spriteRef =
        resolveBattleObjectSpriteRef(defense) ||
        mediaSpriteRef("defense_basic_lantern_barricade", "defense_sprite", true);
      drawSprite(
        ctx,
        spriteRef,
        point.x,
        point.y - recentlyFired * 3,
        mapSpriteSize(66 + recentlyFired * 6, 38),
        recentlyFired > 0.05,
      );
      if (recentlyFired > 0.05) drawTowerMuzzle(ctx, point.x, point.y, recentlyFired, attackColor);
    }
    for (const trap of battle.traps || []) {
      const point = projectCell(trap.x, trap.y);
      drawGroundGlow(ctx, point.x, point.y, "#9edcff", trap.armed ? 0.18 : 0.3, trap.armed ? 28 : 54);
      const spriteRef = resolveBattleObjectSpriteRef(trap);
      if (spriteRef) {
        drawSprite(ctx, spriteRef, point.x, point.y, mapSpriteSize(48, 28));
      } else {
        ctx.strokeStyle = "#9edcff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(point.x, point.y, 24, 10, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  function drawSpawnRift(ctx, x, y, index) {
    const battle = getBattle();
    const metrics = battle.metrics;
    const spawn = getVisualProfile().spawn || {};
    const phase = (battle.elapsedMs || 0) / 900 + index * 1.7;
    drawGroundGlow(ctx, x, y, spawn.glow || "#8f7cff", 0.16, Math.max(58, metrics.tileW * 0.58));
    ctx.save();
    ctx.fillStyle = "rgba(15,10,24,0.72)";
    ctx.beginPath();
    ctx.ellipse(x, y + metrics.tileH * 0.04, metrics.tileW * 0.28, metrics.tileH * 0.2, -0.08, 0, Math.PI * 2);
    ctx.fill();
    drawComponentTextureEllipse(ctx, "spawn_marker", x, y + metrics.tileH * 0.02, metrics.tileW * 0.74, metrics.tileH * 0.52, {
      variant: index,
      rotation: -0.08,
      alpha: 0.26,
      composite: "soft-light",
    });
    ctx.strokeStyle = spawn.stroke || "rgba(187,166,255,0.36)";
    ctx.lineWidth = Math.max(1.4, metrics.tileW * 0.013);
    ctx.beginPath();
    ctx.ellipse(x, y, metrics.tileW * 0.31, metrics.tileH * 0.24, -0.08, 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineCap = "round";
    for (let indexOffset = 0; indexOffset < 6; indexOffset += 1) {
      const progress = indexOffset / 5;
      const drift = Math.sin(phase + indexOffset * 1.3) * metrics.tileW * 0.08;
      const startX = x + (progress - 0.5) * metrics.tileW * 0.38;
      const startY = y - metrics.tileH * (0.08 + progress * 0.08);
      ctx.strokeStyle = `rgba(190,177,255,${0.18 - progress * 0.018})`;
      ctx.lineWidth = Math.max(2, metrics.tileW * (0.016 + progress * 0.006));
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.bezierCurveTo(
        startX + drift,
        startY - metrics.tileH * 0.48,
        startX - drift * 0.7,
        startY - metrics.tileH * 0.78,
        startX + drift * 0.42,
        startY - metrics.tileH * 1.1,
      );
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawSpawnMarkers(ctx) {
    const battle = getBattle();
    if (!battle) return;
    const spawns = (battle.mapPackage || {}).spawn_points || [];
    ctx.save();
    spawns.forEach((spawn, index) => {
      if (!spawn.position) return;
      const point = projectCell(spawn.position.x, spawn.position.y);
      drawSpawnRift(ctx, point.x, point.y, index);
    });
    ctx.restore();
  }

  return {
    drawCollapsedWall,
    drawSpawnMarkers,
    drawWorldObjects,
  };
}
