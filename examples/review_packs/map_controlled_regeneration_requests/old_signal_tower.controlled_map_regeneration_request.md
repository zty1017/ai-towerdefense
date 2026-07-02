# Controlled Map Regeneration Request: old_signal_tower

## Reference Image

- PNG: `game_data/media/map_visual_reference/topology_control_sketches/old_signal_tower.topology_control_sketch.png`
- SVG review: `game_data/media/map_visual_reference/topology_control_sketches/old_signal_tower.topology_control_sketch.svg`

Attach the PNG as a reference / control image when the provider supports it.

## Provider Instruction

```text
Use the attached topology control sketch PNG as the exact composition reference.
Transform it into a natural, polished, hand-painted 2D / pseudo-3D tower-defense battlefield background.
The final image must not show the control sketch style; it should look like a finished game map.

World and scene brief:
Wide 16:9 hand-painted fantasy strategy game terrain background, high three-quarter camera, empty playable map art, no UI. Scene: cold mountain ridge with ruined signal tower structures, snow patches, blue-violet echo light, broken antenna debris. Preserve gameplay topology: the protected core objective must read visually near the left-side lower-mid approach area, not as a huge centered tower; two enemy routes should enter from the right side and curve naturally toward the left-side objective. Show visible dirt or ridge paths matching those routes. Place empty flat build clearings distributed along the two routes, not clustered only in the top-right. No arrows, no text, no units, no projectiles, no UI, no deployed towers, no road lane markings. The map must be ready for runtime overlays. Repair pass v2: reduce the signal tower landmark to a small or medium ruined relay landmark, never a dominant central monument, occupying less than 15 percent of image height. Place the protected objective landmark on the left lower-mid ridge as a compact broken relay base or bunker, with routes curving around it instead of crossing through or under it. Keep the central combat field open. Remove all people, silhouettes, bodies, camp props that read as characters, vehicles, weapons, flags, UI-like signs, and tiny story props. Use only terrain, snow, rocks, fences, broken antenna debris as scenery, dirt/snow paths, and flat empty build pads.

Topology that must remain readable:
- grid: {'cell_size': 64, 'height_cells': 10, 'projection': 'pseudo3d_oblique', 'width_cells': 18}
- route count: 2
- build pad count target: 12
- objective count target: 3
- spawn point count target: 2

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
Wide 16:9 hand-painted fantasy strategy game terrain background, high three-quarter camera, empty playable map art, no UI. Scene: cold mountain ridge with ruined signal tower structures, snow patches, blue-violet echo light, broken antenna debris. Preserve gameplay topology: the protected core objective must read visually near the left-side lower-mid approach area, not as a huge centered tower; two enemy routes should enter from the right side and curve naturally toward the left-side objective. Show visible dirt or ridge paths matching those routes. Place empty flat build clearings distributed along the two routes, not clustered only in the top-right. No arrows, no text, no units, no projectiles, no UI, no deployed towers, no road lane markings. The map must be ready for runtime overlays. Repair pass v2: reduce the signal tower landmark to a small or medium ruined relay landmark, never a dominant central monument, occupying less than 15 percent of image height. Place the protected objective landmark on the left lower-mid ridge as a compact broken relay base or bunker, with routes curving around it instead of crossing through or under it. Keep the central combat field open. Remove all people, silhouettes, bodies, camp props that read as characters, vehicles, weapons, flags, UI-like signs, and tiny story props. Use only terrain, snow, rocks, fences, broken antenna debris as scenery, dirt/snow paths, and flat empty build pads.

Additional text-only topology constraints:
- preserve 2 readable route(s)
- provide roughly 12 flat empty build pads near routes
- show 3 protected objective landmark(s)
- show 2 enemy entrance area(s) at map edges
- no UI, no arrows, no labels, no enemies, no placed towers, no combat effects

Note: text-only fallback is lower confidence than using the control sketch reference image.
```

## Review Policy

- This request is review-only.
- Generated output must re-enter candidate, alignment, overlay, visual, and promotion gates.
- Do not update MapRuntimePackage or published visual layers directly.
