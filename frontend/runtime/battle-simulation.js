export function advanceBattleStep({ battle, dt }) {
  battle.elapsedMs += dt;
  for (const key of Object.keys(battle.cooldowns)) {
    battle.cooldowns[key] = Math.max(0, battle.cooldowns[key] - dt);
  }
  const sampleAsset = battle.config.sample_asset || {};
  const sampleDelivered = !battle.sampleDelivered && battle.elapsedMs >= battle.sampleDeliveryMs;
  if (sampleDelivered) {
    battle.sampleDelivered = true;
    battle.sampleUses = sampleAsset.uses_per_battle || 2;
  }
  return { sampleDelivered };
}

export function spawnEnemies({ battle, routeForSpawn, pathWaypoints }) {
  while (
    battle.spawned < battle.spawnSchedule.length &&
    battle.elapsedMs >= battle.spawnSchedule[battle.spawned].at
  ) {
    const entry = battle.spawnSchedule[battle.spawned];
    const wave = entry.wave;
    const route = routeForSpawn(battle.spawned);
    const points = (route && route.waypoints ? route.waypoints : pathWaypoints()).map((p) => ({
      x: p.x,
      y: p.y,
    }));
    const first = points[0] || { x: 15, y: 4 };
    battle.enemies.push({
      id: `enemy_${battle.spawned}`,
      type: wave.enemy_archetype,
      waveIndex: wave.wave_index,
      routeId: (route || {}).route_id || null,
      x: first.x,
      y: first.y,
      segment: 0,
      hp: wave.durability || 2,
      maxHp: wave.durability || 2,
      speed: wave.speed_cells_per_sec || 1.2,
      slowUntil: 0,
      hitFlashUntil: 0,
      animSeed: battle.spawned * 1.713 + (wave.wave_index || 0) * 0.41,
      birthMs: battle.elapsedMs,
      moveDx: 0,
      moveDy: 0,
    });
    battle.spawned += 1;
  }
}

export function updateEnemies({ battle, dt, enemyWaypoints }) {
  for (const enemy of battle.enemies) {
    const points = enemyWaypoints(enemy);
    if (enemy.hp <= 0) continue;
    const speed = enemy.speed * (enemy.slowUntil > battle.elapsedMs ? 0.42 : 1);
    let remaining = (dt / 1000) * speed;
    const startX = enemy.x;
    const startY = enemy.y;
    while (remaining > 0 && enemy.segment < points.length - 1) {
      const b = points[enemy.segment + 1];
      const dist = Math.hypot(b.x - enemy.x, b.y - enemy.y);
      if (dist <= remaining) {
        enemy.x = b.x;
        enemy.y = b.y;
        enemy.segment += 1;
        remaining -= dist;
      } else {
        enemy.x += ((b.x - enemy.x) / dist) * remaining;
        enemy.y += ((b.y - enemy.y) / dist) * remaining;
        remaining = 0;
      }
    }
    enemy.moveDx = enemy.x - startX;
    enemy.moveDy = enemy.y - startY;
    if (enemy.segment >= points.length - 1) {
      enemy.leaked = true;
      battle.coreHp -= 1;
      battle.leaks += 1;
      if (battle.optionalHp > 1 && battle.leaks % 2 === 1) battle.optionalHp -= 1;
      addFloating(battle, enemy.x, enemy.y, "漏失", "#ff897a");
    }
  }
  battle.enemies = battle.enemies.filter((enemy) => {
    if (enemy.hp <= 0) {
      battle.kills += 1;
      addEffect(battle, "burst", enemy.x, enemy.y, "#777b92", 420);
      return false;
    }
    return !enemy.leaked;
  });
}

export function updateDefenses({ battle }) {
  for (const defense of battle.defenses) {
    if (battle.elapsedMs > defense.until) {
      defense.expired = true;
      continue;
    }
    const attackIntervalMs = Number(defense.attackIntervalMs) > 0 ? Number(defense.attackIntervalMs) : 760;
    const attackRange = Number(defense.range) > 0 ? Number(defense.range) : 2.6;
    const damage = Number(defense.damage) > 0 ? Number(defense.damage) : 1;
    const color = defense.attackColor || "#ffd37a";
    if (battle.elapsedMs < defense.shotAt + attackIntervalMs) continue;
    const target = nearestEnemy({ battle, x: defense.x, y: defense.y, radius: attackRange });
    if (!target) continue;
    defense.shotAt = battle.elapsedMs;
    target.hp -= damage;
    target.hitFlashUntil = battle.elapsedMs + 160;
    addEffect(battle, "muzzle", defense.x, defense.y, color, 220, 0.75);
    addBeam(battle, defense.x, defense.y, target.x, target.y, color);
    addEffect(battle, "burst", target.x, target.y, color, 240, 0.55);
  }
  battle.defenses = battle.defenses.filter((item) => !item.expired);
}

export function updateTraps({ battle }) {
  for (const trap of battle.traps) {
    if (trap.expired) continue;
    const radius = Number(trap.radius) > 0 ? Number(trap.radius) : 1.65;
    const triggerRadius = Math.max(0.6, radius * 0.48);
    const activeDurationMs =
      Number(trap.activeDurationMs) > 0 ? Number(trap.activeDurationMs) : 7800;
    const slowDurationMs = Number(trap.slowDurationMs) > 0 ? Number(trap.slowDurationMs) : 900;
    const color = trap.color || "#9edcff";
    if (trap.armed) {
      const enemy = nearestEnemy({ battle, x: trap.x, y: trap.y, radius: triggerRadius });
      if (enemy) {
        trap.armed = false;
        trap.activeUntil = battle.elapsedMs + activeDurationMs;
        addEffect(battle, "ring", trap.x, trap.y, color, 1100, 1.8);
        addEffect(battle, "aura", trap.x, trap.y, color, activeDurationMs, 1.5);
        addFloating(battle, trap.x, trap.y, "迟滞", "#b8f1ff");
      }
    }
    if (!trap.armed && battle.elapsedMs <= trap.activeUntil) {
      for (const enemy of battle.enemies) {
        if (Math.hypot(enemy.x - trap.x, enemy.y - trap.y) < radius) {
          enemy.slowUntil = Math.max(enemy.slowUntil, battle.elapsedMs + slowDurationMs);
        }
      }
    }
    if (!trap.armed && battle.elapsedMs > trap.activeUntil) {
      trap.expired = true;
    }
  }
  battle.traps = battle.traps.filter((trap) => !trap.expired);
}

export function nearestEnemy({ battle, x, y, radius }) {
  let best = null;
  let bestDist = Infinity;
  for (const enemy of battle.enemies) {
    const dist = Math.hypot(enemy.x - x, enemy.y - y);
    if (dist < radius && dist < bestDist) {
      best = enemy;
      bestDist = dist;
    }
  }
  return best;
}

export function addEffect(battle, type, x, y, color, duration, scale = 1) {
  battle.effects.push({
    type,
    x,
    y,
    color,
    duration,
    scale,
    age: 0,
  });
}

export function addBeam(battle, x1, y1, x2, y2, color) {
  battle.effects.push({
    type: "beam",
    x: x1,
    y: y1,
    x2,
    y2,
    color,
    duration: 130,
    age: 0,
  });
}

export function addFloating(battle, x, y, text, color) {
  battle.effects.push({
    type: "text",
    x,
    y,
    text,
    color,
    duration: 900,
    age: 0,
  });
}

export function updateEffects({ battle, dt }) {
  for (const effect of battle.effects) effect.age += dt;
  battle.effects = battle.effects.filter((effect) => effect.age < effect.duration);
}

export function resolveBattleOutcome({ battle, flowVisualSmoke }) {
  if (!battle || battle.finishing) return null;
  if (battle.coreHp <= 0) return "defeat";
  const allSpawned = battle.spawned >= battle.spawnSchedule.length;
  if (allSpawned && battle.enemies.length === 0 && battle.elapsedMs > 5000) {
    return battle.coreHp > 0 ? "victory" : "defeat";
  }
  if (flowVisualSmoke && battle.elapsedMs > 9000) {
    return battle.coreHp > 0 ? "victory" : "defeat";
  }
  return null;
}
