"""Check semantic contrast and reproducible release output for both modes."""
from pathlib import Path
import re
import io
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from materialize import ROOT, SOURCE, VARIANTS, materialize


def luminance(color):
    """Calculate WCAG relative luminance for an sRGB hex color."""
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return sum(weight * (c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4)
               for weight, c in zip((.2126, .7152, .0722), channels))


def contrast(a, b):
    """Return the contrast ratio of two opaque colors."""
    low, high = sorted((luminance(a), luminance(b)))
    return (high + .05) / (low + .05)


class PaletteTests(unittest.TestCase):
    def test_semantic_contrast(self):
        """Text, selections and indicators remain readable in both palettes."""
        palettes = {}
        for mode in VARIANTS:
            colors = dict(re.findall(r'@define-color (\w+) (#[0-9a-f]{6});',
                                     (SOURCE / f"palettes/{mode}.css").read_text()))
            palettes[mode] = colors
            for role in ("base", "surface", "selection", "selection_backdrop", "thumb"):
                self.assertGreaterEqual(contrast(colors["haku_fg"], colors[f"haku_{role}"]), 4.5, (mode, role))
            self.assertGreaterEqual(contrast(colors["haku_disabled"], colors["haku_surface"]), 3)
            self.assertGreaterEqual(contrast(colors["haku_indicator"], colors["haku_thumb"]), 4.5)
            for role in ("hover", "active", "focus", "selection"):
                self.assertNotEqual(colors[f"haku_{role}"], colors["haku_base"])
        self.assertGreater(luminance(palettes["light"]["haku_base"]), luminance(palettes["dark"]["haku_base"]))

    @unittest.skipUnless(shutil.which("rsvg-convert"), "indicator renders require librsvg and Pillow")
    def test_indicator_renders_on_both_backgrounds(self):
        """Check generated checked, mixed and radio paints at their native size."""
        from PIL import Image
        for mode, name in VARIANTS.items():
            expected = (27, 27, 27) if mode == "light" else (255, 255, 255)
            for asset in ("check", "minus", "dot"):
                path = ROOT / "themes" / name / "assets" / f"{asset}.svg"
                png = subprocess.run(["rsvg-convert", str(path)], check=True, capture_output=True).stdout
                image = Image.open(io.BytesIO(png)).convert("RGBA")
                pixels = image.load()
                opaque = [pixels[x, y][:3] for y in range(16) for x in range(16) if pixels[x, y][3] == 255]
                self.assertGreater(len(opaque), 5, (mode, asset))
                self.assertEqual(set(opaque), {expected}, (mode, asset))

    def test_release_matches_canonical_sources(self):
        """Generated imports stay local and release files have no stale edits."""
        with tempfile.TemporaryDirectory() as temporary:
            materialize(temporary)
            for name in VARIANTS.values():
                output = Path(temporary) / name
                for file in output.rglob("*"):
                    if file.is_file():
                        self.assertEqual(file.read_bytes(), (ROOT / "themes" / name / file.relative_to(output)).read_bytes())
                        self.assertNotIn(b"@INDICATOR@", file.read_bytes())
            light = Path(temporary) / "Hikaide-Light"
            self.assertEqual((light / "dark/shared/colors.css").read_bytes(), (SOURCE / "palettes/dark.css").read_bytes())
