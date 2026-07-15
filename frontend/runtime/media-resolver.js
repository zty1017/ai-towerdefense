import { STATIC_ASSET_PREFIXES } from "./content-registry.js";

export function manifestItems(manifest) {
  return Array.isArray(manifest && manifest.items) ? manifest.items : [];
}

export function resolveStaticAssetUrl(url, prefixes = STATIC_ASSET_PREFIXES) {
  return prefixes.reduce(
    (resolved, [pattern, replacement]) => resolved.replace(pattern, replacement),
    url,
  );
}
