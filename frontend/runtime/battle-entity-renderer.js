function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function createBattleEntityRenderer({
  getBattle,
  projectCell,
  mediaSpriteRef,
  getImage,
  resolveToolSpriteRef = () => null,
} = {}) {
  const dependencies = { getBattle, projectCell, mediaSpriteRef, getImage };
  for (const [name, dependency] of Object.entries(dependencies)) {
    if (typeof dependency !== "function") {
      throw new TypeError(`createBattleEntityRenderer requires ${name}`);
    }
  }

  function projectVector(dx, dy) {
    const origin = projectCell(0, 0);
    const target = projectCell(dx, dy);
    return { x: target.x - origin.x, y: target.y - origin.y };
  }

  function drawEnemyMotionTrail(ctx, point, vector, size, slow) {
    const length = Math.hypot(vector.x, vector.y);
    if (length < 0.1) return;
    const nx = vector.x / length;
    const ny = vector.y / length;
    ctx.save();
    ctx.globalCompositeOperation = "screen";
    for (let index = 1; index <= 3; index += 1) {
      const alpha = slow ? 0.08 / index : 0.06 / index;
      ctx.fillStyle = slow ? `rgba(158,220,255,${alpha})` : `rgba(94,78,116,${alpha})`;
      ctx.beginPath();
      ctx.ellipse(
        point.x - nx * size * 0.18 * index,
        point.y - ny * size * 0.12 * index + 5,
        size * (0.18 + index * 0.025),
        size * (0.055 + index * 0.01),
        Math.atan2(ny, nx),
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
    ctx.restore();
  }

  function drawEnemyStatus(ctx, x, y, phase, slow, hit, size) {
    ctx.save();
    if (slow) {
      ctx.strokeStyle = "rgba(158,220,255,0.58)";
      ctx.lineWidth = 1.5;
      for (let index = 0; index < 2; index += 1) {
        const angle = phase * 0.015 + index * Math.PI;
        ctx.beginPath();
        ctx.ellipse(
          x + Math.cos(angle) * size * 0.12,
          y - size * (0.42 + index * 0.1),
          size * (0.26 - index * 0.03),
          size * 0.08,
          angle * 0.35,
          0,
          Math.PI * 2,
        );
        ctx.stroke();
      }
    }
    if (hit) {
      ctx.fillStyle = "rgba(255,241,191,0.42)";
      ctx.beginPath();
      ctx.ellipse(x, y - size * 0.45, size * 0.34, size * 0.5, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawTowerMuzzle(ctx, x, y, ratio) {
    ctx.save();
    ctx.globalCompositeOperation = "screen";
    ctx.strokeStyle = `rgba(255,211,122,${0.62 * ratio})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(x, y - 42, 10 + 20 * (1 - ratio), 5 + 9 * (1 - ratio), 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = `rgba(255,231,160,${0.42 * ratio})`;
    ctx.beginPath();
    ctx.arc(x, y - 45, 5 + 8 * ratio, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function mapSpriteSize(base, minimum) {
    const scale = ((getBattle() || {}).metrics || {}).scale || 1;
    return clamp(base * Math.max(0.62, scale), minimum, base);
  }

  function drawGroundGlow(ctx, x, y, color, alpha, radius) {
    ctx.save();
    ctx.globalAlpha = alpha;
    const gradient = ctx.createRadialGradient(x, y, 3, x, y, radius);
    gradient.addColorStop(0, color);
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.ellipse(x, y, radius, radius * 0.45, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawSprite(ctx, spriteRef, x, y, size, flash = false) {
    const ref = typeof spriteRef === "string" ? { url: spriteRef, source: null } : spriteRef || {};
    const image = getImage(ref.url);
    const source = ref.source || null;
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,.32)";
    ctx.beginPath();
    ctx.ellipse(x, y + 4, size * 0.34, size * 0.13, 0, 0, Math.PI * 2);
    ctx.fill();
    if (image && image.complete && image.naturalWidth) {
      const sourceWidth = source ? source.width : image.naturalWidth;
      const sourceHeight = source ? source.height : image.naturalHeight;
      const ratio = sourceWidth / sourceHeight;
      const width = ratio >= 1 ? size : size * ratio;
      const height = ratio >= 1 ? size / ratio : size;
      const drawFrame = () => {
        if (source) {
          ctx.drawImage(
            image,
            source.x,
            source.y,
            source.width,
            source.height,
            x - width / 2,
            y - height,
            width,
            height,
          );
        } else {
          ctx.drawImage(image, x - width / 2, y - height, width, height);
        }
      };
      ctx.globalAlpha = 1;
      drawFrame();
      if (flash) {
        ctx.globalCompositeOperation = "screen";
        ctx.globalAlpha = 0.28;
        drawFrame();
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
    const red = parseInt(value.slice(0, 2), 16);
    const green = parseInt(value.slice(2, 4), 16);
    const blue = parseInt(value.slice(4, 6), 16);
    return `rgba(${red},${green},${blue},${clamp(alpha, 0, 1)})`;
  }

  function drawEntities(ctx) {
    const battle = getBattle();
    if (!battle) return;
    const sorted = [...battle.enemies].sort(
      (left, right) => projectCell(left.x, left.y).y - projectCell(right.x, right.y).y,
    );
    for (const enemy of sorted) {
      const point = projectCell(enemy.x, enemy.y);
      const slow = enemy.slowUntil > battle.elapsedMs;
      const hit = enemy.hitFlashUntil > battle.elapsedMs;
      const assetId = enemy.type === "shadow_tide_shade" ? "enemy_shadow_tide_shade" : "enemy_shadow_tide_runner";
      const size = mapSpriteSize(enemy.type === "shadow_tide_shade" ? 58 : 54, 31);
      const phase = battle.elapsedMs / (slow ? 260 : 145) + enemy.animSeed;
      const bob = Math.sin(phase) * (slow ? 1.3 : 3.0);
      const projectedMove = projectVector(enemy.moveDx || 0, enemy.moveDy || 0);
      const moving = Math.hypot(projectedMove.x, projectedMove.y) > 0.08;
      const facing = projectedMove.x < -0.05 ? -1 : 1;
      const lean = moving ? clamp(projectedMove.x * 0.018, -0.16, 0.16) : 0;
      const squash = moving ? Math.sin(phase + Math.PI / 2) * 0.035 : 0;
      drawEnemyMotionTrail(ctx, point, projectedMove, size, slow);
      drawGroundGlow(ctx, point.x, point.y, slow ? "#9edcff" : "#352044", slow ? 0.3 : 0.24, slow ? 38 : 30);
      ctx.save();
      ctx.translate(point.x, point.y + bob);
      ctx.rotate(lean);
      ctx.scale(facing, 1 + squash);
      drawSprite(ctx, mediaSpriteRef(assetId, "unit_sprite", true), 0, 0, size, hit);
      ctx.restore();
      drawEnemyStatus(ctx, point.x, point.y + bob, phase, slow, hit, size);
      drawHealth(ctx, point.x, point.y - 62 + Math.min(0, bob), enemy.hp / enemy.maxHp);
    }
  }

  function drawEffects(ctx) {
    const battle = getBattle();
    if (!battle) return;
    for (const effect of battle.effects) {
      const point = projectCell(effect.x, effect.y);
      const ratio = clamp(effect.age / effect.duration, 0, 1);
      if (effect.type === "ring") {
        ctx.strokeStyle = alphaColor(effect.color, 1 - ratio);
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.ellipse(point.x, point.y, 18 + ratio * 60 * effect.scale, 8 + ratio * 26 * effect.scale, 0, 0, Math.PI * 2);
        ctx.stroke();
      } else if (effect.type === "aura") {
        drawGroundGlow(ctx, point.x, point.y, effect.color, 0.22 * (1 - ratio * 0.35), 64 * effect.scale);
      } else if (effect.type === "burst") {
        ctx.fillStyle = alphaColor(effect.color, 1 - ratio);
        for (let index = 0; index < 10; index += 1) {
          const angle = (index / 10) * Math.PI * 2;
          ctx.beginPath();
          ctx.arc(
            point.x + Math.cos(angle) * ratio * 34 * effect.scale,
            point.y + Math.sin(angle) * ratio * 18 * effect.scale,
            3,
            0,
            Math.PI * 2,
          );
          ctx.fill();
        }
      } else if (effect.type === "muzzle") {
        drawTowerMuzzle(ctx, point.x, point.y, 1 - ratio);
      } else if (effect.type === "beam") {
        const target = projectCell(effect.x2, effect.y2);
        ctx.strokeStyle = alphaColor(effect.color, 1 - ratio);
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(point.x, point.y - 28);
        ctx.lineTo(target.x, target.y - 28);
        ctx.stroke();
      } else if (effect.type === "text") {
        ctx.fillStyle = alphaColor(effect.color, 1 - ratio);
        ctx.font = "700 15px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(effect.text, point.x, point.y - 34 - ratio * 24);
      }
    }
  }

  function drawDragGhost(ctx) {
    const battle = getBattle();
    if (!battle || !battle.draggingTool || !battle.dragPointer || !battle.canvas) return;
    const rect = battle.canvas.getBoundingClientRect();
    const x = battle.dragPointer.x - rect.left;
    const y = battle.dragPointer.y - rect.top;
    if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;
    if (battle.hoverCell) return;
    ctx.save();
    ctx.globalAlpha = 0.72;
    if (battle.draggingTool === "basic") {
      drawSprite(ctx, mediaSpriteRef("defense_basic_lantern_barricade", "defense_sprite", true), x, y + 28, 68);
    } else if (battle.draggingTool === "sample") {
      const spriteRef = resolveToolSpriteRef(battle.draggingTool);
      if (spriteRef) {
        drawSprite(ctx, spriteRef, x, y + 20, 56);
      } else {
        drawGroundGlow(ctx, x, y, "#9edcff", 0.42, 42);
        ctx.strokeStyle = "#9edcff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(x, y, 24, 10, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
    } else {
      const spriteRef = resolveToolSpriteRef(battle.draggingTool);
      if (spriteRef) {
        drawSprite(ctx, spriteRef, x, y + 28, 68);
      } else {
        drawGroundGlow(ctx, x, y, "#8fcf83", 0.32, 72);
      }
    }
    ctx.restore();
  }

  return {
    drawDragGhost,
    drawEffects,
    drawEntities,
    drawGroundGlow,
    drawSprite,
    drawTowerMuzzle,
    mapSpriteSize,
  };
}
