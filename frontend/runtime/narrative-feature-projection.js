function asList(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function createNarrativeFeatureProjection({ getSurfaceContributions } = {}) {
  if (typeof getSurfaceContributions !== "function") {
    throw new TypeError("createNarrativeFeatureProjection requires getSurfaceContributions");
  }

  function queuedBeats(nodeId = "") {
    return asList(getSurfaceContributions(nodeId))
      .filter((item) => item && item.kind === "narrative_beat")
      .map((item) => ({ ...item, payload: asObject(item.payload) }));
  }

  function battleIntro(nodeId, fallback) {
    const targeted = queuedBeats(nodeId).find(
      (item) => item.targetNodeId && item.targetNodeId === nodeId,
    );
    if (!targeted) return fallback;
    const payload = targeted.payload;
    return {
      name: payload.speaker_name || payload.speaker_id || fallback.name,
      line: payload.text || fallback.line,
      portraitId: payload.portrait_asset_id || fallback.portraitId,
      contributionId: targeted.contributionId,
    };
  }

  return { battleIntro, queuedBeats };
}
