"""Behavioral checks for the accepted subjective profile."""

import colorsys
import unittest

from model import NEUTRAL_BLEND_END, NEUTRAL_SATURATION, Profile


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.model = Profile()

    def test_anchors_and_black(self):
        self.assertEqual(self.model.command("#000000"), "#000000")
        self.assertEqual(self.model.command("#FFFFFF"), "#FFE080")
        for row in self.model.data["pastels"]:
            self.assertEqual(self.model.command(row["target"]), row["command"])

    def test_near_neutral_continuity(self):
        neutral = self.model.predict("#808080")
        for color in ("#818080", "#808180", "#808081"):
            self.assertLess(max(abs(a - b) for a, b in zip(neutral, self.model.predict(color))), .025)

    def test_very_light_neutrals_use_white_anchor(self):
        for color in ("#EAF6FF", "#FFF6EA", "#F6FFEA"):
            self.assertEqual(self.model.command(color), "#FFE080")

    def test_wraparound(self):
        for saturation in (.01, .3, .6, 1):
            commands = []
            for hue in (.00001, .99999):
                color = "#" + "".join(f"{round(c * 255):02X}" for c in colorsys.hsv_to_rgb(hue, saturation, 1))
                commands.append(self.model.predict(color))
            self.assertLess(max(abs(a - b) for a, b in zip(*commands)), .01)

    def test_bounds_and_determinism(self):
        for red in range(0, 256, 17):
            for green in range(0, 256, 17):
                for blue in range(0, 256, 17):
                    color = f"#{red:02X}{green:02X}{blue:02X}"
                    output = self.model.predict(color)
                    self.assertTrue(all(0 <= channel <= 1 for channel in output))
                    self.assertEqual(output, self.model.predict(color))

    def test_invalid_input(self):
        for color in ("red", "#123", "#GG0000", "#1234567", None):
            with self.assertRaises(ValueError):
                self.model.command(color)

    def test_runtime_reproduces_fitted_profile(self):
        # Optional for the standalone stdlib command; pytest supplies src/.
        try:
            from edifier_qr65 import _color_profile as profile
            from edifier_qr65.color import match_rgb
        except ModuleNotFoundError:
            self.skipTest("Use PYTHONPATH=src to verify the runtime profile")
        self.assertEqual(profile.PROFILE_NAME, self.model.data["profile"])
        self.assertEqual(profile.POWER, self.model.power)
        self.assertEqual(profile.NEUTRAL_SATURATION, NEUTRAL_SATURATION)
        self.assertEqual(profile.NEUTRAL_BLEND_END, NEUTRAL_BLEND_END)
        self.assertEqual(profile.WHITE, self.model.white)
        self.assertEqual(profile.BOUNDARY, tuple(self.model.boundary))
        self.assertEqual(profile.RESIDUALS, tuple(self.model.residuals))
        for red in range(0, 256, 17):
            for green in range(0, 256, 17):
                for blue in range(0, 256, 17):
                    color = f"#{red:02X}{green:02X}{blue:02X}"
                    expected = self.model.command(color)
                    actual = "#" + "".join(f"{v:02X}" for v in match_rgb(red, green, blue))
                    self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
