#!/usr/bin/env python3
"""Install Hikaide without changing desktop settings or user CSS."""

import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile


SOURCE = Path(__file__).resolve().parents[1] / "themes" / "Hikaide"
REQUIRED = (
    "index.theme", "shared/colors.css", "shared/widgets.css",
    "gtk-3.0/gtk.css", "gtk-3.0/gtk-dark.css", "gtk-3.0/settings.ini",
    "gtk-4.0/gtk.css", "gtk-4.0/gtk-dark.css",
    "assets/check.svg", "assets/minus.svg", "assets/dot.svg",
)


def install(theme_root):
    for name in REQUIRED:
        if not (SOURCE / name).is_file():
            raise ValueError(f"Incomplete theme: missing {name}")
    if any(p.is_symlink() for p in SOURCE.rglob("*")):
        raise ValueError("Theme source must not contain symlinks")
    root = Path(theme_root).expanduser().resolve()
    target = root / "Hikaide"
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError(f"Refusing to replace a symlink or file: {target}")
    if target.exists():
        metadata = target / "index.theme"
        if not metadata.is_file() or "GtkTheme=Hikaide" not in metadata.read_text():
            raise ValueError(f"Refusing to replace an unrecognized directory: {target}")
    if target == SOURCE or target in SOURCE.parents or SOURCE in target.parents:
        raise ValueError("Installation destination must be outside the theme source")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hikaide-install-", dir=root) as staging:
        staged = Path(staging) / "Hikaide"
        shutil.copytree(SOURCE, staged)
        # Appearance managers may symlink entry CSS from a different directory.
        for css in staged.rglob("*.css"):
            def installed_url(match):
                resource = (css.parent / match[1]).resolve(strict=True).relative_to(staged)
                return f'url("{(target / resource).as_uri()}")'
            css.write_text(re.sub(r'url\("([^\"]+)"\)', installed_url, css.read_text()))
        backup = None
        if target.exists():
            backup = Path(tempfile.mkdtemp(prefix=".Hikaide-backup-", dir=root)) / "Hikaide"
            target.rename(backup)
        try:
            staged.rename(target)
        except OSError:
            if backup is not None:
                backup.rename(target)
                backup.parent.rmdir()
            raise
    return target, backup


def main():
    default = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "themes"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=default, help="theme root (default: XDG user themes)")
    args = parser.parse_args()
    try:
        target, backup = install(args.dest)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Install failed: {error}\n")
    print(f"Installed {target}")
    if backup:
        print(f"Previous installation preserved at {backup}")
    print("Desktop settings, user CSS, icons, fonts and cursors were not changed.")


if __name__ == "__main__":
    main()
