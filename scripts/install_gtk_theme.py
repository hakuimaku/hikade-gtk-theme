#!/usr/bin/env python3
"""Install the Hikaide dark/light pair without changing desktop settings."""
import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile
from materialize import ROOT, SOURCE, REQUIRED, VARIANTS, materialize


def install(theme_root):
    """Stage both themes and restore the previous pair on replacement failure."""
    root = Path(theme_root).expanduser().resolve()
    for name in VARIANTS.values():
        target = root / name
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise ValueError(f"Refusing to replace a symlink or file: {target}")
        if target.exists():
            metadata = target / "index.theme"
            if metadata.is_symlink() or not metadata.is_file() or f"GtkTheme={name}" not in metadata.read_text().splitlines():
                raise ValueError(f"Refusing to replace an unrecognized directory: {target}")
        for source in (SOURCE, ROOT / "themes"):
            if target == source or target in source.parents or source in target.parents:
                raise ValueError("Installation destination must be outside the theme source")
    # Build and validate before creating or changing the install root.
    with tempfile.TemporaryDirectory(prefix="hikaide-build-") as generated:
        materialize(generated)
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".hikaide-install-", dir=root) as staging:
            for name in VARIANTS.values():
                staged = Path(staging) / name
                target = root / name
                shutil.copytree(Path(generated) / name, staged)
                # Appearance managers can symlink entry CSS from another directory.
                for css in staged.rglob("*.css"):
                    def installed_url(match):
                        """Bind resources to the final installation location."""
                        resource = (css.parent / match[1]).resolve(strict=True).relative_to(staged)
                        return f'url("{(target / resource).as_uri()}")'
                    css.write_text(re.sub(r'url\("([^\"]+)"\)', installed_url, css.read_text()))
            backup = Path(tempfile.mkdtemp(prefix=".Hikaide-backup-", dir=root))
            replaced = []
            try:
                for name in VARIANTS.values():
                    target = root / name
                    if target.exists():
                        target.rename(backup / name)
                    (Path(staging) / name).rename(target)
                    replaced.append(target)
            except OSError:
                for target in reversed(replaced):
                    shutil.rmtree(target)
                for previous in backup.iterdir():
                    previous.rename(root / previous.name)
                backup.rmdir()
                raise
            if not any(backup.iterdir()):
                backup.rmdir()
                backup = None
    # Preserve the existing return contract for the legacy dark theme.
    return root / "Hikaide", backup / "Hikaide" if backup else None


def main():
    """Install to the selected user theme root."""
    default = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "themes"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=default, help="theme root (default: XDG user themes)")
    args = parser.parse_args()
    try:
        target, backup = install(args.dest)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Install failed: {error}\n")
    print(f"Installed {target} and {target.parent / 'Hikaide-Light'}")
    if backup:
        print(f"Previous installations preserved at {backup.parent}")
    print("Desktop settings, user CSS, icons, fonts and cursors were not changed.")


if __name__ == "__main__":
    main()
