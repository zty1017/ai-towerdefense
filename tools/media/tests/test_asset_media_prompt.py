import json
import unittest
from pathlib import Path

from tools.media import asset_media_prompt


ROOT = Path(__file__).resolve().parents[3]


def _asset(filename: str) -> dict:
    path = ROOT / "examples" / "compiled_assets" / filename
    return json.loads(path.read_text(encoding="utf-8"))


class AssetMediaPromptTest(unittest.TestCase):
    def test_default_roles_are_clean_frontend_assets(self) -> None:
        tower = _asset("ash_burst_lantern.compiled_asset.json")
        support = _asset("mirror_lure_trap.compiled_asset.json")
        intel = _asset("east_dark_echo_survey.compiled_asset.json")
        mod = _asset("overload_chain_mod.compiled_asset.json")

        self.assertEqual(asset_media_prompt.default_media_roles(tower), ["icon", "tower_sprite"])
        self.assertEqual(asset_media_prompt.default_media_roles(support), ["icon", "ui_card"])
        self.assertEqual(asset_media_prompt.default_media_roles(intel), ["icon", "ui_card"])
        self.assertEqual(asset_media_prompt.default_media_roles(mod), ["icon", "ui_card"])

    def test_clean_role_prompts_do_not_embed_world_text_or_scene_roles(self) -> None:
        tower = _asset("ash_burst_lantern.compiled_asset.json")
        prompt = asset_media_prompt.build_prompt_for_role(tower, "tower_sprite")

        self.assertIn("single isolated subject only", prompt)
        self.assertIn("solid pure white matte background", prompt)
        self.assertIn("no enemies", prompt)
        self.assertIn("effects are separate frontend overlays", prompt)
        self.assertNotIn("灯灰爆鸣塔", prompt)
        self.assertNotIn("敌人聚集", prompt)
        self.assertNotIn("shockwave expanding", prompt)

    def test_clean_ui_card_prompt_is_not_a_card_frame_request(self) -> None:
        intel = _asset("east_dark_echo_survey.compiled_asset.json")
        prompt = asset_media_prompt.build_prompt_for_role(intel, "ui_card")

        self.assertIn("not a card UI", prompt)
        self.assertIn("no UI frame", prompt)
        self.assertIn("no card border", prompt)
        self.assertIn("no writing or map labels", prompt)
        self.assertNotIn("东暗回声测记", prompt)
        self.assertNotIn("revealing enemy path", prompt)


if __name__ == "__main__":
    unittest.main()
