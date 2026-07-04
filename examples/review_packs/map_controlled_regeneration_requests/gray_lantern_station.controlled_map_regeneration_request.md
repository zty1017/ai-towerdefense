# Controlled Map Regeneration Request: gray_lantern_station

## Reference Image

- PNG: `game_data/media/map_visual_reference/topology_control_sketches/gray_lantern_station.topology_control_sketch.png`
- SVG review: `game_data/media/map_visual_reference/topology_control_sketches/gray_lantern_station.topology_control_sketch.svg`

Attach the PNG as a reference / control image when the provider supports it.

## Provider Instruction

```text
Use the attached topology control sketch PNG as the exact composition reference.
Transform it into a natural, polished, hand-painted 2D / pseudo-3D tower-defense battlefield background.
The final image must not show the control sketch style; it should look like a finished game map.

World and scene brief:
Wide 16:9 empty fantasy lantern frontier map. The station/outpost must be a clear protected objective near the left upper side, with one natural road entering from the right and curving toward it. Use flat empty build clearings beside the road. No arrows, no units, no projectiles, no deployed towers, no UI.

Topology that must remain readable:
- grid: {'cell_size': 64, 'height_cells': 9, 'projection': 'pseudo3d_oblique', 'width_cells': 16}
- route count: 1
- build pad count target: 12
- objective count target: 2
- spawn point count target: 1

Hard output requirements:
- wide 16:9 full-frame battlefield background, no UI, no border, no text
- paths, objectives, and flat empty build pads must align visually with the reference sketch
- build pads should be terrain-integrated clearings or flush stone foundations, not towers
- enemy entrances and protected objectives should be implied by terrain landmarks, not arrows
- leave enough readable ground around routes and pads for runtime overlays

Forbidden elements:
- no UI, frame, panel, card, menu, icon bar, watermark, logo, or text
- no arrows, chevrons, direction marks, labels, numbers, or grid lines
- no enemies, NPCs, human figures, monsters, animals, projectiles, explosions, or combat effects
- no deployed towers, turrets, watchtowers, castles, large central monument towers, or raised build structures
- no asphalt highways, lane markings, sci-fi HUD overlays, or technical diagram style
```

## Text-Only Fallback

```text
Wide 16:9 empty fantasy lantern frontier map. The station/outpost must be a clear protected objective near the left upper side, with one natural road entering from the right and curving toward it. Use flat empty build clearings beside the road. No arrows, no units, no projectiles, no deployed towers, no UI.

Additional text-only topology constraints:
- preserve 1 readable route(s)
- provide roughly 12 flat empty build pads near routes
- show 2 protected objective landmark(s)
- show 1 enemy entrance area(s) at map edges
- no UI, no arrows, no labels, no enemies, no placed towers, no combat effects

Note: text-only fallback is lower confidence than using the control sketch reference image.
```

## Review Policy

- This request is review-only.
- Generated output must re-enter candidate, alignment, overlay, visual, and promotion gates.
- Do not update MapRuntimePackage or published visual layers directly.
