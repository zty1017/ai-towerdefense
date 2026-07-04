import json
import tempfile
import unittest
from pathlib import Path

from tools.media import png_pipeline, runtime_readiness


def _cutout_sprite() -> png_pipeline.PngImage:
    image = png_pipeline.PngImage(32, 32, bytearray(32 * 32 * 4))
    for y in range(8, 28):
        for x in range(10, 22):
            idx = (y * image.width + x) * 4
            image.pixels[idx : idx + 4] = bytes([180, 40, 60, 255])
    return image


def _opaque_sprite() -> png_pipeline.PngImage:
    return png_pipeline.PngImage(32, 32, bytearray([220, 220, 220, 255] * 32 * 32))


class RuntimeReadinessTest(unittest.TestCase):
    def test_cutout_sprite_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            published = root / "published"
            sprite = published / "tower.png"
            atlas = published / "atlas.png"
            descriptor = published / "atlas.json"
            png_pipeline.write_png(sprite, _cutout_sprite())
            png_pipeline.write_png(atlas, _cutout_sprite())
            descriptor.write_text(json.dumps({"frames": {}}), encoding="utf-8")
            manifest = {
                "media_layer": "published_media",
                "published_media": [
                    {
                        "stable_internal_id": "tower",
                        "media_role": "tower_sprite",
                        "url": "/assets/generated/tower.png",
                        "file": "published/tower.png",
                        "width": 32,
                        "height": 32,
                        "sha256": runtime_readiness.sha256_file(sprite),
                        "anchor": {"preset": "bottom_center", "x": 0.5, "y": 1.0},
                        "texture_key": "atlas",
                        "atlas_frame": {"x": 0, "y": 0, "w": 32, "h": 32},
                    }
                ],
                "atlas": {
                    "texture_key": "atlas",
                    "image": "/assets/generated/atlas.png",
                    "descriptor": "/assets/generated/atlas.json",
                    "image_file": "published/atlas.png",
                    "descriptor_file": "published/atlas.json",
                },
            }
            report = runtime_readiness.assess_runtime_readiness(manifest, artifact_dir=root)
            self.assertEqual(report["status"], "passed")

    def test_opaque_sprite_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            published = root / "published"
            sprite = published / "tower.png"
            atlas = published / "atlas.png"
            descriptor = published / "atlas.json"
            png_pipeline.write_png(sprite, _opaque_sprite())
            png_pipeline.write_png(atlas, _opaque_sprite())
            descriptor.write_text(json.dumps({"frames": {}}), encoding="utf-8")
            manifest = {
                "media_layer": "published_media",
                "published_media": [
                    {
                        "stable_internal_id": "tower",
                        "media_role": "tower_sprite",
                        "url": "/assets/generated/tower.png",
                        "file": "published/tower.png",
                        "width": 32,
                        "height": 32,
                        "sha256": runtime_readiness.sha256_file(sprite),
                        "anchor": {"preset": "bottom_center", "x": 0.5, "y": 1.0},
                        "texture_key": "atlas",
                        "atlas_frame": {"x": 0, "y": 0, "w": 32, "h": 32},
                    }
                ],
                "atlas": {
                    "texture_key": "atlas",
                    "image": "/assets/generated/atlas.png",
                    "descriptor": "/assets/generated/atlas.json",
                    "image_file": "published/atlas.png",
                    "descriptor_file": "published/atlas.json",
                },
            }
            report = runtime_readiness.assess_runtime_readiness(manifest, artifact_dir=root)
            self.assertEqual(report["status"], "failed")
            self.assertIn("sprite_lacks_transparent_background", report["items"][0]["issues"])

    def test_empty_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = runtime_readiness.assess_runtime_readiness(
                {"media_layer": "published_media", "published_media": []},
                artifact_dir=Path(tmp),
            )
            self.assertEqual(report["status"], "failed")
            self.assertIn("published_media_empty", report["manifest_issues"])


if __name__ == "__main__":
    unittest.main()
