import tempfile
import unittest
from pathlib import Path

from tools.media import png_pipeline


def _sample_sprite() -> png_pipeline.PngImage:
    image = png_pipeline.PngImage(16, 16, bytearray([255, 255, 255, 255] * 16 * 16))
    for y in range(4, 12):
        for x in range(5, 11):
            idx = (y * image.width + x) * 4
            image.pixels[idx : idx + 4] = bytes([200, 32, 48, 255])
    return image


class PngPipelineTest(unittest.TestCase):
    def test_png_pipeline_builds_cutout_and_atlas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "source.png"
            png_pipeline.write_png(source_path, _sample_sprite())

            source = png_pipeline.read_png(source_path)
            cutout = png_pipeline.remove_matte_background(source, threshold=4)
            alpha = cutout.pixels[3::4]
            self.assertGreater(alpha.count(0), 0)
            self.assertGreater(alpha.count(255), 0)

            cropped = png_pipeline.crop_and_pad(cutout, padding=2)
            self.assertEqual(cropped.width, 10)
            self.assertEqual(cropped.height, 12)

            normalized = png_pipeline.normalize_canvas(cropped, square=True, align="bottom_center")
            self.assertEqual(normalized.width, 12)
            self.assertEqual(normalized.height, 12)

            processed_path = tmp_path / "processed.png"
            png_pipeline.write_png(processed_path, normalized)
            atlas, descriptor = png_pipeline.pack_horizontal(
                [
                    (
                        "asset_test_sprite",
                        processed_path,
                        {
                            "media_role": "tower_sprite",
                            "anchor": {"preset": "bottom_center", "x": 0.5, "y": 1.0},
                        },
                    )
                ]
            )

            self.assertEqual(atlas.width, 12)
            self.assertEqual(atlas.height, 12)
            self.assertEqual(
                descriptor["frames"]["asset_test_sprite"]["frame"],
                {"x": 0, "y": 0, "w": 12, "h": 12},
            )


if __name__ == "__main__":
    unittest.main()
