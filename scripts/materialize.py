#!/usr/bin/env python3
"""Materialize two relocatable GTK themes from shared geometry and palettes."""
from pathlib import Path
import re
import shutil

# Canonical sources and public theme names.
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "theme-src"
VARIANTS = {"dark": "Hikaide", "light": "Hikaide-Light"}
REQUIRED = (
    "index.theme", "shared/colors.css", "shared/widgets.css",
    "gtk-3.0/gtk.css", "gtk-3.0/gtk-dark.css", "gtk-3.0/settings.ini",
    "gtk-4.0/gtk.css", "gtk-4.0/gtk-dark.css",
    "assets/check.svg", "assets/minus.svg", "assets/dot.svg",
)


def validate(theme):
    """Reject incomplete themes, symlinks and references outside the theme."""
    for name in REQUIRED:
        if not (theme / name).is_file():
            raise ValueError(f"Incomplete theme: missing {name}")
    if any(p.is_symlink() for p in theme.rglob("*")):
        raise ValueError("Theme source must not contain symlinks")
    for css in theme.rglob("*.css"):
        for name in re.findall(r'url\("([^\"]+)"\)', css.read_text()):
            resource = (css.parent / name).resolve(strict=True)
            if not resource.is_relative_to(theme.resolve()) or not resource.is_file():
                raise ValueError(f"Escaping or invalid theme resource: {resource}")


def materialize(destination):
    """Generate both themes, including a local dark fallback in the light theme."""
    if not SOURCE.is_dir():
        raise ValueError(f"Missing theme source: {SOURCE}")
    if SOURCE.is_symlink() or any(p.is_symlink() for p in SOURCE.rglob("*")):
        raise ValueError("Theme source must not contain symlinks")
    for mode, name in VARIANTS.items():
        theme = Path(destination) / name
        shutil.copytree(SOURCE, theme, ignore=shutil.ignore_patterns("palettes"))
        palette = (SOURCE / f"palettes/{mode}.css").read_text()
        (theme / "shared/colors.css").write_text(palette)
        metadata = theme / "index.theme"
        metadata.write_text(metadata.read_text().replace("Hikaide", name))
        color = re.search(r"@define-color haku_indicator (#[0-9a-fA-F]{6});", palette)
        if color is None:
            raise ValueError(f"Missing indicator paint in {mode} palette")
        for asset in (theme / "assets").glob("*.svg"):
            asset.write_text(asset.read_text().replace("@INDICATOR@", color[1]))
        if mode == "light":
            shutil.copytree(Path(destination) / "Hikaide", theme / "dark")
            for version in ("3.0", "4.0"):
                (theme / f"gtk-{version}/gtk-dark.css").write_text(
                    f'@import url("../dark/gtk-{version}/gtk.css");\n')
        validate(theme)


if __name__ == "__main__":
    import tempfile
    # Validate generated files before replacing release output.
    with tempfile.TemporaryDirectory() as temporary:
        materialize(temporary)
        for name in VARIANTS.values():
            target = ROOT / "themes" / name
            if target.is_symlink():
                raise ValueError(f"Refusing symlinked output: {target}")
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(Path(temporary) / name, target)
