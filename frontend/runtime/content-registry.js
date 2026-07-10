export const NODE_ID = "gray_lantern_station";

export const STATIC_PATHS = {
  pack: "/examples/frontend_mock/frontend_mock_pack.v0.1.json",
  runtimeKit: "/examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json",
  mediaManifest: "/game_data/media/frontend_mock/frontend_media_manifest.v0.1.json",
  mediaAtlasManifest: "/game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json",
  runtimeMediaManifest:
    "/game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
  runtimeArtAtlasManifest:
    "/game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
  activatedRuntimeBundle:
    "/examples/frontend_runtime/activated_runtime_bundle.mvp.v0.1.json",
  mapVisualManifest:
    "/game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json",
  mapComponentManifest:
    "/game_data/media/map_components/map_component_media_manifest.v0.1.json",
  strategicMapMarkerManifest:
    "/game_data/media/strategic_map_markers/strategic_map_marker_media_manifest.v0.1.json",
  opening: "/content/worldbooks/long_night_lanterns/opening.json",
  worldConfig: "/content/worldbooks/long_night_lanterns/world_instance_config.json",
  map: "/game_data/demo/initial_map.json",
  briefing: "/game_data/demo/first_crisis_node.json",
  battleConfig: "/game_data/demo/first_battle_config.json",
  mapRuntimePackage:
    "/examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json",
  mapStylePack:
    "/examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json",
  mapRenderPlan:
    "/examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json",
  mapSemanticVisualConsistencyReport:
    "/examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json",
};

export const STATIC_NODE_PATHS = {
  gray_lantern_station: {
    displayName: "灰灯驿站",
    briefing: "/game_data/demo/first_crisis_node.json",
    battleConfig: "/game_data/demo/first_battle_config.json",
    mapRuntimePackage:
      "/examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json",
    mapStylePack:
      "/examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json",
    mapRenderPlan:
      "/examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json",
    layeredMapVisualPackage:
      "/game_data/media/layered_maps/gray_lantern_station/layered_map_visual_package.v0.1.json",
    mapSemanticVisualConsistencyReport:
      "/examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json",
    suggestedInput: "我想做一个能拖慢影潮的临时装置。",
  },
  lamp_wick_store: {
    displayName: "灯芯仓",
    battleConfig: "/game_data/demo/wick_store_pressure_battle_config.json",
    mapRuntimePackage:
      "/examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json",
    mapStylePack:
      "/examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json",
    mapRenderPlan:
      "/examples/map_render_plans/mvp_wick_store_pressure.procedural_map_render_plan.json",
    layeredMapVisualPackage:
      "/game_data/media/layered_maps/lamp_wick_store/layered_map_visual_package.v0.1.json",
    mapSemanticVisualConsistencyReport:
      "/examples/semantic_visual_consistency_reports/mvp_wick_store_pressure.semantic_visual_consistency_report.json",
    suggestedInput: "我想把灯灰和导线做成能逼退密集影潮的临时灯具。",
  },
  old_signal_tower: {
    displayName: "旧信号塔",
    battleConfig: "/game_data/demo/old_signal_tower_pressure_battle_config.json",
    mapRuntimePackage:
      "/examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json",
    mapStylePack:
      "/examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json",
    mapRenderPlan:
      "/examples/map_render_plans/mvp_old_signal_tower_pressure.procedural_map_render_plan.json",
    layeredMapVisualPackage:
      "/game_data/media/layered_maps/old_signal_tower/layered_map_visual_package.v0.1.json",
    mapSemanticVisualConsistencyReport:
      "/examples/semantic_visual_consistency_reports/mvp_old_signal_tower_pressure.semantic_visual_consistency_report.json",
    suggestedInput: "我想让信号塔的回光形成短暂屏障，争取修复时间。",
  },
};

export const STATIC_CAMPAIGN_STEPS = [
  {
    stage_index: 1,
    node_id: "gray_lantern_station",
    display_name: "灰灯驿站",
    kind: "battle",
    interlude:
      "首战数据被送回中枢，补线人和北路斥候加入评估，灯芯仓压力节点被打开。",
    next_state:
      "/examples/run_world_states/demo_after_stage_03_northern_road.run_world_state.json",
  },
  {
    stage_index: 2,
    node_id: "lamp_wick_store",
    display_name: "灯芯仓",
    kind: "battle",
    interlude: "灯芯仓守住后，辉晶样品让旧信号塔回光变成可处理的下一处危机。",
    next_state:
      "/examples/run_world_states/demo_after_stage_05_old_signal_tower.run_world_state.json",
  },
  {
    stage_index: 3,
    node_id: "old_signal_tower",
    display_name: "旧信号塔",
    kind: "battle",
    interlude: "旧塔短暂稳定，北路分潮线被照出，本章演示流程完成。",
    next_state:
      "/examples/run_world_states/demo_after_stage_06_signal_resonance.run_world_state.json",
  },
];

export const STATIC_CAMPAIGN_STATE_PATHS = [
  "/examples/run_world_states/demo_initial.run_world_state.json",
  "/examples/run_world_states/demo_after_stage_03_northern_road.run_world_state.json",
  "/examples/run_world_states/demo_after_stage_05_old_signal_tower.run_world_state.json",
  "/examples/run_world_states/demo_after_stage_06_signal_resonance.run_world_state.json",
];

export const STATIC_ASSET_PREFIXES = [
  [
    /^\/assets\/frontend_runtime_mock\/processed\//,
    "/game_data/media/frontend_runtime_mock/processed/",
  ],
  [
    /^\/assets\/frontend_runtime_mock\/generated\//,
    "/game_data/media/frontend_runtime_mock/generated/",
  ],
  [
    /^\/assets\/frontend_runtime_mock\/atlas_frames\//,
    "/game_data/media/frontend_runtime_mock/atlas_frames/",
  ],
  [
    /^\/assets\/frontend_runtime_mock\/atlas_sheets\//,
    "/game_data/media/frontend_runtime_mock/atlas_sheets/",
  ],
  [/^\/assets\/frontend_mock\/processed\//, "/game_data/media/frontend_mock/processed/"],
  [/^\/assets\/frontend_mock\/generated\//, "/game_data/media/frontend_mock/generated/"],
  [/^\/assets\/frontend_mock\/atlas_frames\//, "/game_data/media/frontend_mock/atlas_frames/"],
  [/^\/assets\/frontend_mock\/atlas_sheets\//, "/game_data/media/frontend_mock/atlas_sheets/"],
  [/^\/assets\/layered_maps\//, "/game_data/media/layered_maps/"],
  [/^\/assets\/map_visual_reference\//, "/game_data/media/map_visual_reference/"],
  [/^\/assets\/map_components\//, "/game_data/media/map_components/"],
  [/^\/assets\/strategic_map_markers\//, "/game_data/media/strategic_map_markers/"],
];

export const DEFAULT_WORLD_CONFIG = {
  worldbook_template_id: "long_night_lanterns",
  worldbook_display_name: "长夜灯火",
  visual_style_id: "old_chinese_lantern_frontier_pseudo3d",
  visual_style_display_name: "灯塬旧朝·伪三维",
  creativity_mode: {
    selected: "stable",
    options: [
      {
        id: "stable",
        display_name: "稳健",
        summary: "倾向使用已验证的灯塬工艺，方案更稳定但变化较少。",
      },
      {
        id: "experimental",
        display_name: "实验性",
        summary: "允许尝试非常规改写与稀疏配比，可能产出意外样品。",
      },
    ],
  },
  player_origin: {
    selected: "lampwright_apprentice",
    options: [
      {
        id: "lampwright_apprentice",
        display_name: "守灯技师",
        summary: "熟悉灯台、灯坊与灯火工艺，善于在余灯中枢附近进行临时改造。",
      },
      {
        id: "flow_engineer",
        display_name: "流亡工程师",
        summary: "曾维护远方补给线，对导线与输送装置更有心得。",
      },
      {
        id: "signal_dispatcher",
        display_name: "见习调度员",
        summary: "负责观测影潮边缘与驿站信标，擅长判断敌潮动向。",
      },
    ],
  },
  recommended_defaults: {
    creativity_mode: "stable",
    player_origin: "lampwright_apprentice",
    visual_style_id: "old_chinese_lantern_frontier_pseudo3d",
  },
};
