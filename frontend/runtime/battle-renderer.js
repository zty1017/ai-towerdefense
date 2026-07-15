export function drawBattleFrame({
  battle,
  drawBackdrop,
  drawBuildableTerraces,
  drawSlotAccessTrails,
  drawPath,
  drawMapRuntimeStrongSemantics,
  drawDeployHints,
  drawWorldObjects,
  drawSpawnMarkers,
  drawEntities,
  drawEffects,
  drawDragGhost,
}) {
  const ctx = battle.ctx;
  const m = battle.metrics;
  if (!ctx || !m) return;
  ctx.clearRect(0, 0, m.width, m.height);
  const layeredBackdrop = drawBackdrop(ctx, m);
  if (!layeredBackdrop) {
    drawBuildableTerraces(ctx);
    drawSlotAccessTrails(ctx);
    drawPath(ctx);
    drawMapRuntimeStrongSemantics(ctx);
  }
  drawDeployHints(ctx, { layeredBackdrop });
  drawWorldObjects(ctx, { layeredBackdrop });
  if (!layeredBackdrop) drawSpawnMarkers(ctx);
  drawEntities(ctx);
  drawEffects(ctx);
  drawDragGhost(ctx);
}
