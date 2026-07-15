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


def _sprite_with_noise() -> png_pipeline.PngImage:
    image = png_pipeline.PngImage(16, 16, bytearray(16 * 16 * 4))
    for y in range(4, 12):
        for x in range(5, 11):
            idx = (y * image.width + x) * 4
            image.pixels[idx : idx + 4] = bytes([200, 32, 48, 255])
    for y in range(1, 3):
        for x in range(1, 3):
            idx = (y * image.width + x) * 4
            image.pixels[idx : idx + 4] = bytes([20, 20, 20, 255])
    return image


class PngPipelineTest(unittest.TestCase):
    def test_center_crop_to_ratio_crops_square_to_widescreen(self) -> None:
        image = png_pipeline.PngImage(8, 8, bytearray([255, 0, 0, 255] * 64))

        cropped = png_pipeline.center_crop_to_ratio(image, 16 / 9)

        self.assertEqual(cropped.width, 8)
        self.assertEqual(cropped.height, 4)
        self.assertEqual(len(cropped.pixels), 8 * 4 * 4)

    def test_center_crop_fraction_extracts_inner_widescreen_sample(self) -> None:
        image = png_pipeline.PngImage(12, 12, bytearray([255, 0, 0, 255] * 144))

        cropped = png_pipeline.center_crop_fraction(image, 0.75, ratio=2.0)

        self.assertEqual((cropped.width, cropped.height), (9, 4))

    def test_mirrored_seamless_tile_matches_opposite_edges(self) -> None:
        pixels = bytearray()
        for y in range(4):
            for x in range(8):
                pixels.extend((x * 20, y * 30, 0, 255))
        tiled = png_pipeline.mirrored_seamless_tile(
            png_pipeline.PngImage(8, 4, pixels)
        )

        self.assertEqual((tiled.width, tiled.height), (8, 4))
        for y in range(tiled.height):
            left = (y * tiled.width) * 4
            right = (y * tiled.width + tiled.width - 1) * 4
            self.assertEqual(tiled.pixels[left : left + 4], tiled.pixels[right : right + 4])
        for x in range(tiled.width):
            top = x * 4
            bottom = ((tiled.height - 1) * tiled.width + x) * 4
            self.assertEqual(tiled.pixels[top : top + 4], tiled.pixels[bottom : bottom + 4])

    def test_edge_blended_seamless_tile_matches_edges_without_mirroring_center(self) -> None:
        pixels = bytearray()
        for y in range(10):
            for x in range(20):
                pixels.extend((x * 10, y * 20, (x + y) * 5, 255))
        source = png_pipeline.PngImage(20, 10, pixels)

        tiled = png_pipeline.edge_blended_seamless_tile(source, blend_fraction=0.2)

        for y in range(tiled.height):
            left = (y * tiled.width) * 4
            right = (y * tiled.width + tiled.width - 1) * 4
            self.assertEqual(tiled.pixels[left : left + 4], tiled.pixels[right : right + 4])
        for x in range(tiled.width):
            top = x * 4
            bottom = ((tiled.height - 1) * tiled.width + x) * 4
            self.assertEqual(tiled.pixels[top : top + 4], tiled.pixels[bottom : bottom + 4])
        center = ((tiled.height // 2) * tiled.width + tiled.width // 2) * 4
        self.assertEqual(tiled.pixels[center : center + 4], source.pixels[center : center + 4])

    def test_keep_largest_alpha_component_removes_detached_noise(self) -> None:
        image = _sprite_with_noise()
        cleaned = png_pipeline.keep_largest_alpha_component(image)

        self.assertEqual(cleaned.pixels[(1 * cleaned.width + 1) * 4 + 3], 0)
        self.assertEqual(cleaned.pixels[(6 * cleaned.width + 6) * 4 + 3], 255)

    def test_remove_small_alpha_components_keeps_large_detached_parts(self) -> None:
        image = png_pipeline.PngImage(8, 8, bytearray(8 * 8 * 4))
        for y in range(1, 4):
            for x in range(1, 4):
                idx = (y * image.width + x) * 4
                image.pixels[idx : idx + 4] = bytes([200, 30, 30, 255])
        for y in range(5, 7):
            for x in range(5, 7):
                idx = (y * image.width + x) * 4
                image.pixels[idx : idx + 4] = bytes([30, 30, 200, 255])
        image.pixels[(0 * image.width + 7) * 4 : (0 * image.width + 7) * 4 + 4] = bytes([0, 0, 0, 255])

        cleaned = png_pipeline.remove_small_alpha_components(image, min_pixels=4)

        self.assertEqual(cleaned.pixels[(2 * cleaned.width + 2) * 4 + 3], 255)
        self.assertEqual(cleaned.pixels[(6 * cleaned.width + 6) * 4 + 3], 255)
        self.assertEqual(cleaned.pixels[(0 * cleaned.width + 7) * 4 + 3], 0)

    def test_clear_transparent_rgb_zeroes_hidden_color_channels(self) -> None:
        image = png_pipeline.PngImage(1, 1, bytearray([255, 255, 255, 0]))

        cleaned = png_pipeline.clear_transparent_rgb(image)

        self.assertEqual(list(cleaned.pixels), [0, 0, 0, 0])

    def test_edge_matte_removal_preserves_light_subject_interior(self) -> None:
        image = png_pipeline.PngImage(5, 5, bytearray([255, 255, 255, 255] * 25))
        for y in range(1, 4):
            for x in range(1, 4):
                idx = (y * image.width + x) * 4
                image.pixels[idx : idx + 4] = bytes([20, 20, 20, 255])
        center = (2 * image.width + 2) * 4
        image.pixels[center : center + 4] = bytes([232, 232, 232, 255])

        cleaned = png_pipeline.remove_edge_matte_background(image, threshold=40)

        self.assertEqual(cleaned.pixels[3], 0)
        self.assertEqual(cleaned.pixels[center + 3], 255)

    def test_near_white_island_removal_keeps_colored_highlight(self) -> None:
        image = png_pipeline.PngImage(8, 4, bytearray(8 * 4 * 4))
        for y in range(1, 3):
            for x in range(1, 3):
                idx = (y * image.width + x) * 4
                image.pixels[idx : idx + 4] = bytes([252, 252, 250, 255])
            for x in range(5, 7):
                idx = (y * image.width + x) * 4
                image.pixels[idx : idx + 4] = bytes([255, 238, 180, 255])

        cleaned = png_pipeline.remove_near_white_background_islands(image, min_pixels=4)

        self.assertEqual(cleaned.pixels[(1 * cleaned.width + 1) * 4 + 3], 0)
        self.assertEqual(cleaned.pixels[(1 * cleaned.width + 5) * 4 + 3], 255)

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
